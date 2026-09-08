import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from scripts import mail_filing_worker as worker
from scripts import mail_workbench_sync as sync
from tests.test_mail_workbench_sync import fixture
from utils import mail_workspace
from utils.mail_filing import export_message
from utils.mail_filing_state import cancel_unrequested, queue_filing


AT = "2026-09-08T21:00:00+08:00"


def attachment(name="材料.xlsx", data=b"real-attachment"):
    return {"id": name, "name": name, "data": data, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def source(message, attachments=None, complete=True):
    attachments = [attachment()] if attachments is None else attachments
    return {"parsed": {"id": message["id"], "attachments": attachments,
                       "expected_attachment_count": len(attachments), "attachments_complete": complete},
            "error_codes": [], "raw": b"raw-not-an-output", "source": "local_eml"}


class FilingFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.message = fixture()["messages"][0]

    def export(self, value):
        return export_message(self.root, self.root, self.message, source_reader=Mock(return_value=value))

    def test_bytes_and_manifest_are_verified_and_repeat_is_idempotent(self):
        first = self.export(source(self.message))
        self.assertEqual("success", first["status"])
        path = self.root / first["files"][0]["path"]
        self.assertEqual(".", first["destination"])
        self.assertEqual("材料.xlsx", first["files"][0]["path"])
        self.assertEqual(self.root, path.parent)
        self.assertEqual(b"real-attachment", path.read_bytes())
        self.assertEqual(attachment()["sha256"], mail_workspace._sha_file(path))
        second = self.export(source(self.message))
        self.assertEqual(first, second)
        self.assertEqual(1, len(list(self.root.rglob("*.xlsx"))))
        self.assertEqual([], list(self.root.rglob("*.partial")))
        self.assertFalse(any(path.is_dir() for path in self.root.iterdir()))

    def test_same_name_user_file_is_preserved_and_new_content_versioned(self):
        original = self.root / "材料.xlsx"
        original.write_bytes(b"user-edited-file")
        result = self.export(source(self.message))
        self.assertEqual("success", result["status"])
        self.assertEqual(b"user-edited-file", original.read_bytes())
        self.assertNotEqual(original, self.root / result["files"][0]["path"])
        self.assertEqual(result, self.export(source(self.message)))
        self.assertFalse(any(path.is_dir() for path in self.root.iterdir()))

    def test_existing_same_name_same_content_is_reused_without_renaming(self):
        original = self.root / "材料.xlsx"
        original.write_bytes(attachment()["data"])
        result = self.export(source(self.message))
        self.assertEqual(("success", ".", "材料.xlsx"),
                         (result["status"], result["destination"], result["files"][0]["path"]))
        self.assertEqual([original], list(self.root.iterdir()))

    def test_duplicate_names_are_all_preserved_and_names_cannot_escape_root(self):
        values = [attachment("../../CON.xlsx", b"one"), attachment("../../CON.xlsx", b"two")]
        result = self.export(source(self.message, values))
        self.assertEqual(2, result["saved_count"])
        paths = [self.root / row["path"] for row in result["files"]]
        self.assertEqual(2, len(set(paths)))
        self.assertTrue(all(path.resolve().is_relative_to(self.root.resolve()) for path in paths))
        self.assertTrue(all(path.parent == self.root for path in paths))
        self.assertFalse(any("/" in row["path"] or "\\" in row["path"] for row in result["files"]))
        self.assertFalse(any(path.is_dir() for path in self.root.iterdir()))

    def test_zero_byte_is_partial_and_bad_digest_is_not_saved(self):
        values = [attachment(), attachment("空.xlsx", b"")]
        result = self.export(source(self.message, values, False))
        self.assertEqual(("partial", 1, 2), (result["status"], result["saved_count"], result["total_count"]))
        self.assertIn("ATTACHMENT_EMPTY", result["error_codes"])
        wrong = attachment("bad.pdf", b"bad")
        wrong["sha256"] = "a" * 64
        result = self.export(source(self.message, [wrong]))
        self.assertEqual("error", result["status"])
        self.assertEqual([], result["files"])

    def test_incomplete_mime_cannot_claim_no_attachments(self):
        result = self.export(source(self.message, [], False))
        self.assertEqual("error", result["status"])
        self.assertIn("ATTACHMENT_INVENTORY_INCOMPLETE", result["error_codes"])
        complete = self.export(source(self.message, [], True))
        self.assertEqual(("success", 0, ""), (complete["status"], complete["total_count"], complete["destination"]))

    def test_missing_or_sensitive_original_does_not_create_output(self):
        for value in ({"parsed": None, "error_codes": ["SOURCE_NOT_FOUND"]},
                      {"parsed": {"id": "m1", "authentication_notice": True}, "error_codes": []}):
            with self.subTest(value=value):
                result = self.export(value)
                self.assertEqual("error", result["status"])
                self.assertEqual([], result["files"])
                self.assertEqual([], list(self.root.iterdir()))


class FakeClient:
    def __init__(self, first, latest=None, conflict=False):
        self.reads = [copy.deepcopy(first), copy.deepcopy(first if latest is None else latest)]
        self.calls = []
        self.conflict = conflict

    def read(self):
        return {"snapshot": self.reads.pop(0), "version": "b" * 40 if not self.reads else "a" * 40}

    def write(self, snapshot, version):
        self.calls.append((copy.deepcopy(snapshot), version))
        if self.conflict:
            raise sync.MailCommandError("conflict")
        return "c" * 40


class FilingWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = fixture()
        self.data["actions"][0].update(status="archived", updated_at=AT)
        queue_filing(self.data, ["m1"], AT)
        mail_workspace._atomic_json(self.root / "dashboard.json", self.data)
        mail_workspace._atomic_json(self.root / "config.json", {
            "private_repo": sync.DEFAULT_REPO, "private_branch": "main",
            "filing": {"enabled": True, "destination_root": str(self.root)}})
        self.exporter = Mock(return_value={"status": "success", "destination": ".",
            "saved_count": 1, "total_count": 1, "error_count": 0, "error_codes": [],
            "files": [{"path": "file.xlsx", "size": 12, "sha256": "a" * 64}]})

    def test_latest_unrelated_edits_and_raw_local_fields_survive_ack(self):
        latest = copy.deepcopy(self.data)
        latest["messages"][0]["summary"] = "new remote summary"
        client = FakeClient(self.data, latest)
        result = worker.run_once(self.root, client=client, exporter=self.exporter)
        self.assertEqual((1, 1), (result["processed_count"], result["acknowledged_count"]))
        uploaded, version = client.calls[0]
        self.assertEqual("b" * 40, version)
        self.assertEqual("new remote summary", uploaded["messages"][0]["summary"])
        self.assertNotIn("body_text", uploaded["messages"][0])
        self.assertNotIn("files", uploaded["messages"][0]["filing"])
        local = mail_workspace.load_dashboard(self.root)
        self.assertEqual(self.data["messages"][0]["body_text"], local["messages"][0]["body_text"])
        self.assertEqual("archived", local["actions"][0]["status"])
        self.assertIsNone(local["actions"][0]["completed_at"])

    def test_cancellation_and_requeued_request_are_not_overwritten(self):
        for requeue in (False, True):
            latest = copy.deepcopy(self.data)
            if requeue:
                queue_filing(latest, ["m1"], "2026-09-08T21:01:00+08:00")
            else:
                latest["actions"][0]["status"] = "pending"
                cancel_unrequested(latest, ["m1"], "2026-09-08T21:01:00+08:00")
            client = FakeClient(self.data, latest)
            result = worker.run_once(self.root, client=client, exporter=self.exporter)
            self.assertEqual("superseded", result["status"])
            self.assertEqual([], client.calls)

    def test_conflict_stops_without_retry_and_keeps_local_receipt(self):
        client = FakeClient(self.data, conflict=True)
        with self.assertRaises(sync.MailCommandError):
            worker.run_once(self.root, client=client, exporter=self.exporter)
        self.assertEqual(1, len(client.calls))
        self.assertEqual(1, len(list((self.root / "state/filing_results").glob("*.json"))))
        self.assertEqual("pending", mail_workspace.load_dashboard(self.root)["messages"][0]["filing"]["status"])

    def test_completed_and_unselected_mail_are_not_exported_again(self):
        self.data["messages"][0]["filing"].update(status="success", destination=".", saved_count=0, total_count=0)
        client = FakeClient(self.data)
        result = worker.run_once(self.root, client=client, exporter=self.exporter)
        self.assertEqual("idle", result["status"])
        self.exporter.assert_not_called()
        self.assertEqual([], client.calls)


if __name__ == "__main__":
    unittest.main()
