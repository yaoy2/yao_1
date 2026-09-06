import base64
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import requests

from utils import mail_private_sync as sync


TEST_TOKEN = "test-only-mail-token"
OLD_SHA = "a" * 40
NEW_SHA = "b" * 40


def snapshot_fixture():
    return {
        "schema_version": 1,
        "account": "staff@example.edu.cn",
        "timezone": "Asia/Shanghai",
        "updated_at": "2026-09-06T08:00:00+08:00",
        "coverage": {"since": "2026-09-05", "through": "2026-09-06", "complete": True, "note": ""},
        "messages": [{"id": "m1", "subject": "材料报送", "received_at": "2026-09-06T07:00:00+08:00", "body_text": "源邮件不可由网页修改"}],
        "actions": [{
            "id": "a1", "message_id": "m1", "title": "报送材料", "requirement": "提交附件",
            "owner": "学院", "due_at": "2026-09-08", "due_text": "9月8日前", "due_basis": "explicit",
            "recipient": "教学部门", "submission_method": "邮件", "status": "pending",
            "completed_at": None, "updated_at": "2026-09-06T08:00:00+08:00",
        }],
        "runs": [{"id": "r1", "status": "success"}],
        "reports": [{"id": "report1", "summary": "邮件摘要"}],
    }


def message_snapshot_fixture():
    snapshot = snapshot_fixture()
    snapshot["messages"].append({
        "id": "m2", "subject": "学院活动信息", "received_at": "2026-09-06T07:30:00+08:00",
        "body_text": "仅供阅读的邮件正文", "attachments": [{"id": "file2", "filename": "活动介绍.pdf"}],
    })
    return snapshot


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = {} if payload is None else payload

    def json(self):
        return self.payload


def contents_response(snapshot=None, sha=OLD_SHA):
    raw = json.dumps(snapshot_fixture() if snapshot is None else snapshot, ensure_ascii=False).encode("utf-8")
    return FakeResponse(payload={"sha": sha, "encoding": "base64", "content": base64.b64encode(raw).decode("ascii")})


class FakeSession:
    def __init__(self, gets=None, put=None):
        self.gets = list(gets if gets is not None else [FakeResponse(payload={"private": True}), contents_response()])
        self.put_response = put or FakeResponse(payload={"content": {"sha": NEW_SHA}})
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.gets.pop(0)

    def put(self, url, **kwargs):
        self.calls.append(("put", url, kwargs))
        return self.put_response


class MailPrivateSyncTests(unittest.TestCase):
    def load(self, session, **kwargs):
        kwargs.setdefault("environ", {"MAIL_WORKBENCH_TOKEN": TEST_TOKEN})
        kwargs.setdefault("secrets", {})
        return sync.load_snapshot(session=session, **kwargs)

    def save(self, session, updates=None, expected_version=OLD_SHA, **kwargs):
        kwargs.setdefault("environ", {"MAIL_WORKBENCH_TOKEN": TEST_TOKEN})
        kwargs.setdefault("secrets", {})
        return sync.save_action_updates(
            {"a1": "done"} if updates is None else updates, expected_version,
            session=session, **kwargs,
        )

    def save_messages(self, session, updates=None, expected_version=OLD_SHA, **kwargs):
        kwargs.setdefault("environ", {"MAIL_WORKBENCH_TOKEN": TEST_TOKEN})
        kwargs.setdefault("secrets", {})
        return sync.save_message_updates(
            {"m2": "done"} if updates is None else updates, expected_version,
            session=session, **kwargs,
        )

    def assert_error(self, code, function, *args, **kwargs):
        with self.assertRaises(sync.MailSyncError) as caught:
            function(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)
        self.assertNotIn(TEST_TOKEN, str(caught.exception))
        self.assertNotIn("Authorization", str(caught.exception))
        return caught.exception

    def test_missing_config_fails_without_network_or_implicit_local_path(self):
        session = FakeSession()
        self.assert_error("missing_token", self.load, session, environ={})
        self.assertEqual([], session.calls)

    def test_refuses_public_or_unverified_repo_before_content_access(self):
        for metadata in ({"private": False}, {}, {"private": "true"}):
            with self.subTest(metadata=metadata):
                session = FakeSession(gets=[FakeResponse(payload=metadata)])
                self.assert_error("public_repo", self.load, session)
                self.assertEqual(1, len(session.calls))
                self.assertNotIn("/contents/", session.calls[0][1])

    def test_explicit_app_repo_is_never_a_data_target(self):
        session = FakeSession()
        self.assert_error("public_repo", self.load, session, environ={
            "MAIL_WORKBENCH_REPO": "yaoy2/yao_1", "MAIL_WORKBENCH_TOKEN": TEST_TOKEN,
        })
        self.assertEqual([], session.calls)

    def test_legacy_token_reuse_never_reuses_public_repository_or_branch(self):
        session = FakeSession()
        with patch.object(sync.github_backup_sync, "get_backup_sync_config", return_value={
            "token": TEST_TOKEN, "repo": "yaoy2/yao_1", "branch": "legacy-branch",
        }):
            self.load(session, environ={})
        self.assertEqual("https://api.github.com/repos/yaoy2/mail-workbench-data", session.calls[0][1])
        self.assertEqual({"ref": "main"}, session.calls[1][2]["params"])

    def test_nested_mail_configuration_has_precedence_and_redirects_are_disabled(self):
        session = FakeSession()
        result = self.load(session, secrets={"mail_workbench": {
            "repo": "team/private-mail", "branch": "mail-data", "token": "nested-test-token",
        }}, environ={"MAIL_WORKBENCH_TOKEN": TEST_TOKEN, "MAIL_WORKBENCH_REPO": "env/private-mail"})
        self.assertEqual("github", result["source"])
        self.assertEqual(OLD_SHA, result["version"])
        self.assertEqual("https://api.github.com/repos/team/private-mail", session.calls[0][1])
        self.assertEqual({"ref": "mail-data"}, session.calls[1][2]["params"])
        self.assertEqual("Bearer nested-test-token", session.calls[0][2]["headers"]["Authorization"])
        self.assertTrue(all(call[2]["allow_redirects"] is False for call in session.calls))

    def test_nested_legacy_token_is_supported_without_legacy_repo(self):
        session = FakeSession()
        self.load(session, environ={}, secrets={"github_backup": {"token": TEST_TOKEN, "repo": "yaoy2/yao_1"}})
        self.assertIn("/repos/yaoy2/mail-workbench-data", session.calls[0][1])
        self.assertEqual("Bearer " + TEST_TOKEN, session.calls[0][2]["headers"]["Authorization"])

    def test_authentication_and_permission_errors_are_explicit_and_sanitized(self):
        for status, code in ((401, "unauthorized"), (403, "forbidden"), (404, "repo_not_found")):
            with self.subTest(status=status):
                session = FakeSession(gets=[FakeResponse(status, {"message": TEST_TOKEN, "Authorization": TEST_TOKEN})])
                self.assert_error(code, self.load, session)
                self.assertEqual(1, len(session.calls))

    def test_snapshot_missing_and_redirect_do_not_fall_back(self):
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), FakeResponse(404)])
        self.assert_error("snapshot_not_found", self.load, session)
        session = FakeSession(gets=[FakeResponse(301, {"url": "https://example.invalid/" + TEST_TOKEN})])
        self.assert_error("remote_error", self.load, session)
        self.assertEqual(1, len(session.calls))

    def test_network_failure_never_exposes_request_exception(self):
        session = FakeSession()
        with patch.object(session, "get", side_effect=requests.ConnectionError("Authorization: " + TEST_TOKEN)):
            error = self.assert_error("network_error", self.load, session)
        self.assertTrue(error.__suppress_context__)

    def test_load_decodes_complete_snapshot_without_mutating_source(self):
        original = snapshot_fixture()
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(original)])
        self.assertEqual(original, self.load(session)["snapshot"])

    def test_explicit_local_snapshot_is_readonly_and_does_not_contact_github(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            content = json.dumps(snapshot_fixture(), ensure_ascii=False)
            path.write_text(content, encoding="utf-8")
            environment = {"MAIL_WORKBENCH_SNAPSHOT": str(path)}
            session = FakeSession()
            result = self.load(session, environ=environment)
            self.assertEqual("local_readonly", result["source"])
            self.assertIsNone(result["version"])
            self.assert_error("readonly", self.save, session, environ=environment)
            self.assertEqual(content, path.read_text(encoding="utf-8"))
            self.assertEqual([], session.calls)

    def test_missing_local_path_is_not_replaced_with_remote_data(self):
        with tempfile.TemporaryDirectory() as directory:
            session = FakeSession()
            self.assert_error("local_read_error", self.load, session, environ={
                "MAIL_WORKBENCH_SNAPSHOT": str(Path(directory) / "missing.json"),
                "MAIL_WORKBENCH_TOKEN": TEST_TOKEN,
            })
            self.assertEqual([], session.calls)

    def test_save_checks_sha_and_changes_only_status_and_managed_timestamps(self):
        source = snapshot_fixture()
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
        result = self.save(session)
        method, url, kwargs = session.calls[-1]
        self.assertEqual("put", method)
        self.assertTrue(url.endswith("/contents/dashboard.json"))
        self.assertEqual(OLD_SHA, kwargs["json"]["sha"])
        self.assertEqual("main", kwargs["json"]["branch"])
        saved = json.loads(base64.b64decode(kwargs["json"]["content"]))
        self.assertEqual("done", saved["actions"][0]["status"])
        completed = datetime.fromisoformat(saved["actions"][0]["completed_at"])
        self.assertEqual(timedelta(hours=8), completed.utcoffset())
        self.assertEqual(saved["updated_at"], saved["actions"][0]["updated_at"])
        self.assertEqual(saved["updated_at"], saved["actions"][0]["completed_at"])
        expected = copy.deepcopy(source)
        expected["updated_at"] = saved["updated_at"]
        for key in ("status", "updated_at", "completed_at"):
            expected["actions"][0][key] = saved["actions"][0][key]
        self.assertEqual(expected, saved)
        self.assertEqual(source, snapshot_fixture())
        self.assertEqual({"snapshot": saved, "version": NEW_SHA, "source": "github"}, result)

    def test_stale_or_missing_version_is_never_overwritten(self):
        session = FakeSession()
        self.assert_error("conflict", self.save, session, expected_version="older-sha")
        self.assertEqual(["get", "get"], [call[0] for call in session.calls])
        for version in (None, ""):
            with self.subTest(version=version):
                session = FakeSession()
                self.assert_error("conflict", self.save, session, expected_version=version)
                self.assertEqual([], session.calls)

    def test_put_conflict_is_not_retried_and_never_returns_unconfirmed_snapshot(self):
        session = FakeSession(put=FakeResponse(409, {"message": TEST_TOKEN}))
        self.assert_error("conflict", self.save, session)
        self.assertEqual(["get", "get", "put"], [call[0] for call in session.calls])

    def test_write_permission_failure_is_explicit(self):
        session = FakeSession(put=FakeResponse(403, {"message": TEST_TOKEN}))
        self.assert_error("forbidden", self.save, session)

    def test_missing_write_sha_requires_refresh_instead_of_claiming_success(self):
        session = FakeSession(put=FakeResponse(payload={"content": {}}))
        self.assert_error("invalid_response", self.save, session)

    def test_web_cannot_modify_source_fields_or_managed_timestamps(self):
        for field in ("body", "body_text", "title", "due_at", "completed_at", "updated_at", "messages"):
            with self.subTest(field=field):
                session = FakeSession()
                self.assert_error("invalid_update", self.save, session, updates=[{"id": "a1", "status": "done", field: "tampered"}])
                self.assertEqual([], session.calls)
        session = FakeSession()
        self.assert_error("invalid_update", self.save, session, updates={"a1": {"status": "done", "body": "tampered"}})
        self.assertEqual([], session.calls)

    def test_rejects_unknown_invalid_and_duplicate_actions(self):
        session = FakeSession()
        self.assert_error("invalid_update", self.save, session, updates={"unknown": "done"})
        self.assertNotIn("put", [call[0] for call in session.calls])
        for updates in ({"a1": "archived"}, [{"id": "a1", "status": "done"}, {"id": "a1", "status": "pending"}]):
            with self.subTest(updates=updates):
                session = FakeSession()
                self.assert_error("invalid_update", self.save, session, updates=updates)
                self.assertEqual([], session.calls)

    def test_unchanged_status_is_noop_and_keeps_completion_time(self):
        source = snapshot_fixture()
        source["actions"][0].update(status="done", completed_at="2026-09-06T08:00:00+08:00")
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
        result = self.save(session)
        self.assertEqual(source, result["snapshot"])
        self.assertEqual(OLD_SHA, result["version"])
        self.assertNotIn("put", [call[0] for call in session.calls])

    def test_reopened_action_clears_completion_timestamp(self):
        source = snapshot_fixture()
        source["actions"][0].update(status="done", completed_at="2026-09-06T08:00:00+08:00")
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
        result = self.save(session, updates=[{"id": "a1", "status": "in_progress"}])
        self.assertIsNone(result["snapshot"]["actions"][0]["completed_at"])

    def test_no_action_and_out_of_scope_save_without_completion_or_source_changes(self):
        for state in ("no_action", "out_of_scope"):
            with self.subTest(state=state):
                source = snapshot_fixture()
                source["actions"][0].update(status="done", completed_at="2026-09-06T08:00:00+08:00")
                source["reports"][0]["action_ids"] = ["a1"]
                session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
                saved = self.save(session, updates={"a1": state})["snapshot"]
                self.assertEqual(state, saved["actions"][0]["status"])
                self.assertIsNone(saved["actions"][0]["completed_at"])
                expected = copy.deepcopy(source)
                expected["updated_at"] = saved["updated_at"]
                for field in ("status", "updated_at", "completed_at"):
                    expected["actions"][0][field] = saved["actions"][0][field]
                self.assertEqual(expected, saved)

    def test_all_archived_states_can_restore_to_active_states(self):
        for before in ("done", "no_action", "out_of_scope"):
            for after in ("pending", "needs_confirmation", "in_progress"):
                with self.subTest(before=before, after=after):
                    source = snapshot_fixture()
                    source["actions"][0].update(status=before, completed_at="2026-09-06T08:00:00+08:00")
                    session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
                    saved = self.save(session, updates={"a1": after})["snapshot"]
                    self.assertEqual(after, saved["actions"][0]["status"])
                    self.assertIsNone(saved["actions"][0]["completed_at"])
                    self.assertEqual(saved["updated_at"], saved["actions"][0]["updated_at"])

    def test_report_action_ids_are_optional_but_validated_when_present(self):
        legacy = snapshot_fixture()
        self.assertEqual(legacy, sync._validate_snapshot(legacy))
        for identifiers in ([], ["a1"], ["historical-action-no-longer-present"]):
            source = snapshot_fixture()
            source["reports"][0]["action_ids"] = identifiers
            self.assertEqual(source, sync._validate_snapshot(source))
        for identifiers in (None, "a1", ["a1", "a1"], [""], [" "], [[]]):
            with self.subTest(identifiers=identifiers):
                source = snapshot_fixture()
                source["reports"][0]["action_ids"] = identifiers
                self.assert_error("invalid_snapshot", sync._validate_snapshot, source)

    def test_timezone_and_timestamps_are_validated_but_date_only_deadlines_preserved(self):
        for zone in ("CST", "UTC+8", "Not/AZone", " Asia/Shanghai", None):
            with self.subTest(zone=zone):
                source = snapshot_fixture()
                source["timezone"] = zone
                session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
                self.assert_error("invalid_snapshot", self.load, session)
        for field, value in (("due_at", "2026-09-08T17:00:00"), ("due_at", "2026-02-30"), ("updated_at", "2026-09-06T08:00:00")):
            with self.subTest(field=field, value=value):
                source = snapshot_fixture()
                source["actions"][0][field] = value
                session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
                self.assert_error("invalid_snapshot", self.load, session)
        session = FakeSession()
        self.assertEqual("2026-09-08", self.load(session)["snapshot"]["actions"][0]["due_at"])

    def test_save_uses_snapshot_timezone(self):
        source = snapshot_fixture()
        source["timezone"] = "UTC"
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
        result = self.save(session)
        self.assertEqual(timedelta(0), datetime.fromisoformat(result["snapshot"]["updated_at"]).utcoffset())

    def test_message_save_supports_all_six_states_and_changes_only_triage_fields(self):
        states = {"needs_confirmation", "pending", "in_progress", "done", "no_action", "out_of_scope"}
        self.assertEqual(states, set(sync.ALLOWED_STATUSES))
        for state in states:
            with self.subTest(state=state):
                source = message_snapshot_fixture()
                session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
                result = self.save_messages(session, updates={"m2": state})
                method, url, kwargs = session.calls[-1]
                self.assertEqual("put", method)
                self.assertTrue(url.endswith("/contents/dashboard.json"))
                self.assertEqual(OLD_SHA, kwargs["json"]["sha"])
                self.assertEqual("main", kwargs["json"]["branch"])
                saved = json.loads(base64.b64decode(kwargs["json"]["content"]))
                message = saved["messages"][1]
                self.assertEqual(state, message["triage_status"])
                self.assertEqual(saved["updated_at"], message["triage_updated_at"])
                self.assertEqual(timedelta(hours=8), datetime.fromisoformat(message["triage_updated_at"]).utcoffset())
                self.assertNotIn("completed_at", message)
                expected = copy.deepcopy(source)
                expected["updated_at"] = saved["updated_at"]
                expected["messages"][1].update(triage_status=state, triage_updated_at=saved["updated_at"])
                self.assertEqual(expected, saved)
                self.assertEqual(source, message_snapshot_fixture())
                self.assertEqual({"snapshot": saved, "version": NEW_SHA, "source": "github"}, result)
                self.assertTrue(all(call[2]["allow_redirects"] is False for call in session.calls))

    def test_message_save_accepts_list_and_restores_an_archived_message_without_action(self):
        source = message_snapshot_fixture()
        source["messages"][1].update(triage_status="out_of_scope", triage_updated_at="2026-09-05T12:00:00+08:00")
        source["timezone"] = "UTC"
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
        saved = self.save_messages(session, updates=[{"id": "m2", "status": "pending"}])["snapshot"]
        self.assertEqual("pending", saved["messages"][1]["triage_status"])
        self.assertEqual(timedelta(0), datetime.fromisoformat(saved["messages"][1]["triage_updated_at"]).utcoffset())
        self.assertEqual(source["actions"], saved["actions"])
        self.assertNotIn("completed_at", saved["messages"][1])

    def test_message_save_readonly_does_not_read_or_write_the_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            content = json.dumps(message_snapshot_fixture(), ensure_ascii=False)
            path.write_text(content, encoding="utf-8")
            session = FakeSession()
            self.assert_error("readonly", self.save_messages, session, environ={"MAIL_WORKBENCH_SNAPSHOT": str(path)})
            self.assertEqual(content, path.read_text(encoding="utf-8"))
            self.assertEqual([], session.calls)

    def test_message_save_rejects_unknown_or_action_linked_messages_atomically(self):
        for message_id in ("unknown", "m1"):
            with self.subTest(message_id=message_id):
                source = message_snapshot_fixture()
                session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
                self.assert_error("invalid_update", self.save_messages, session, updates={"m2": "done", message_id: "pending"})
                self.assertEqual(["get", "get"], [call[0] for call in session.calls])
                self.assertEqual(source, message_snapshot_fixture())

    def test_message_save_rejects_extra_fields_invalid_values_and_duplicate_updates(self):
        invalid_updates = [
            {"m2": "archived"}, {"m2": {"status": "done"}}, {"": "done"},
            [{"id": "m2", "status": "done"}, {"id": "m2", "status": "pending"}],
        ]
        for field in ("subject", "body_text", "attachments", "message_id", "triage_status", "triage_updated_at", "completed_at", "updated_at", "actions"):
            invalid_updates.append([{"id": "m2", "status": "done", field: "tampered"}])
        for updates in invalid_updates:
            with self.subTest(updates=updates):
                session = FakeSession()
                self.assert_error("invalid_update", self.save_messages, session, updates=updates)
                self.assertEqual([], session.calls)

    def test_message_save_requires_private_repository_before_content_access(self):
        for metadata in ({"private": False}, {}, {"private": "true"}):
            with self.subTest(metadata=metadata):
                session = FakeSession(gets=[FakeResponse(payload=metadata)])
                self.assert_error("public_repo", self.save_messages, session)
                self.assertEqual(1, len(session.calls))
                self.assertNotIn("/contents/", session.calls[0][1])
        session = FakeSession()
        self.assert_error("public_repo", self.save_messages, session, environ={
            "MAIL_WORKBENCH_REPO": "yaoy2/yao_1", "MAIL_WORKBENCH_TOKEN": TEST_TOKEN,
        })
        self.assertEqual([], session.calls)

    def test_message_save_stale_or_missing_version_never_overwrites(self):
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(message_snapshot_fixture())])
        self.assert_error("conflict", self.save_messages, session, expected_version="older-sha")
        self.assertEqual(["get", "get"], [call[0] for call in session.calls])
        for version in (None, ""):
            with self.subTest(version=version):
                session = FakeSession()
                self.assert_error("conflict", self.save_messages, session, expected_version=version)
                self.assertEqual([], session.calls)

    def test_message_save_put_conflict_is_not_retried(self):
        session = FakeSession(
            gets=[FakeResponse(payload={"private": True}), contents_response(message_snapshot_fixture())],
            put=FakeResponse(409, {"message": TEST_TOKEN}),
        )
        self.assert_error("conflict", self.save_messages, session)
        self.assertEqual(["get", "get", "put"], [call[0] for call in session.calls])

    def test_message_save_permission_or_unconfirmed_write_never_reports_success(self):
        for response, code in (
            (FakeResponse(403, {"message": TEST_TOKEN}), "forbidden"),
            (FakeResponse(payload={"content": {}}), "invalid_response"),
        ):
            with self.subTest(code=code):
                session = FakeSession(
                    gets=[FakeResponse(payload={"private": True}), contents_response(message_snapshot_fixture())], put=response,
                )
                self.assert_error(code, self.save_messages, session)
                self.assertEqual(["get", "get", "put"], [call[0] for call in session.calls])

    def test_unchanged_message_triage_is_noop_and_preserves_original_time(self):
        source = message_snapshot_fixture()
        source["messages"][1].update(triage_status="done", triage_updated_at="2026-09-05T12:00:00+08:00")
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
        result = self.save_messages(session)
        self.assertEqual({"snapshot": source, "version": OLD_SHA, "source": "github"}, result)
        self.assertEqual(["get", "get"], [call[0] for call in session.calls])

    def test_message_triage_fields_are_optional_for_legacy_snapshots_and_accept_all_states(self):
        source = message_snapshot_fixture()
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
        self.assertEqual(source, self.load(session)["snapshot"])
        for state in sync.ALLOWED_STATUSES:
            with self.subTest(state=state):
                source = message_snapshot_fixture()
                source["messages"][1].update(triage_status=state, triage_updated_at="2026-09-05T12:00:00Z")
                self.assertEqual(source, sync._validate_snapshot(source))

    def test_message_triage_fields_require_a_valid_state_and_nonempty_zoned_timestamp_together(self):
        invalid_fields = [
            {"triage_status": "done"}, {"triage_updated_at": "2026-09-05T12:00:00+08:00"},
        ]
        invalid_fields.extend({"triage_status": state, "triage_updated_at": "2026-09-05T12:00:00+08:00"}
                              for state in (None, "", "archived", [], True))
        invalid_fields.extend({"triage_status": "done", "triage_updated_at": timestamp}
                              for timestamp in (None, "", " ", "2026-09-05", "2026-09-05T12:00:00", "2026-02-30T12:00:00+08:00", 123, []))
        for fields in invalid_fields:
            with self.subTest(fields=fields):
                source = message_snapshot_fixture()
                source["messages"][1].update(fields)
                self.assert_error("invalid_snapshot", sync._validate_snapshot, source)

    def test_message_updates_cannot_silently_target_missing_or_duplicate_message_ids(self):
        for identifier in (None, "", " ", [], "m1"):
            with self.subTest(identifier=identifier):
                source = message_snapshot_fixture()
                source["messages"][1]["id"] = identifier
                session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
                self.assert_error("invalid_snapshot", self.save_messages, session)
                self.assertEqual(["get", "get"], [call[0] for call in session.calls])

    def test_invalid_schema_or_malformed_response_fails_cleanly(self):
        for modify in (
            lambda data: data.update(schema_version=True),
            lambda data: data.update(messages={}),
            lambda data: data["actions"].append(copy.deepcopy(data["actions"][0])),
            lambda data: data["actions"][0].update(status=[]),
        ):
            source = snapshot_fixture()
            modify(source)
            session = FakeSession(gets=[FakeResponse(payload={"private": True}), contents_response(source)])
            self.assert_error("invalid_snapshot", self.load, session)
        session = FakeSession(gets=[FakeResponse(payload={"private": True}), FakeResponse(payload={
            "sha": OLD_SHA, "encoding": "base64", "content": "%%%" + TEST_TOKEN,
        })])
        self.assert_error("invalid_response", self.load, session)


if __name__ == "__main__":
    unittest.main()
