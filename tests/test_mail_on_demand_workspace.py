import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.mail_workbench import main, redact_review_batch
from utils import mail_workspace as mail


class OnDemandWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "workspace"
        mail.initialize(self.root, "test@example.edu")
        self.body = "transient-full-original-body-never-archived"
        self.raw = Path(self.temp.name) / "original.eml"
        self.raw.write_bytes(b"raw-original")
        self.file = Path(self.temp.name) / "source.pdf"
        self.file.write_bytes(b"attachment")
        self.batch = {"schema_version": 1, "account": "test@example.edu", "kind": "daily",
            "id": "imap-" + "a" * 32, "storage_mode": "on_demand",
            "started_at": "2026-09-08T20:00:00+08:00", "finished_at": "2026-09-08T20:01:00+08:00",
            "window": {"since": "2026-09-08T00:00:00+08:00", "through": "2026-09-08T20:00:00+08:00", "complete": True},
            "messages": [{"id": "<test@example.edu>", "received_at": "2026-09-08T10:00:00+08:00",
                "subject": "Reviewed message", "sender": "school", "folder": "收件箱", "category": "教学",
                "summary": "Reviewed summary", "body_text": self.body, "headers_text": "full headers",
                "attachment_reviews": [{"text": "transient attachment full text"}],
                "source_url": "https://mail.nsu.edu.cn/owa/", "raw_eml_download_path": str(self.raw),
                "raw_sha256": hashlib.sha256(self.raw.read_bytes()).hexdigest(),
                "attachments_complete": True, "mime_structure_complete": True, "expected_attachment_count": 1,
                "attachments": [{"id": "a1", "name": "file.pdf", "size": 10,
                    "sha256": hashlib.sha256(self.file.read_bytes()).hexdigest(), "download_path": str(self.file)}]}],
            "actions": [], "errors": []}

    def test_only_metadata_persists_despite_supplied_legacy_download_paths(self):
        with patch.object(mail, "_archive_raw_eml", side_effect=AssertionError("must not archive raw")), \
             patch.object(mail, "_archive_attachment", side_effect=AssertionError("must not copy attachment")):
            result = mail.ingest(self.root, self.batch)
        self.assertEqual(("success", 0, 0), (result["status"], result["attachment_count"], result["incomplete_attachments"]))
        data = mail.load_dashboard(self.root)
        self.assertEqual("on_demand", data["collection_storage"])
        message = data["messages"][0]
        self.assertEqual("", message["archive_path"])
        self.assertNotIn("raw_eml_path", message)
        self.assertNotIn("body_text", message)
        self.assertEqual("not_requested", message["attachments"][0]["status"])
        self.assertEqual([], list((self.root / "archive").rglob("*")))
        for path in self.root.rglob("*.json"):
            self.assertNotIn(self.body, path.read_text(encoding="utf-8"))
        public = mail.public_snapshot(data, self.root)
        self.assertEqual("on_demand", public["collection_storage"])

    def test_local_policy_cannot_be_overridden_by_full_batch(self):
        mail._atomic_json(self.root / "config.json", {"collection_storage": "on_demand"})
        self.batch.pop("storage_mode")
        mail.ingest(self.root, self.batch)
        self.assertEqual([], list((self.root / "archive").rglob("*")))

    def test_empty_attachment_does_not_fail_collection_but_structure_error_does(self):
        self.batch["messages"][0]["attachments_complete"] = False
        self.batch["messages"][0]["attachments"][0].update(size=0, error="MIME_ATTACHMENT_EMPTY")
        self.assertEqual("success", mail.ingest(self.root, self.batch)["status"])
        self.batch["messages"][0]["mime_structure_complete"] = False
        self.assertEqual("partial", mail.ingest(self.root, self.batch)["status"])

    def test_existing_original_and_files_are_preserved(self):
        full = copy.deepcopy(self.batch)
        full.pop("storage_mode")
        mail.ingest(self.root, full)
        before = {p: p.read_bytes() for p in (self.root / "archive").rglob("*") if p.is_file()}
        previous = mail.load_dashboard(self.root)["messages"][0]
        result = mail.ingest(self.root, self.batch)
        current = mail.load_dashboard(self.root)["messages"][0]
        self.assertEqual(previous["raw_eml_path"], current["raw_eml_path"])
        self.assertEqual(previous["archive_path"], current["archive_path"])
        self.assertEqual(0, result["attachment_count"])
        self.assertEqual(before, {p: p.read_bytes() for p in (self.root / "archive").rglob("*") if p.is_file()})

    def test_ingest_redacts_only_owned_review_batch_after_success(self):
        incoming = self.root / "incoming"
        incoming.mkdir()
        path = incoming / (self.batch["id"] + ".json")
        mail._atomic_json(path, self.batch)
        with patch("builtins.print"):
            code = main(["--root", str(self.root), "ingest", "--batch", str(path)])
        self.assertEqual(0, code)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(saved["review_content_removed"])
        self.assertNotIn(self.body, path.read_text(encoding="utf-8"))
        self.assertNotIn("body_text", saved["messages"][0])
        self.assertNotIn("attachment_reviews", saved["messages"][0])
        self.assertEqual("Reviewed summary", saved["messages"][0]["summary"])
        foreign = Path(self.temp.name) / path.name
        mail._atomic_json(foreign, self.batch)
        self.assertFalse(redact_review_batch(self.root, foreign, self.batch))
        self.assertIn(self.body, foreign.read_text(encoding="utf-8"))

    def test_cli_redacts_legacy_batch_using_effective_config_or_dashboard_policy(self):
        for policy_source in ("config", "dashboard"):
            with self.subTest(policy_source=policy_source):
                workspace = self.root / policy_source
                mail.initialize(workspace, "test@example.edu")
                if policy_source == "config":
                    mail._atomic_json(workspace / "config.json", {"collection_storage": "on_demand"})
                else:
                    data = mail.load_dashboard(workspace)
                    data["collection_storage"] = "on_demand"
                    mail._atomic_json(workspace / "dashboard.json", data)
                legacy = copy.deepcopy(self.batch)
                legacy["storage_mode"] = "full"
                path = workspace / "incoming" / (legacy["id"] + ".json")
                mail._atomic_json(path, legacy)
                with patch("builtins.print") as output:
                    code = main(["--root", str(workspace), "ingest", "--batch", str(path)])
                self.assertEqual(0, code)
                result = json.loads(output.call_args.args[0])
                self.assertEqual("on_demand", result["storage_mode"])
                self.assertTrue(result["review_content_removed"])
                self.assertNotIn(self.body, path.read_text(encoding="utf-8"))
                self.assertNotIn("attachment_reviews", json.loads(path.read_text(encoding="utf-8"))["messages"][0])
                self.assertEqual([], list((workspace / "archive").rglob("*")))


if __name__ == "__main__":
    unittest.main()
