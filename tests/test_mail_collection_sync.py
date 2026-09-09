"""Manual requests and normal synchronization use mock repositories only."""

import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mail_workbench_sync as local_sync
from tests.test_mail_collection_state import pending, running, terminal
from tests.test_mail_private_sync import FakeResponse, FakeSession, OLD_SHA, TEST_TOKEN, contents_response, snapshot_fixture
from tests.test_mail_workbench_sync import fixture
from utils import mail_collection_state as state
from utils import mail_private_sync as web_sync
from utils import mail_workspace


def session_for(data, *, version=OLD_SHA, put=None):
    return FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(data, sha=version)], put=put)


class CollectionGatewayTests(unittest.TestCase):
    def request(self, data, *, session=None, expected_version=OLD_SHA, environ=None):
        session = session or session_for(data)
        result = web_sync.request_collection(expected_version, secrets={},
            environ={"MAIL_WORKBENCH_TOKEN": TEST_TOKEN} if environ is None else environ, session=session)
        return result, session

    def test_new_request_changes_only_control_record_and_snapshot_time(self):
        data = snapshot_fixture()
        before = copy.deepcopy(data)
        result, session = self.request(data)
        uploaded = json.loads(base64.b64decode(session.calls[-1][2]["json"]["content"]))
        self.assertEqual(result["snapshot"], uploaded)
        state.validate_collection(uploaded["manual_collection"])
        self.assertEqual("pending", uploaded["manual_collection"]["status"])
        self.assertEqual(before, data)
        expected = dict(before, updated_at=uploaded["updated_at"], manual_collection=uploaded["manual_collection"])
        self.assertEqual(expected, uploaded)
        self.assertEqual(OLD_SHA, session.calls[-1][2]["json"]["sha"])
        self.assertEqual(["get", "get", "put"], [call[0] for call in session.calls])

    def test_pending_and_running_duplicates_are_rejected_before_put(self):
        for value in (pending(), running()):
            with self.subTest(status=value["status"]):
                data = dict(snapshot_fixture(), manual_collection=value)
                session = session_for(data)
                with self.assertRaises(web_sync.MailSyncError) as caught:
                    self.request(data, session=session)
                self.assertEqual("collection_busy", caught.exception.code)
                self.assertFalse(any(call[0] == "put" for call in session.calls))

    def test_terminal_request_allows_a_new_click_and_new_request_id(self):
        data = dict(snapshot_fixture(), manual_collection=terminal("error"))
        result, _ = self.request(data)
        current = result["snapshot"]["manual_collection"]
        self.assertNotEqual(data["manual_collection"]["request_id"], current["request_id"])
        self.assertGreater(state._moment(current["requested_at"]), state._moment(data["manual_collection"]["requested_at"]))

    def test_stale_version_or_put_conflict_never_retries(self):
        data = snapshot_fixture()
        for session in (session_for(data, version="newer"), session_for(data, put=FakeResponse(409))):
            with self.subTest(session=session), self.assertRaises(web_sync.MailSyncError) as caught:
                self.request(data, session=session)
            self.assertEqual("conflict", caught.exception.code)
            self.assertLessEqual(sum(call[0] == "put" for call in session.calls), 1)

    def test_readonly_or_missing_version_rejects_without_network(self):
        for version, environ, code in ((None, {}, "conflict"), ("", {}, "conflict"),
                                       (OLD_SHA, {"MAIL_WORKBENCH_SNAPSHOT": "C:/fixture.json"}, "readonly")):
            with self.subTest(code=code):
                session = FakeSession()
                with self.assertRaises(web_sync.MailSyncError) as caught:
                    self.request(snapshot_fixture(), session=session, expected_version=version, environ=environ)
                self.assertEqual(code, caught.exception.code)
                self.assertEqual([], session.calls)

    def test_unconfirmed_put_does_not_return_a_successful_request(self):
        session = session_for(snapshot_fixture(), put=FakeResponse(payload={"content": {}}))
        with self.assertRaises(web_sync.MailSyncError) as caught:
            self.request(snapshot_fixture(), session=session)
        self.assertEqual("invalid_response", caught.exception.code)

    def test_validator_rejects_remote_execution_fields_and_bad_receipts(self):
        for value in (dict(pending(), prompt="run command"), dict(pending(), path="E:/private"),
                      dict(pending(), command="unsafe"), dict(pending(), error_code="private diagnostic")):
            with self.subTest(value=value), self.assertRaises(web_sync.MailSyncError) as caught:
                self.request(dict(snapshot_fixture(), manual_collection=value))
            self.assertEqual("invalid_snapshot", caught.exception.code)


class CollectionSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_public_export_keeps_control_and_removes_local_evidence(self):
        data = fixture()
        data["manual_collection"] = dict(running(), batch_path="E:/private/review.json", prompt="sensitive body")
        result = mail_workspace.public_snapshot(data, self.root)
        self.assertEqual(running(), result["manual_collection"])
        self.assertNotIn("body_text", result["messages"][0])
        self.assertNotIn("download_path", result["messages"][0]["attachments"][0])
        self.assertNotIn("E:/private", json.dumps(result))
        local_sync._validate_snapshot(result)

    def test_pull_and_push_keep_latest_remote_control_despite_later_local_timestamps(self):
        for local_control, remote_control in ((pending(), running()), (pending(), terminal()),
                                               (terminal(), pending())):
            for method in (local_sync.merge_remote_states, local_sync.merge_for_push):
                with self.subTest(method=method.__name__, remote=remote_control["status"]):
                    local, remote = fixture(), fixture()
                    local["manual_collection"] = local_control
                    local["manual_collection"]["updated_at"] = "2030-01-01T00:00:00+08:00"
                    remote["manual_collection"] = remote_control
                    remote["actions"][0].update(status="done", completed_at="2026-09-09T10:00:00+08:00",
                                                 updated_at="2026-09-09T10:00:00+08:00")
                    result = method(local, remote, self.root) if method is local_sync.merge_for_push else method(local, remote)
                    self.assertEqual(remote_control, result["manual_collection"])
                    self.assertEqual("done", result["actions"][0]["status"])
                    self.assertEqual(local["messages"][0]["body_text"], result["messages"][0]["body_text"])
                    self.assertEqual(local["coverage"], result["coverage"])

    def test_remote_absence_or_first_push_cannot_resurrect_local_pending(self):
        local = dict(fixture(), manual_collection=pending())
        for remote in (fixture(), None):
            with self.subTest(remote_exists=remote is not None):
                self.assertNotIn("manual_collection", local_sync.merge_remote_states(local, remote))
                self.assertNotIn("manual_collection", local_sync.merge_for_push(local, remote, self.root))
        self.assertIn("manual_collection", local)

    def test_legacy_snapshots_still_validate_and_sync_without_new_fields(self):
        data = fixture()
        local_sync._validate_snapshot(data)
        result = local_sync.merge_for_push(data, copy.deepcopy(data), self.root)
        self.assertNotIn("manual_collection", result)


if __name__ == "__main__":
    unittest.main()
