import copy
import json
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

from scripts import mail_imap_collect as cli
from tests.test_mail_imap import FakeImap, make_message
from tests.test_mail_imap_collect import ACCOUNT, FIRST, HOST, NOW, SECRET, TARGET, ReadonlyMailbox
from utils import mail_imap as imap
from utils import mail_workspace


DATE = "08-Sep-2026 12:00:00 +0800"


class OnDemandCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def collect(self, raw=None, *, client=None, **changes):
        client = client or FakeImap({"INBOX": {1: (raw if raw is not None else make_message(attachment=True), DATE)}})
        arguments = {"account": ACCOUNT, "folders": ["收件箱"], "since": FIRST, "through": NOW,
                     "staging_dir": self.root, "source_url": "https://mail.nsu.edu.cn/owa/",
                     "storage_mode": "on_demand"}
        arguments.update(changes)
        with patch.object(imap, "_write_message", side_effect=AssertionError("on-demand must not write mail or attachments")):
            return imap.collect(client, **arguments)

    def assert_evidence_only(self, batch):
        staging = Path(batch["collection"]["staging_dir"])
        self.assertEqual(["evidence.json"], [path.name for path in staging.iterdir()])
        text = (staging / "evidence.json").read_text(encoding="utf-8")
        for private in ("Please review the attached form.", "Administrative notice", "form contents", "表格.docx"):
            self.assertNotIn(private, text)

    def test_returns_review_text_and_metadata_without_creating_message_or_attachment_files(self):
        batch = self.collect()
        self.assertTrue(batch["window"]["complete"])
        self.assertEqual([], batch["errors"])
        self.assertEqual("on_demand", batch["storage_mode"])
        self.assertEqual("on_demand", batch["collection"]["storage_mode"])
        message = batch["messages"][0]
        self.assertEqual("on_demand", message["storage_mode"])
        self.assertEqual("Please review the attached form.", message["body_text"])
        self.assertEqual("待整理", message["summary"])
        self.assertTrue(message["mime_structure_complete"])
        self.assertTrue(message["attachments_complete"])
        attachment = message["attachments"][0]
        self.assertEqual(("not_requested", "", "表格.docx", 13),
                         (attachment["status"], attachment["path"], attachment["name"], attachment["size"]))
        self.assertEqual(64, len(attachment["sha256"]))
        serialized = json.dumps(batch)
        for field in ("raw_eml_download_path", "raw_sha256", "download_path", '"data"', "headers_text"):
            self.assertNotIn(field, serialized)
        self.assert_evidence_only(batch)

    def test_empty_attachment_is_visible_metadata_and_does_not_fail_unrequested_collection(self):
        message = EmailMessage()
        message["Message-ID"] = "<empty-on-demand@example.edu>"
        message["Subject"] = "Form"
        message.set_content("Attached form")
        message.add_attachment(b"", maintype="application", subtype="octet-stream", filename="empty.xlsx")
        batch = self.collect(message.as_bytes())
        self.assertTrue(batch["window"]["complete"])
        self.assertEqual([], batch["errors"])
        result = batch["messages"][0]
        self.assertTrue(result["mime_structure_complete"])
        self.assertTrue(result["attachments_complete"])
        self.assertEqual(("not_requested", 0, "MIME_ATTACHMENT_EMPTY"),
                         tuple(result["attachments"][0][key] for key in ("status", "size", "error")))
        self.assert_evidence_only(batch)

    def test_broken_mime_tree_still_marks_window_incomplete(self):
        raw = (b'Message-ID: <broken@example.edu>\r\nMIME-Version: 1.0\r\n'
               b'Content-Type: multipart/mixed; boundary="cut"\r\n\r\n'
               b'--cut\r\nContent-Type: text/plain\r\n\r\nBody\r\n'
               b'--cut\r\nContent-Type: application/octet-stream\r\n'
               b'Content-Disposition: attachment; filename="form.txt"\r\n'
               b'Content-Transfer-Encoding: base64\r\n\r\nYWJj\r\n')
        batch = self.collect(raw)
        self.assertFalse(batch["window"]["complete"])
        self.assertIn("IMAP_ATTACHMENTS_INCOMPLETE", batch["errors"])
        self.assertFalse(batch["messages"][0]["mime_structure_complete"])
        self.assertEqual("not_requested", batch["messages"][0]["attachments"][0]["status"])
        self.assert_evidence_only(batch)

    def test_old_missing_attachment_retries_are_suppressed_at_collector_boundary(self):
        client = FakeImap({"INBOX": {1: (make_message("<old@example.edu>"), "01-Aug-2026 12:00:00 +0800")}})
        batch = self.collect(client=client, retry_message_ids=["<old@example.edu>", "sha256:" + "a" * 64])
        self.assertTrue(batch["window"]["complete"])
        self.assertEqual([], batch["messages"])
        self.assertEqual({"requested_count": 0, "resolved_count": 0, "unresolved_count": 0}, batch["collection"]["retry"])
        self.assertFalse(any(call[0] == "SEARCH" and call[2] == "HEADER" for call in client.calls))
        self.assertFalse(any(call[0] == "FETCH" and "BODY" in call[2] for call in client.calls))
        self.assert_evidence_only(batch)

    def test_authentication_notification_is_not_in_review_metadata_or_evidence(self):
        batch = self.collect(make_message(subject="Verification code 123456", body="Your one-time code is 123456."))
        self.assertTrue(batch["window"]["complete"])
        self.assertEqual([], batch["messages"])
        self.assertEqual(1, batch["collection"]["skipped_authentication_notifications"]["count"])
        self.assertNotIn("123456", json.dumps(batch))
        self.assert_evidence_only(batch)

    def test_transport_truncation_still_fails_without_writing_files(self):
        client = FakeImap({"INBOX": {1: (make_message(attachment=True), DATE)}})
        client.truncate.add(1)
        batch = self.collect(client=client)
        self.assertFalse(batch["window"]["complete"])
        self.assertEqual([], batch["messages"])
        self.assertIn("IMAP_BODY_INCOMPLETE", batch["errors"])
        self.assert_evidence_only(batch)

    def test_unknown_storage_mode_fails_before_staging_or_reading_mail(self):
        client = FakeImap()
        with self.assertRaises(ValueError):
            self.collect(client=client, storage_mode="unexpected")
        self.assertEqual([], client.calls)
        self.assertEqual([], list(self.root.iterdir()))

    def test_metadata_whitelist_removes_source_bytes_paths_and_unrequested_extra_fields(self):
        parsed = {"id": "mail", "body_text": "review", "mime_structure_complete": True,
                  "attachments_complete": True, "raw_sha256": "secret", "raw_eml_download_path": "E:/raw",
                  "headers_text": "sensitive headers", "extra": b"raw bytes",
                  "attachments": [{"id": "a", "name": "a.txt", "size": 3, "sha256": "f" * 64,
                                   "data": b"abc", "download_path": "E:/private", "path": "E:/private", "extra": b"binary"}]}
        result = imap._on_demand_message(parsed)
        self.assertEqual("", result["attachments"][0]["path"])
        self.assertEqual("review", result["body_text"])
        for forbidden in ("raw_sha256", "raw_eml_download_path", "headers_text", "download_path", '"data"', "extra"):
            self.assertNotIn(forbidden, json.dumps(result))


class OnDemandWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mail_workspace.initialize(self.root, ACCOUNT)
        self.config = {"account": ACCOUNT, "collection_start": FIRST, "mail_folders": ["收件箱"],
                       "collection_storage": "on_demand", "source_url": "https://mail.nsu.edu.cn/owa/",
                       "imap": {"host": HOST, "port": 993, "ssl": True, "verify_tls": True, "credential_target": TARGET}}
        self.write_config()

    def write_config(self):
        (self.root / "config.json").write_text(json.dumps(self.config), encoding="utf-8")

    def test_wrapper_stages_one_review_json_and_never_retries_or_modifies_old_archives(self):
        old_file = self.root / "archive" / "existing-original.eml"
        old_file.write_bytes(b"previously archived user content")
        dashboard = mail_workspace.load_dashboard(self.root)
        dashboard["messages"] = [{"id": "old-mail", "received_at": "2026-08-01T12:00:00+08:00",
                                   "attachments": [{"id": "old-file", "name": "old.pdf", "status": "missing"}]}]
        mail_workspace._atomic_json(self.root / "dashboard.json", dashboard)
        before = (self.root / "dashboard.json").read_bytes()
        raw = make_message(attachment=True, body="Only this review batch contains body text.")
        client = ReadonlyMailbox({1: (raw, DATE)})
        original_collect = imap.collect
        with patch.object(cli, "read_credential", return_value=(ACCOUNT, SECRET)), \
             patch.object(imap, "connect", return_value=client), \
             patch.object(imap, "collect", wraps=original_collect) as collector:
            summary = cli.collect_workspace(self.root, at=NOW)
        arguments = collector.call_args.kwargs
        self.assertEqual("on_demand", arguments["storage_mode"])
        self.assertEqual([], arguments["retry_message_ids"])
        self.assertEqual("on_demand", summary["storage_mode"])
        batch_path = Path(summary["batch_path"])
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        self.assertEqual("on_demand", batch["storage_mode"])
        self.assertEqual("not_requested", batch["messages"][0]["attachments"][0]["status"])
        files = [path for path in (self.root / "incoming").rglob("*") if path.is_file()]
        self.assertEqual({batch_path, Path(batch["collection"]["staging_dir"]) / "evidence.json"}, set(files))
        body_files = [path for path in self.root.rglob("*.json") if "Only this review batch contains body text." in path.read_text(encoding="utf-8")]
        self.assertEqual([batch_path], body_files)
        self.assertEqual(before, (self.root / "dashboard.json").read_bytes())
        self.assertEqual(b"previously archived user content", old_file.read_bytes())
        self.assertEqual([old_file], [path for path in (self.root / "archive").rglob("*") if path.is_file()])

    def test_invalid_config_storage_mode_is_rejected_before_credentials(self):
        self.config["collection_storage"] = "invalid"
        self.write_config()
        with patch.object(cli, "read_credential") as credential:
            with self.assertRaises(ValueError):
                cli.collect_workspace(self.root, at=NOW)
        credential.assert_not_called()
        self.assertFalse((self.root / "incoming").exists())


if __name__ == "__main__":
    unittest.main()
