import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import mail_manual_collect as worker
from scripts import mail_collection_request as jobs
from scripts import mail_workbench_sync as sync
from utils import mail_workspace as workspace
from utils.mail_collection_state import new_request, claim_collection
from tests.test_mail_workbench_sync import fixture


class Client:
    repo = sync.DEFAULT_REPO
    branch = "main"

    def __init__(self, data):
        self.snapshot = copy.deepcopy(data)
        self.version = "a" * 40
        self.writes = []
        self.fail = None

    def read(self):
        return {"snapshot": copy.deepcopy(self.snapshot), "version": self.version}

    def write(self, snapshot, version):
        if version != self.version or (self.fail and self.fail(snapshot)):
            raise sync.MailCommandError("conflict")
        self.writes.append(copy.deepcopy(snapshot))
        self.snapshot = copy.deepcopy(snapshot)
        self.version = format(len(self.writes), "040x")
        return self.version


class ManualCollectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = fixture()
        self.data["collection_storage"] = "on_demand"
        workspace._atomic_json(self.root / "dashboard.json", self.data)
        workspace._atomic_json(self.root / "config.json", {
            "collection_mode": "manual", "collection_storage": "on_demand",
            "private_repo": sync.DEFAULT_REPO, "private_branch": "main",
            "filing": {"enabled": False, "destination_root": "unavailable"}})
        self.client = Client(workspace.public_snapshot(self.data, self.root))
        self.collector = Mock(side_effect=self.collect)
        self.reviewer = Mock(side_effect=self.review)

    def collect(self, root, **kwargs):
        self.batch = {"schema_version": 1, "account": self.data["account"],
            "id": "imap-" + "9" * 32, "kind": "daily", "storage_mode": "on_demand",
            "manual_request_id": kwargs.get("manual_request_id"),
            "started_at": "2026-09-09T18:00:00+08:00", "finished_at": "2026-09-09T18:01:00+08:00",
            "window": {"since": "2026-09-05T00:00:00+08:00", "through": "2026-09-09T18:00:00+08:00", "complete": True},
            "messages": [{"id": "m2", "received_at": "2026-09-09T16:00:00+08:00",
                "subject": "new message", "sender": "school", "folder": "INBOX", "category": "", "summary": "",
                "source_url": "https://mail.nsu.edu.cn/owa/", "body_text": "private-review-marker",
                "attachment_reviews": [{"text": "private-attachment-marker"}], "attachments": []}],
            "actions": [], "errors": []}
        self.path = self.root / "incoming" / (self.batch["id"] + ".json")
        workspace._atomic_json(self.path, self.batch)
        return {"batch_path": str(self.path)}

    def review(self, batch, dashboard, root):
        result = copy.deepcopy(batch)
        result["messages"][0].update(summary="grounded summary", category="通知")
        result["actions"] = [{"id": "a2", "message_id": "m2", "title": "new task", "requirement": "submit",
                              "status": "needs_confirmation", "due_at": None}]
        return result

    def queue(self):
        return jobs.request(self.root, client=self.client)["manual_collection"]

    def run_job(self):
        return worker.run_once(self.root, client=self.client, collector=self.collector, reviewer=self.reviewer)

    def test_no_request_means_no_mail_or_ai(self):
        self.assertEqual("idle", self.run_job()["status"])
        self.collector.assert_not_called()
        self.reviewer.assert_not_called()
        self.assertEqual([], self.client.writes)

    def test_claim_must_succeed_before_mail_access(self):
        self.queue()
        self.client.fail = lambda snapshot: True
        with self.assertRaises(sync.MailCommandError):
            self.run_job()
        self.collector.assert_not_called()
        self.reviewer.assert_not_called()

    def test_complete_pipeline_preserves_user_edits_and_redacts_review(self):
        old_action = copy.deepcopy(self.data["actions"][0])
        def while_reviewing(batch, dashboard, root):
            self.client.snapshot["actions"][0].update(status="done", completed_at="2026-09-09T18:00:00+08:00",
                                                      updated_at="2026-09-09T18:00:00+08:00")
            return self.review(batch, dashboard, root)
        self.reviewer.side_effect = while_reviewing
        self.queue()
        result = self.run_job()
        self.assertEqual(("success", 1, 1, 1), tuple(result[k] for k in ("status", "message_count", "new_message_count", "action_count")))
        local = workspace.load_dashboard(self.root)
        self.assertEqual("done", next(a for a in local["actions"] if a["id"] == old_action["id"])["status"])
        self.assertEqual(self.data["messages"][0]["archive_path"], next(m for m in local["messages"] if m["id"] == "m1")["archive_path"])
        redacted = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(redacted["review_content_removed"])
        self.assertNotIn("body_text", redacted["messages"][0])
        self.assertNotIn("private-review-marker", json.dumps(self.client.snapshot))
        self.assertNotIn("private-attachment-marker", json.dumps(self.client.snapshot))
        self.assertFalse((self.root / "archive").exists())
        self.assertEqual("idle", self.run_job()["status"])
        self.assertEqual(1, self.collector.call_count)

    def test_ai_failure_is_error_without_ingest_and_removes_full_text(self):
        self.queue()
        self.reviewer.side_effect = ValueError("private-ai-diagnostic")
        result = self.run_job()
        self.assertEqual(("error", "REVIEW_FAILED"), (result["status"], result["error_code"]))
        self.assertEqual(1, len(workspace.load_dashboard(self.root)["messages"]))
        self.assertNotIn("private-review-marker", self.path.read_text(encoding="utf-8"))
        self.assertNotIn("private-ai-diagnostic", json.dumps(self.client.snapshot))

    def test_sync_retry_never_collects_or_reviews_again(self):
        self.queue()
        self.client.fail = lambda snapshot: len(snapshot["messages"]) > 1
        with self.assertRaises(sync.MailCommandError):
            self.run_job()
        self.assertEqual("running", self.client.snapshot["manual_collection"]["status"])
        self.client.fail = None
        result = self.run_job()
        self.assertEqual("success", result["status"])
        self.assertEqual((1, 1), (self.collector.call_count, self.reviewer.call_count))

    def test_interrupted_owned_job_fails_without_reexecution(self):
        job = self.queue()
        cid = "b" * 32
        jobs.claim(self.root, job["request_id"], claim_id=cid, client=self.client)
        workspace._atomic_json(worker._receipt_path(self.root, job["request_id"]),
                               {"request_id": job["request_id"], "claim_id": cid, "stage": "reviewing"})
        result = self.run_job()
        self.assertEqual("WORKER_INTERRUPTED", result["error_code"])
        self.collector.assert_not_called()
        self.reviewer.assert_not_called()

    def test_another_computer_running_job_is_not_stolen(self):
        job = self.queue()
        jobs.claim(self.root, job["request_id"], claim_id="c" * 32, client=self.client)
        self.assertEqual("waiting", self.run_job()["status"])
        self.collector.assert_not_called()

    def test_crash_recovery_redacts_only_this_requests_transient_text(self):
        job = self.queue()
        self.collect(self.root, manual_request_id=job["request_id"])
        previous_path = self.path.with_name("imap-" + "8" * 32 + ".json")
        previous = copy.deepcopy(self.batch)
        previous.pop("manual_request_id")
        previous["id"] = "imap-" + "8" * 32
        workspace._atomic_json(previous_path, previous)
        cid = "d" * 32
        jobs.claim(self.root, job["request_id"], claim_id=cid, client=self.client)
        workspace._atomic_json(worker._receipt_path(self.root, job["request_id"]),
                               {"request_id": job["request_id"], "claim_id": cid, "stage": "reviewing"})
        self.assertEqual("WORKER_INTERRUPTED", self.run_job()["error_code"])
        self.assertNotIn("private-review-marker", self.path.read_text(encoding="utf-8"))
        self.assertIn("private-review-marker", previous_path.read_text(encoding="utf-8"))
        self.collector.assert_not_called()
        self.reviewer.assert_not_called()

    def test_redaction_failure_is_visible_and_retried_without_receiving(self):
        self.queue()
        with patch.object(worker, "redact_review_batch", return_value=False):
            result = self.run_job()
        self.assertEqual(("error", "LOCAL_STATE_FAILED"), (result["status"], result["error_code"]))
        self.assertIn("private-review-marker", self.path.read_text(encoding="utf-8"))
        self.assertEqual("idle", self.run_job()["status"])
        self.assertNotIn("private-review-marker", self.path.read_text(encoding="utf-8"))
        self.assertEqual((1, 1), (self.collector.call_count, self.reviewer.call_count))

    def test_owned_redaction_io_failure_is_not_treated_as_clean(self):
        job = self.queue()
        self.collect(self.root, manual_request_id=job["request_id"])
        with patch.object(worker, "redact_review_batch", side_effect=OSError("disk unavailable")):
            self.assertFalse(worker._redact_owned_review(self.root, job["request_id"], self.batch["id"]))

    def test_failed_ai_reason_survives_receipt_upload_retry(self):
        self.queue()
        self.reviewer.side_effect = ValueError("private-ai-diagnostic")
        self.client.fail = lambda snapshot: snapshot.get("manual_collection", {}).get("status") == "error"
        with self.assertRaises(sync.MailCommandError):
            self.run_job()
        self.client.fail = None
        result = self.run_job()
        self.assertEqual("REVIEW_FAILED", result["error_code"])
        self.assertEqual((1, 1), (self.collector.call_count, self.reviewer.call_count))

    def test_overlapping_local_entry_cannot_claim(self):
        self.queue()
        with worker.collection_lock(self.root):
            with self.assertRaises(sync.MailCommandError) as caught:
                self.run_job()
        self.assertEqual("collection_already_running", caught.exception.code)
        self.collector.assert_not_called()

    def test_zero_messages_can_complete_without_ai_provider(self):
        def collect_empty(root, **kwargs):
            result = self.collect(root, **kwargs)
            self.batch["messages"] = []
            workspace._atomic_json(self.path, self.batch)
            return result
        self.collector.side_effect = collect_empty
        self.reviewer.side_effect = lambda batch, *_: copy.deepcopy(batch)
        self.queue()
        result = self.run_job()
        self.assertEqual(("success", 0, 0), (result["status"], result["message_count"], result["new_message_count"]))

    def test_manual_receive_is_independent_of_filing_destination(self):
        from scripts import mail_filing_worker
        with patch("scripts.mail_manual_collect.run_once", return_value={"status": "idle"}) as receive:
            with patch.object(mail_filing_worker, "run_once", side_effect=sync.MailCommandError("filing_destination_unavailable")):
                result = mail_filing_worker.run_cycle(self.root)
        receive.assert_called_once_with(self.root)
        self.assertEqual("idle", result["manual_collection"]["status"])
        self.assertEqual("filing_destination_unavailable", result["error_code"])


if __name__ == "__main__":
    unittest.main()
