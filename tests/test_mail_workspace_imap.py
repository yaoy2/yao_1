"""IMAP original-byte and retry contract tests; all data stays in temp folders."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from utils import mail_workspace as mail


class MailWorkspaceImapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "workspace"
        self.raw_source = self.base / "download.eml"
        self.original_bytes = (b"From: staff@example.edu\r\nSubject: original\r\n"
                               b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
                               + "原始正文，保留全部字节。".encode("utf-8") + b"\r\n\x00\xff")
        self.raw_source.write_bytes(self.original_bytes)
        mail.initialize(self.root, "sample@example.edu")

    def batch(self):
        return {
            "schema_version": 1, "account": "sample@example.edu", "kind": "daily", "id": "imap-run-1",
            "started_at": "2026-09-05T19:58:00+08:00", "finished_at": "2026-09-05T20:00:00+08:00",
            "window": {"since": "2026-09-05T00:00:00+08:00", "through": "2026-09-05T20:00:00+08:00", "complete": True},
            "messages": [{"id": "imap-stable-1", "received_at": "2026-09-05T18:30:00+08:00",
                          "sender": "教务部门", "subject": "历史邮件", "folder": "INBOX",
                          "body_text": "本地完整正文标记", "summary": "待核对内容", "category": "未分类",
                          "headers_text": "local-header-marker", "internet_message_id": "local-id-marker",
                          "raw_eml_download_path": str(self.raw_source),
                          "raw_sha256": hashlib.sha256(self.original_bytes).hexdigest(),
                          "attachments_complete": True, "expected_attachment_count": 0, "attachments": []}],
            "actions": [], "errors": [],
        }

    def next_window(self, batch):
        batch = copy.deepcopy(batch)
        batch["id"] = "imap-run-2"
        batch["started_at"] = "2026-09-06T19:58:00+08:00"
        batch["finished_at"] = "2026-09-06T20:00:00+08:00"
        batch["window"].update(since="2026-09-05T20:00:00+08:00", through="2026-09-06T20:00:00+08:00")
        batch["messages"][0]["retry_of_existing"] = True
        return batch

    def only_message(self):
        return mail.load_dashboard(self.root)["messages"][0]

    def test_exact_original_bytes_hash_size_and_idempotent_ingest(self):
        batch = self.batch()
        first_result = mail.ingest(self.root, batch)
        before_paths = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*") if path.is_file())
        second_result = mail.ingest(self.root, batch)
        after_paths = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*") if path.is_file())
        self.assertEqual(first_result, second_result)
        self.assertEqual(before_paths, after_paths)
        item = self.only_message()
        self.assertEqual(self.original_bytes, (self.root / item["raw_eml_path"]).read_bytes())
        self.assertEqual(hashlib.sha256(self.original_bytes).hexdigest(), item["raw_eml_sha256"])
        self.assertEqual(len(self.original_bytes), item["raw_eml_size"])
        snapshot = json.loads((self.root / item["archive_path"]).read_text(encoding="utf-8"))
        self.assertEqual("imap_text_snapshot", snapshot["format"])
        self.assertFalse(snapshot["is_original_eml"])
        self.assertEqual(item["raw_eml_path"], snapshot["original_eml"]["raw_eml_path"])
        self.assertEqual(1, len(mail.load_dashboard(self.root)["runs"]))

    def test_new_original_version_preserves_both_raw_and_snapshot_versions(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        old = self.only_message()
        old_snapshot = (self.root / old["archive_path"]).read_bytes()
        replacement = self.original_bytes + b"additional original bytes\r\n"
        self.raw_source.write_bytes(replacement)
        batch["messages"][0]["raw_sha256"] = hashlib.sha256(replacement).hexdigest()
        self.assertEqual("success", mail.ingest(self.root, batch)["status"])
        new = self.only_message()
        self.assertNotEqual(old["raw_eml_path"], new["raw_eml_path"])
        self.assertNotEqual(old["archive_path"], new["archive_path"])
        self.assertEqual(self.original_bytes, (self.root / old["raw_eml_path"]).read_bytes())
        self.assertEqual(old_snapshot, (self.root / old["archive_path"]).read_bytes())
        self.assertEqual(replacement, (self.root / new["raw_eml_path"]).read_bytes())
        self.assertEqual([], list(self.root.rglob(".mail-eml-*.tmp")))

    def test_mismatched_download_is_partial_retains_prior_original_and_cursor(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        old = self.only_message()
        old_through = mail.status(self.root)["coverage"]["through"]
        retry = self.next_window(batch)
        self.raw_source.write_bytes(b"wrong downloaded bytes")
        result = mail.ingest(self.root, retry)
        self.assertEqual("partial", result["status"])
        self.assertEqual(old_through, result["coverage"]["through"])
        self.assertFalse(result["coverage"]["complete"])
        self.assertEqual(old["raw_eml_path"], self.only_message()["raw_eml_path"])
        self.assertEqual(self.original_bytes, (self.root / old["raw_eml_path"]).read_bytes())
        self.assertEqual(1, len(list(self.root.rglob("*.eml"))))
        self.assertEqual([], list(self.root.rglob(".mail-eml-*.tmp")))

    def test_missing_retained_original_blocks_cursor_on_metadata_only_retry(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        old = self.only_message()
        old_through = mail.status(self.root)["coverage"]["through"]
        # Test data only: simulate a missing archived original.
        (self.root / old["raw_eml_path"]).unlink()
        retry = self.next_window(batch)
        retry["messages"][0].pop("raw_eml_download_path")
        retry["messages"][0].pop("body_text")
        result = mail.ingest(self.root, retry)
        self.assertEqual("partial", result["status"])
        self.assertEqual(old_through, result["coverage"]["through"])
        self.assertEqual(old["archive_path"], self.only_message()["archive_path"])

    def test_conflicting_existing_raw_destination_is_preserved(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        old = self.only_message()
        destination = self.root / old["raw_eml_path"]
        destination.write_bytes(b"existing conflicting bytes retained for inspection")
        result = mail.ingest(self.root, batch)
        self.assertEqual("partial", result["status"])
        self.assertEqual(b"existing conflicting bytes retained for inspection", destination.read_bytes())
        self.assertEqual([], list(self.root.rglob(".mail-eml-*.tmp")))

    def test_cloud_snapshot_excludes_all_raw_fields_and_local_message_content(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        local = self.only_message()
        self.assertIn("raw_eml_path", local)
        cloud = mail.cloud_snapshot(self.root)
        encoded = json.dumps(cloud, ensure_ascii=False)
        for private_value in ["raw_eml_path", "raw_eml_sha256", "raw_eml_size", "raw_eml_download_path",
                              "raw_sha256", str(self.raw_source), "local-header-marker", "local-id-marker",
                              "本地完整正文标记", local["raw_eml_path"]]:
            self.assertNotIn(private_value, encoded)
        self.assertEqual(local["id"], cloud["messages"][0]["id"])

    def test_known_historic_retry_is_accepted_and_preserves_user_out_of_scope(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        data = mail.load_dashboard(self.root)
        data["messages"][0].update(triage_status="out_of_scope", triage_updated_at="2026-09-05T21:00:00+08:00")
        mail._atomic_json(self.root / "dashboard.json", data)
        retry = self.next_window(batch)
        retry["messages"][0].update(triage_status="pending", triage_updated_at="2099-01-01T00:00:00+08:00")
        retry["actions"] = [{"id": "extracted-later", "message_id": "imap-stable-1", "title": "新提取事项",
                             "status": "pending"}]
        result = mail.ingest(self.root, retry)
        self.assertEqual("success", result["status"])
        self.assertEqual(retry["window"]["through"], result["coverage"]["through"])
        data = mail.load_dashboard(self.root)
        self.assertEqual("out_of_scope", data["messages"][0]["triage_status"])
        self.assertEqual("2026-09-05T21:00:00+08:00", data["messages"][0]["triage_updated_at"])
        self.assertEqual("out_of_scope", data["actions"][0]["status"])
        self.assertIsNone(data["actions"][0]["completed_at"])
        self.assertNotIn("retry_of_existing", data["messages"][0])

    def test_unknown_historic_retry_is_rejected_before_any_archive_changes(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        retry = self.next_window(batch)
        retry["messages"][0]["id"] = "never-seen-before"
        before = (self.root / "dashboard.json").read_bytes()
        old_files = sorted(str(path) for path in self.root.rglob("*") if path.is_file())
        with self.assertRaisesRegex(ValueError, "outside the declared collection window"):
            mail.ingest(self.root, retry)
        self.assertEqual(before, (self.root / "dashboard.json").read_bytes())
        self.assertEqual(old_files, sorted(str(path) for path in self.root.rglob("*") if path.is_file()))

    def test_historic_known_message_still_requires_explicit_retry_flag(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        retry = self.next_window(batch)
        retry["messages"][0].pop("retry_of_existing")
        with self.assertRaisesRegex(ValueError, "outside the declared collection window"):
            mail.ingest(self.root, retry)

    def test_empty_attachment_and_retained_legacy_empty_success_are_not_complete(self):
        empty = self.base / "empty.xlsx"
        empty.write_bytes(b"")
        batch = self.batch()
        batch["messages"][0].update(expected_attachment_count=1, attachments=[{
            "id": "empty", "name": "empty.xlsx", "download_path": str(empty)}])
        self.assertEqual("partial", mail.ingest(self.root, batch)["status"])
        data = mail.load_dashboard(self.root)
        legacy = self.root / "archive" / "legacy-empty.xlsx"
        legacy.write_bytes(b"")
        data["messages"][0]["attachments"][0].update(status="success", size=0,
            path="archive/legacy-empty.xlsx", sha256=hashlib.sha256(b"").hexdigest())
        mail._atomic_json(self.root / "dashboard.json", data)
        attachment = batch["messages"][0]["attachments"][0]
        attachment.pop("download_path")
        attachment.update(status="missing", error="MIME_ATTACHMENT_EMPTY")
        self.assertEqual("partial", mail.ingest(self.root, batch)["status"])
        self.assertNotEqual("success", mail.load_dashboard(self.root)["messages"][0]["attachments"][0]["status"])

    def test_next_day_daily_report_starts_at_midnight_and_excludes_previous_evening(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        mail.generate_report(self.root, "daily", "2026-09-05T20:00:00+08:00")
        followup = self.next_window(batch)
        yesterday = copy.deepcopy(batch["messages"][0])
        yesterday.update(id="yesterday-evening", subject="昨日晚间邮件", received_at="2026-09-05T23:59:59+08:00")
        today = copy.deepcopy(batch["messages"][0])
        today.update(id="today-midnight", subject="今日零点邮件", received_at="2026-09-06T00:00:00+08:00")
        followup["messages"] = [yesterday, today]
        self.assertEqual("success", mail.ingest(self.root, followup)["status"])
        result = mail.generate_report(self.root, "daily", "2026-09-06T20:00:00+08:00")
        report = mail.load_dashboard(self.root)["reports"][-1]
        self.assertEqual("2026-09-06T00:00:00+08:00", report["period_start"])
        self.assertEqual(1, result["message_count"])
        self.assertTrue(result["coverage_complete"])
        self.assertIn("今日零点邮件", report["markdown"])
        self.assertNotIn("昨日晚间邮件", report["markdown"])


if __name__ == "__main__":
    unittest.main()
