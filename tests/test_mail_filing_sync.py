import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import mail_workbench_sync as local_sync
from tests.test_mail_filing_state import AT, receipt
from tests.test_mail_private_sync import FakeResponse, FakeSession, OLD_SHA, TEST_TOKEN, contents_response, snapshot_fixture
from utils import mail_filing_state as filing
from utils import mail_private_sync as web_sync
from utils import mail_workspace


def fixture():
    data = snapshot_fixture()
    data["messages"].append({"id": "m2", "subject": "Other mail", "attachments": []})
    data["actions"].extend([dict(data["actions"][0], id="a2"),
                            dict(data["actions"][0], id="a3", message_id="m2")])
    return data


def session_for(data, *, version=OLD_SHA, put=None):
    return FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(data, sha=version)], put=put)


class FilingWebSyncTests(unittest.TestCase):
    def save(self, data, updates, *, messages=False, session=None, expected_version=OLD_SHA):
        session = session or session_for(data)
        method = web_sync.save_message_updates if messages else web_sync.save_action_updates
        result = method(updates, expected_version, secrets={}, environ={"MAIL_WORKBENCH_TOKEN": TEST_TOKEN}, session=session)
        return result, session

    def retry(self, data, ids, *, session=None, expected_version=OLD_SHA):
        session = session or session_for(data)
        result = web_sync.save_filing_requests(ids, expected_version, secrets={},
            environ={"MAIL_WORKBENCH_TOKEN": TEST_TOKEN}, session=session)
        return result, session

    def test_bulk_archived_children_queue_one_mail_request_with_one_put(self):
        data = fixture()
        before = copy.deepcopy(data)
        with patch.object(filing, "uuid4", return_value=SimpleNamespace(hex="a" * 32)) as uuid:
            result, session = self.save(data, {"a1": "archived", "a2": "archived"})
        saved = result["snapshot"]
        self.assertEqual(1, uuid.call_count)
        self.assertEqual(["get", "get", "put"], [call[0] for call in session.calls])
        self.assertEqual("pending", saved["messages"][0]["filing"]["status"])
        for action in saved["actions"][:2]:
            self.assertEqual("archived", action["status"])
            self.assertIsNone(action["completed_at"])
        self.assertEqual(before["actions"][2], saved["actions"][2])
        self.assertEqual(before["messages"][1], saved["messages"][1])
        self.assertEqual(before, data)
        uploaded = json.loads(base64.b64decode(session.calls[-1][2]["json"]["content"]))
        self.assertEqual(saved, uploaded)

    def test_unactioned_mail_archived_queues_and_same_state_does_not_requeue(self):
        data = fixture()
        data["actions"] = data["actions"][:2]
        result, _ = self.save(data, {"m2": "archived"}, messages=True)
        saved = result["snapshot"]
        self.assertEqual("archived", saved["messages"][1]["triage_status"])
        self.assertEqual("pending", saved["messages"][1]["filing"]["status"])
        second, session = self.save(saved, {"m2": "archived"}, messages=True)
        self.assertEqual(saved, second["snapshot"])
        self.assertFalse(any(call[0] == "put" for call in session.calls))

    def test_repeated_archived_action_is_noop_and_keeps_success(self):
        data = fixture()
        data["actions"][0]["status"] = "archived"
        data["messages"][0]["filing"] = receipt(status="success")
        result, session = self.save(data, {"a1": "archived"})
        self.assertEqual(data, result["snapshot"])
        self.assertFalse(any(call[0] == "put" for call in session.calls))

    def test_last_child_leaving_archived_cancels_but_remaining_child_keeps_request(self):
        data = fixture()
        data["actions"][0]["status"] = data["actions"][1]["status"] = "archived"
        data["messages"][0]["filing"] = receipt()
        result, _ = self.save(data, {"a1": "pending"})
        self.assertEqual(receipt(), result["snapshot"]["messages"][0]["filing"])
        result, _ = self.save(result["snapshot"], {"a2": "pending"})
        self.assertEqual("cancelled", result["snapshot"]["messages"][0]["filing"]["status"])

    def test_leaving_archived_keeps_completed_receipt_and_other_source_fields(self):
        data = fixture()
        data["actions"] = []
        data["messages"][0].update(triage_status="archived", triage_updated_at=AT, filing=receipt(status="success"))
        result, _ = self.save(data, {"m1": "pending"}, messages=True)
        self.assertEqual(receipt(status="success"), result["snapshot"]["messages"][0]["filing"])
        self.assertEqual(data["messages"][0]["body_text"], result["snapshot"]["messages"][0]["body_text"])

    def test_retry_changes_only_receipt_and_snapshot_time(self):
        data = fixture()
        data["actions"][0]["status"] = "archived"
        data["messages"][0]["filing"] = receipt(status="error", error_count=1, error_codes=["SOURCE_MISSING"])
        result, session = self.retry(data, ["m1"])
        saved = result["snapshot"]
        self.assertEqual("pending", saved["messages"][0]["filing"]["status"])
        self.assertNotEqual(data["messages"][0]["filing"]["request_id"], saved["messages"][0]["filing"]["request_id"])
        expected = copy.deepcopy(data)
        expected["updated_at"] = saved["updated_at"]
        expected["messages"][0]["filing"] = saved["messages"][0]["filing"]
        self.assertEqual(expected, saved)
        self.assertEqual(1, sum(call[0] == "put" for call in session.calls))

    def test_retry_rejects_any_unknown_or_unarchived_mail_before_put(self):
        data = fixture()
        data["actions"][0]["status"] = "archived"
        for ids in (["m1", "missing"], ["m1", "m2"]):
            with self.subTest(ids=ids):
                session = session_for(data)
                with self.assertRaises(web_sync.MailSyncError) as caught:
                    self.retry(data, ids, session=session)
                self.assertEqual("invalid_update", caught.exception.code)
                self.assertFalse(any(call[0] == "put" for call in session.calls))

    def test_retry_rejects_paths_and_duplicate_ids_without_network(self):
        for ids in ([], "m1", ["m1", "m1"], [{"id": "m1", "destination": "E:/private"}]):
            with self.subTest(ids=ids):
                session = FakeSession()
                with self.assertRaises(web_sync.MailSyncError) as caught:
                    self.retry(fixture(), ids, session=session)
                self.assertEqual("invalid_update", caught.exception.code)
                self.assertEqual([], session.calls)

    def test_retry_cas_conflict_never_retries_or_returns_unconfirmed_state(self):
        data = fixture()
        data["actions"][0]["status"] = "archived"
        before = copy.deepcopy(data)
        for session in (session_for(data, version="newer"), session_for(data, put=FakeResponse(409))):
            with self.subTest(after_put=session.put_response.status_code == 409):
                with self.assertRaises(web_sync.MailSyncError) as caught:
                    self.retry(data, ["m1"], session=session)
                self.assertEqual("conflict", caught.exception.code)
                self.assertLessEqual(sum(call[0] == "put" for call in session.calls), 1)
                self.assertEqual(before, data)

    def test_legacy_snapshot_and_valid_receipt_load_but_unsafe_receipt_rejected(self):
        data = fixture()
        web_sync._validate_snapshot(data)
        data["messages"][0]["filing"] = receipt()
        web_sync._validate_snapshot(data)
        data["messages"][0]["filing"]["destination"] = "E:/private"
        with self.assertRaises(web_sync.MailSyncError) as caught:
            web_sync._validate_snapshot(data)
        self.assertEqual("invalid_snapshot", caught.exception.code)


class FilingLocalSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_pull_merges_filing_without_overwriting_user_status_or_original_metadata(self):
        local, remote = fixture(), fixture()
        local["actions"][0].update(status="pending", updated_at="2026-09-09T12:00:00+08:00")
        local["messages"][0]["filing"] = receipt()
        remote["messages"][0]["filing"] = receipt(status="success", updated_at="2026-09-08T12:01:00+08:00")
        remote["messages"][0]["subject"] = "Do not overwrite local source"
        merged = local_sync.merge_remote_states(local, remote)
        self.assertEqual(remote["messages"][0]["filing"], merged["messages"][0]["filing"])
        self.assertEqual(local["messages"][0]["subject"], merged["messages"][0]["subject"])
        self.assertEqual(local["actions"][0], merged["actions"][0])

    def test_push_new_remote_request_survives_later_timestamp_on_old_local_success(self):
        local, remote = fixture(), fixture()
        local["messages"][0]["filing"] = receipt(status="success", updated_at="2026-09-10T12:00:00+08:00")
        remote["messages"][0]["filing"] = receipt(request_id="b" * 32,
            requested_at="2026-09-09T12:00:00+08:00", updated_at="2026-09-09T12:00:00+08:00")
        merged = local_sync.merge_for_push(local, remote, self.root)
        self.assertEqual(remote["messages"][0]["filing"], merged["messages"][0]["filing"])

    def test_public_snapshot_whitelists_filing_and_keeps_original_eml_local(self):
        data = fixture()
        data["messages"][0].update(raw_eml_path="archive/original.eml", raw_eml_sha256="f" * 64,
            filing=receipt(local_path="E:/private", raw_bytes="sensitive"))
        public = mail_workspace.public_snapshot(data, self.root)
        self.assertEqual(receipt(), public["messages"][0]["filing"])
        self.assertNotIn("raw_eml_path", public["messages"][0])
        self.assertNotIn("E:/private", json.dumps(public))

    def test_ingest_preserves_user_filing_and_new_actions_inherit_archived(self):
        mail_workspace.initialize(self.root, "staff@example.edu.cn")
        batch = {"schema_version": 1, "account": "staff@example.edu.cn", "kind": "sample", "id": "sample",
                 "started_at": AT, "finished_at": AT, "window": {"since": AT, "through": AT, "complete": True},
                 "messages": [{"id": "m1", "received_at": AT, "body_text": "Source", "attachments": []}], "actions": []}
        mail_workspace.ingest(self.root, batch)
        data = mail_workspace.load_dashboard(self.root)
        data["messages"][0].update(triage_status="archived", triage_updated_at=AT, filing=receipt())
        mail_workspace._atomic_json(self.root / "dashboard.json", data)
        batch["id"] = "new-extraction"
        batch["messages"][0]["filing"] = receipt(request_id="c" * 32)
        batch["actions"] = [{"id": "a1", "message_id": "m1", "title": "Action"}]
        mail_workspace.ingest(self.root, batch)
        result = mail_workspace.load_dashboard(self.root)
        self.assertEqual(receipt(), result["messages"][0]["filing"])
        self.assertEqual("archived", result["actions"][0]["status"])
        self.assertIsNone(result["actions"][0]["completed_at"])
        report = mail_workspace.generate_report(self.root, "weekly", AT)
        self.assertEqual(0, report["active_action_count"])
        self.assertEqual(0, report["completed_action_count"])

    def test_first_push_of_new_action_obeys_later_remote_archived_mail_decision(self):
        local, remote = fixture(), fixture()
        remote["actions"] = []
        remote["messages"][0].update(triage_status="archived", triage_updated_at=AT, filing=receipt())
        merged = local_sync.merge_for_push(local, remote, self.root)
        self.assertTrue(all(action["status"] == "archived" for action in merged["actions"] if action["message_id"] == "m1"))
        self.assertEqual(receipt(), merged["messages"][0]["filing"])


if __name__ == "__main__":
    unittest.main()
