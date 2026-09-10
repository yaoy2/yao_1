import base64
import copy
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from scripts import mail_workbench_sync as sync
from utils import mail_workspace


OLD_SHA = "a" * 40
NEW_SHA = "b" * 40
PRIVATE_MARKER = "private-test-mail-body-do-not-log"
TEST_TOKEN = "test-only-mail-token"


def fixture():
    return {
        "schema_version": 1, "account": "staff@example.edu.cn", "timezone": "Asia/Shanghai",
        "updated_at": "2026-09-06T10:00:00+08:00",
        "coverage": {"since": "2026-09-05T00:00:00+08:00", "through": "2026-09-05T23:00:00+08:00", "complete": False, "note": "等待补采"},
        "messages": [{
            "id": "m1", "received_at": "2026-09-05T18:00:00+08:00", "sender": "教务部门", "subject": "本地材料报送",
            "folder": "inbox", "category": "报送", "summary": "提交材料", "source_url": "https://mail.nsu.edu.cn/owa/",
            "archive_path": "archive/2026-09-05/message.json", "body_text": PRIVATE_MARKER,
            "attachments": [{"id": "f1", "name": "材料.xlsx", "path": "archive/2026-09-05/材料.xlsx",
                             "status": "success", "size": 5, "sha256": "c" * 64, "error": "",
                             "download_path": "C:/private-download.xlsx"}],
        }],
        "actions": [{
            "id": "a1", "message_id": "m1", "title": "本地事项名称", "requirement": "提交材料", "owner": "学院",
            "due_at": "2026-09-08", "due_text": "9月8日前", "due_basis": "explicit", "recipient": "教务部门",
            "submission_method": "邮件", "status": "pending", "updated_at": "2026-09-06T08:00:00+08:00", "completed_at": None,
        }],
        "runs": [{"id": "r1", "kind": "sample", "started_at": "2026-09-06T07:00:00+08:00", "finished_at": "2026-09-06T08:00:00+08:00",
                  "status": "partial", "message_count": 1, "attachment_count": 1, "errors": []}],
        "reports": [{"id": "p1", "kind": "daily", "date": "2026-09-06", "generated_at": "2026-09-06T08:00:00+08:00",
                     "period_start": "2026-09-05T00:00:00+08:00", "period_end": "2026-09-05T23:00:00+08:00",
                     "title": "本地简报", "markdown": "摘要内容"}],
    }


def http_result(status=200, payload=None):
    return Mock(status_code=status, json=Mock(return_value={} if payload is None else payload))


def repo_response(private=True, full_name=sync.DEFAULT_REPO):
    return http_result(payload={"private": private, "full_name": full_name})


def content_response(data=None, sha=OLD_SHA):
    content = base64.b64encode(json.dumps(fixture() if data is None else data, ensure_ascii=False).encode("utf-8")).decode("ascii")
    return http_result(payload={"sha": sha, "encoding": "base64", "content": content})


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class MailWorkbenchSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dashboard = self.root / "dashboard.json"
        self.original = fixture()
        self.write_local(self.original)

    def write_local(self, data):
        self.dashboard.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def local(self):
        return json.loads(self.dashboard.read_text(encoding="utf-8"))

    def sync(self, command, session, **kwargs):
        kwargs.setdefault("environ", {"MAIL_WORKBENCH_TOKEN": TEST_TOKEN})
        kwargs.setdefault("secrets", {})
        return sync.synchronize(self.root, command, session=session, **kwargs)

    def assert_code(self, code, command, session, **kwargs):
        with self.assertRaises(sync.MailCommandError) as caught:
            self.sync(command, session, **kwargs)
        self.assertEqual(code, caught.exception.code)
        self.assertNotIn(PRIVATE_MARKER, str(caught.exception))
        self.assertNotIn("Authorization", str(caught.exception))
        return caught.exception

    def test_private_repo_checked_before_contents_and_public_repo_is_rejected(self):
        for private in (False, None, "true"):
            with self.subTest(private=private):
                session = FakeSession([repo_response(private)])
                self.assert_code("public_repo_forbidden", "push", session)
                self.assertEqual(1, len(session.calls))
                self.assertEqual("https://api.github.com/repos/" + sync.DEFAULT_REPO, session.calls[0][1])
                self.assertEqual(self.original, self.local())
        session = FakeSession([])
        self.assert_code("public_repo_forbidden", "status", session, repo="yaoy2/yao_1")
        self.assertEqual([], session.calls)

    def test_transferred_repository_is_not_silently_used(self):
        session = FakeSession([repo_response(full_name="other/private-repo")])
        self.assert_code("repository_mismatch", "status", session)
        self.assertEqual(1, len(session.calls))

    def test_first_empty_pull_records_version_without_changing_dashboard(self):
        original_bytes = self.dashboard.read_bytes()
        session = FakeSession([repo_response(), http_result(404)])
        result = self.sync("pull", session)
        self.assertEqual("empty", result["status"])
        self.assertIsNone(result["version"])
        self.assertEqual(original_bytes, self.dashboard.read_bytes())
        state = json.loads((self.root / sync.SYNC_STATE_PATH).read_text(encoding="utf-8"))
        self.assertEqual("pull", state["operation"])
        self.assertIsNone(state["version"])

    def test_pull_changes_only_matching_action_statuses_and_preserves_local_sources(self):
        remote = fixture()
        remote["actions"][0].update(status="done", updated_at="2026-09-06T09:00:00+08:00", completed_at="2026-09-06T09:00:00+08:00", title="云端不能覆盖事项名称")
        remote["messages"][0]["subject"] = "云端不能覆盖正文与元数据"
        remote["actions"].append({**remote["actions"][0], "id": "remote-only"})
        session = FakeSession([repo_response(), content_response(remote)])
        result = self.sync("pull", session)
        actual = self.local()
        expected = copy.deepcopy(self.original)
        for key in sync.STATUS_FIELDS:
            expected["actions"][0][key] = remote["actions"][0][key]
        expected["updated_at"] = actual["updated_at"]
        self.assertEqual(expected, actual)
        self.assertEqual("pulled", result["status"])
        self.assertEqual(OLD_SHA, result["version"])
        self.assertEqual(1, len(actual["actions"]))
        self.assertEqual(self.original["coverage"], actual["coverage"])
        self.assertEqual(2, len(session.calls))

    def test_older_remote_action_never_reopens_newer_local_completion(self):
        local = fixture()
        local["actions"][0].update(status="done", updated_at="2026-09-06T12:00:00+08:00", completed_at="2026-09-06T12:00:00+08:00")
        self.write_local(local)
        session = FakeSession([repo_response(), content_response()])
        self.sync("pull", session)
        self.assertEqual(local, self.local())

    def test_legacy_snapshots_do_not_gain_empty_message_triage_fields(self):
        before = self.dashboard.read_bytes()
        self.sync("pull", FakeSession([repo_response(), content_response()]))
        self.assertEqual(before, self.dashboard.read_bytes())
        session = FakeSession([repo_response(), content_response(), http_result(payload={"content": {"sha": NEW_SHA}})])
        self.sync("push", session)
        payload = session.calls[-1][2]["json"]
        uploaded = json.loads(base64.b64decode(payload["content"]))
        for snapshot in (self.local(), uploaded):
            self.assertEqual(1, snapshot["schema_version"])
            self.assertNotIn("triage_status", snapshot["messages"][0])
            self.assertNotIn("triage_updated_at", snapshot["messages"][0])

    def test_pull_merges_only_matching_message_triage_and_action_state(self):
        remote = fixture()
        remote["messages"][0].update(
            triage_status="out_of_scope", triage_updated_at="2026-09-06T09:00:00+08:00",
            subject="云端主题不可覆盖", summary="云端摘要不可覆盖", body_text="云端正文不可覆盖",
            received_at="2026-09-06T08:00:00+08:00", arbitrary_remote_field=PRIVATE_MARKER,
        )
        remote["messages"][0]["attachments"][0]["name"] = "云端附件不可覆盖.xlsx"
        remote["messages"][0]["attachments"].append({
            **remote["messages"][0]["attachments"][0], "id": "remote-file", "name": "云端附件不可导入.xlsx",
        })
        remote["messages"].append({**copy.deepcopy(remote["messages"][0]), "id": "remote-message"})
        remote["actions"][0].update(
            status="done", updated_at="2026-09-06T09:00:00+08:00", completed_at="2026-09-06T09:00:00+08:00",
        )
        remote["actions"].append({**remote["actions"][0], "id": "remote-action", "message_id": "remote-message"})
        self.sync("pull", FakeSession([repo_response(), content_response(remote)]))
        actual = self.local()
        expected = copy.deepcopy(self.original)
        expected["messages"][0].update(
            triage_status="out_of_scope", triage_updated_at="2026-09-06T09:00:00+08:00",
        )
        for key in sync.STATUS_FIELDS:
            expected["actions"][0][key] = remote["actions"][0][key]
        expected["updated_at"] = actual["updated_at"]
        self.assertEqual(expected, actual)

    def test_message_triage_uses_its_own_timestamp_for_pull_and_push(self):
        cases = (
            ("2026-09-06T11:00:00+08:00", "2026-09-06T10:00:00+08:00", "pending"),
            ("2026-09-06T10:00:00+08:00", "2026-09-06T11:00:00+08:00", "done"),
            ("2026-09-06T10:00:00+08:00", "2026-09-06T10:00:00+08:00", "done"),
        )
        for local_time, remote_time, expected_status in cases:
            with self.subTest(local_time=local_time, remote_time=remote_time):
                local, remote = fixture(), fixture()
                local["messages"][0].update(triage_status="pending", triage_updated_at=local_time)
                remote["messages"][0].update(triage_status="done", triage_updated_at=remote_time)
                # Deliberately make snapshot and receipt chronology disagree
                # with the human decision version in both directions.
                older, newer = (local, remote) if expected_status == "pending" else (remote, local)
                older["updated_at"] = "2026-09-06T07:00:00+08:00"
                older["messages"][0]["received_at"] = "2026-09-04T07:00:00+08:00"
                newer["updated_at"] = "2026-09-06T20:00:00+08:00"
                newer["messages"][0]["received_at"] = "2026-09-06T19:00:00+08:00"
                expected_time = local_time if expected_status == "pending" else remote_time
                local_before, remote_before = copy.deepcopy(local), copy.deepcopy(remote)
                for merged in (sync.merge_remote_states(local, remote), sync.merge_for_push(local, remote, self.root)):
                    self.assertEqual(expected_status, merged["messages"][0]["triage_status"])
                    self.assertEqual(expected_time, merged["messages"][0]["triage_updated_at"])
                    self.assertEqual(local["messages"][0]["received_at"], merged["messages"][0]["received_at"])
                    self.assertEqual(self.original["actions"], merged["actions"])
                self.assertEqual(local_before, local)
                self.assertEqual(remote_before, remote)

    def test_missing_message_triage_cannot_erase_an_explicit_decision(self):
        for decision_side in ("local", "remote"):
            with self.subTest(decision_side=decision_side):
                local, remote = fixture(), fixture()
                decision = local if decision_side == "local" else remote
                legacy = remote if decision_side == "local" else local
                decision["messages"][0].update(
                    triage_status="no_action", triage_updated_at="2026-09-06T09:00:00+08:00",
                )
                legacy["updated_at"] = "2026-09-06T23:00:00+08:00"
                legacy["messages"][0]["received_at"] = "2026-09-06T22:00:00+08:00"
                for merged in (sync.merge_remote_states(local, remote), sync.merge_for_push(local, remote, self.root)):
                    self.assertEqual("no_action", merged["messages"][0]["triage_status"])
                    self.assertEqual("2026-09-06T09:00:00+08:00", merged["messages"][0]["triage_updated_at"])

    def test_push_retains_remote_only_message_triage_and_exports_only_allowed_fields(self):
        local, remote = fixture(), fixture()
        local["messages"][0].update(
            triage_status="pending", triage_updated_at="2026-09-06T09:00:00+08:00",
            arbitrary_local_field=PRIVATE_MARKER,
        )
        remote["messages"][0].update(
            triage_status="done", triage_updated_at="2026-09-06T11:00:00+08:00",
            subject="云端旧主题", arbitrary_remote_field=PRIVATE_MARKER,
        )
        remote["messages"].append({
            **copy.deepcopy(remote["messages"][0]), "id": "remote-message", "triage_status": "out_of_scope",
        })
        self.write_local(local)
        session = FakeSession([repo_response(), content_response(remote), http_result(payload={"content": {"sha": NEW_SHA}})])
        result = self.sync("push", session)
        payload = session.calls[-1][2]["json"]
        uploaded_bytes = base64.b64decode(payload["content"])
        uploaded = json.loads(uploaded_bytes)
        messages = {message["id"]: message for message in uploaded["messages"]}
        self.assertEqual({"m1", "remote-message"}, set(messages))
        self.assertEqual("done", messages["m1"]["triage_status"])
        self.assertEqual("2026-09-06T11:00:00+08:00", messages["m1"]["triage_updated_at"])
        self.assertEqual("本地材料报送", messages["m1"]["subject"])
        self.assertEqual("out_of_scope", messages["remote-message"]["triage_status"])
        self.assertEqual("2026-09-06T11:00:00+08:00", messages["remote-message"]["triage_updated_at"])
        self.assertNotIn(PRIVATE_MARKER, uploaded_bytes.decode("utf-8"))
        for message in messages.values():
            self.assertNotIn("body_text", message)
            self.assertNotIn("arbitrary_local_field", message)
            self.assertNotIn("arbitrary_remote_field", message)
            for attachment in message["attachments"]:
                self.assertNotIn("download_path", attachment)
        saved = {message["id"]: message for message in self.local()["messages"]}
        self.assertEqual(PRIVATE_MARKER, saved["m1"]["body_text"])
        self.assertNotIn("body_text", saved["remote-message"])
        self.assertEqual("done", saved["m1"]["triage_status"])
        self.assertEqual(self.original["actions"], self.local()["actions"])
        self.assertEqual(1, result["action_count"])

    def test_message_done_does_not_create_or_complete_actions_in_weekly_report(self):
        for action_status in (None, "pending", "done"):
            with self.subTest(action_status=action_status):
                local, remote = fixture(), fixture()
                if action_status is None:
                    local["actions"] = []
                    remote["actions"] = []
                elif action_status == "done":
                    for snapshot in (local, remote):
                        snapshot["actions"][0].update(
                            status="done", updated_at="2026-09-06T08:00:00+08:00",
                            completed_at="2026-09-06T08:00:00+08:00",
                        )
                remote["messages"][0].update(
                    triage_status="done", triage_updated_at="2026-09-06T09:00:00+08:00",
                )
                self.write_local(local)
                result = self.sync("pull", FakeSession([repo_response(), content_response(remote)]))
                self.assertEqual("done", self.local()["messages"][0]["triage_status"])
                self.assertEqual(local["actions"], self.local()["actions"])
                self.assertEqual(int(action_status is not None), result["action_count"])
                report = mail_workspace.generate_report(self.root, "weekly", "2026-09-06T23:00:00+08:00")
                self.assertEqual(int(action_status == "done"), report["completed_action_count"])
                self.assertEqual(local["actions"], self.local()["actions"])

    def test_web_completion_survives_later_ingestion_of_changed_requirements(self):
        # The webpage edits the action after our pull, while a later collection
        # changes only its requirement text. Collection time is not a new user
        # status version and must not reopen the completed task.
        self.sync("pull", FakeSession([repo_response(), content_response()]))
        remote = fixture()
        remote["actions"][0].update(status="done", updated_at="2026-09-06T09:30:00+08:00",
                                      completed_at="2026-09-06T09:30:00+08:00")
        mail_workspace.ingest(self.root, {
            "schema_version": 1, "account": self.original["account"], "kind": "sample", "id": "metadata-change",
            "started_at": "2026-09-06T19:59:00+08:00", "finished_at": "2026-09-06T20:00:00+08:00",
            "window": {"since": "2026-09-05T00:00:00+08:00", "through": "2026-09-06T20:00:00+08:00", "complete": False},
            "messages": [], "actions": [{"id": "a1", "message_id": "m1", "requirement": "改为提交修订版材料"}],
        })
        self.assertEqual("2026-09-06T08:00:00+08:00", self.local()["actions"][0]["updated_at"])
        session = FakeSession([repo_response(), content_response(remote), http_result(payload={"content": {"sha": NEW_SHA}})])
        self.sync("push", session)
        action = self.local()["actions"][0]
        self.assertEqual("done", action["status"])
        self.assertEqual("2026-09-06T09:30:00+08:00", action["completed_at"])
        self.assertEqual("改为提交修订版材料", action["requirement"])
        self.assertEqual(self.original["coverage"], self.local()["coverage"])

    def test_push_merges_remote_union_and_keeps_remote_action_state_on_tie(self):
        remote = fixture()
        remote["actions"][0].update(status="done", completed_at="2026-09-06T08:00:00+08:00", title="云端旧标题")
        remote["messages"][0]["subject"] = "云端旧主题"
        remote["messages"].append({**copy.deepcopy(remote["messages"][0]), "id": "m2"})
        remote["actions"].append({**copy.deepcopy(remote["actions"][0]), "id": "a2", "message_id": "m2"})
        remote["runs"].append({**remote["runs"][0], "id": "r2"})
        remote["reports"].append({**remote["reports"][0], "id": "p2"})
        remote["coverage"].update(through="2026-10-01T00:00:00+08:00", complete=True)
        session = FakeSession([repo_response(), content_response(remote), http_result(payload={"content": {"sha": NEW_SHA}})])
        result = self.sync("push", session)
        method, url, kwargs = session.calls[-1]
        self.assertEqual("PUT", method)
        self.assertEqual(f"https://api.github.com/repos/{sync.DEFAULT_REPO}/contents/dashboard.json", url)
        payload = kwargs["json"]
        self.assertEqual(OLD_SHA, payload["sha"])
        uploaded_bytes = base64.b64decode(payload["content"])
        uploaded = json.loads(uploaded_bytes)
        self.assertNotIn(PRIVATE_MARKER, uploaded_bytes.decode("utf-8"))
        self.assertNotIn("download_path", uploaded_bytes.decode("utf-8"))
        self.assertNotIn("body_text", uploaded_bytes.decode("utf-8"))
        for name in sync.COLLECTIONS:
            self.assertEqual(2, len(uploaded[name]))
        self.assertEqual("done", uploaded["actions"][0]["status"])
        self.assertEqual("本地事项名称", uploaded["actions"][0]["title"])
        self.assertEqual("本地材料报送", uploaded["messages"][0]["subject"])
        self.assertEqual(self.original["coverage"], uploaded["coverage"])
        self.assertEqual("done", self.local()["actions"][0]["status"])
        self.assertEqual(PRIVATE_MARKER, self.local()["messages"][0]["body_text"])
        self.assertNotIn("body_text", self.local()["messages"][1])
        self.assertEqual("pushed", result["status"])
        self.assertEqual(NEW_SHA, result["version"])
        state = json.loads((self.root / sync.SYNC_STATE_PATH).read_text(encoding="utf-8"))
        self.assertEqual(NEW_SHA, state["version"])

    def test_latest_run_and_report_are_selected_without_dropping_other_ids(self):
        local, remote = fixture(), fixture()
        remote["runs"][0].update(status="success", finished_at="2026-09-06T12:00:00+08:00")
        local["reports"][0].update(title="本机更新简报", generated_at="2026-09-06T12:00:00+08:00")
        merged = sync.merge_for_push(local, remote, self.root)
        self.assertEqual("success", merged["runs"][0]["status"])
        self.assertEqual("本机更新简报", merged["reports"][0]["title"])

    def test_new_terminal_states_and_later_restoration_follow_status_version(self):
        for state in ("no_action", "out_of_scope"):
            with self.subTest(state=state):
                local, remote = fixture(), fixture()
                remote["actions"][0].update(status=state, updated_at="2026-09-06T09:00:00+08:00")
                self.write_local(local)
                self.sync("pull", FakeSession([repo_response(), content_response(remote)]))
                self.assertEqual(state, self.local()["actions"][0]["status"])
                self.assertIsNone(self.local()["actions"][0]["completed_at"])
                local = self.local()
                local["actions"][0].update(status="pending", updated_at="2026-09-06T10:00:00+08:00")
                merged = sync.merge_for_push(local, remote, self.root)
                self.assertEqual("pending", merged["actions"][0]["status"])
                local["actions"][0]["updated_at"] = remote["actions"][0]["updated_at"]
                self.assertEqual(state, sync.merge_for_push(local, remote, self.root)["actions"][0]["status"])

    def test_report_action_ids_survive_sync_export_with_legacy_report_unchanged(self):
        remote = fixture()
        remote["reports"].append({**remote["reports"][0], "id": "new-report", "action_ids": ["a1"]})
        session = FakeSession([repo_response(), content_response(remote), http_result(payload={"content": {"sha": NEW_SHA}})])
        self.sync("push", session)
        payload = session.calls[-1][2]["json"]
        uploaded = json.loads(base64.b64decode(payload["content"]))
        reports = {report["id"]: report for report in uploaded["reports"]}
        self.assertEqual(["a1"], reports["new-report"]["action_ids"])
        self.assertNotIn("action_ids", reports["p1"])
        self.assertEqual("摘要内容", reports["p1"]["markdown"])

    def test_push_preserves_remote_only_attachments_with_local_same_id_metadata(self):
        local, remote = fixture(), fixture()
        remote["messages"][0]["attachments"].append({**remote["messages"][0]["attachments"][0], "id": "f2", "name": "云端补充.xlsx"})
        remote["messages"][0]["attachments"][0]["name"] = "远端旧名.xlsx"
        merged = sync.merge_for_push(local, remote, self.root)
        items = {item["id"]: item for item in merged["messages"][0]["attachments"]}
        self.assertEqual({"f1", "f2"}, set(items))
        self.assertEqual("材料.xlsx", items["f1"]["name"])

    def test_create_initial_snapshot_omits_sha_and_uploads_only_whitelist(self):
        session = FakeSession([repo_response(), http_result(404), http_result(201, {"content": {"sha": NEW_SHA}})])
        self.sync("push", session)
        payload = session.calls[-1][2]["json"]
        self.assertNotIn("sha", payload)
        snapshot = json.loads(base64.b64decode(payload["content"]))
        self.assertNotIn("body_text", snapshot["messages"][0])
        self.assertNotIn("download_path", snapshot["messages"][0]["attachments"][0])

    def test_put_409_or_422_does_not_retry_or_modify_local_data(self):
        for status in (409, 422):
            with self.subTest(status=status):
                before = self.dashboard.read_bytes()
                session = FakeSession([repo_response(), content_response(), http_result(status, {"message": PRIVATE_MARKER})])
                self.assert_code("conflict", "push", session)
                self.assertEqual(before, self.dashboard.read_bytes())
                self.assertEqual(3, len(session.calls))
                self.assertFalse((self.root / sync.SYNC_STATE_PATH).exists())

    def test_permission_and_schema_failures_stop_before_any_local_or_remote_write(self):
        for status, code in ((401, "unauthorized"), (403, "forbidden"), (404, "repo_not_found")):
            session = FakeSession([http_result(status, {"message": PRIVATE_MARKER})])
            self.assert_code(code, "pull", session)
            self.assertEqual(self.original, self.local())
        invalid = fixture()
        invalid["schema_version"] = 2
        session = FakeSession([repo_response(), content_response(invalid)])
        self.assert_code("invalid_snapshot", "push", session)
        self.assertEqual(self.original, self.local())
        self.assertEqual(2, len(session.calls))

    def test_wrong_remote_account_is_rejected_without_state_merge(self):
        remote = fixture()
        remote["account"] = "other@example.edu.cn"
        session = FakeSession([repo_response(), content_response(remote)])
        self.assert_code("workspace_mismatch", "pull", session)
        self.assertEqual(self.original, self.local())

    def test_http_uses_bearer_headers_and_json_without_spawning_any_cli(self):
        session = FakeSession([repo_response(), content_response(), http_result(payload={"content": {"sha": NEW_SHA}})])
        with patch.object(subprocess, "run", side_effect=AssertionError("No CLI is allowed")) as process:
            self.sync("push", session)
        process.assert_not_called()
        for method, url, kwargs in session.calls:
            self.assertTrue(url.startswith("https://api.github.com/repos/"))
            self.assertNotIn(TEST_TOKEN, url)
            self.assertEqual(f"Bearer {TEST_TOKEN}", kwargs["headers"]["Authorization"])
            self.assertIs(kwargs["allow_redirects"], False)
            self.assertEqual(35, kwargs["timeout"])
            self.assertNotIn(TEST_TOKEN, json.dumps(kwargs.get("json")))
        self.assertIsInstance(session.calls[-1][2]["json"], dict)

    def test_status_returns_only_safe_counts_and_does_not_mutate_local_files(self):
        before = self.dashboard.read_bytes()
        session = FakeSession([repo_response(), content_response()])
        result = self.sync("status", session)
        self.assertEqual({"status", "repo", "branch", "private", "version", "message_count", "action_count", "run_count", "report_count"}, set(result))
        self.assertEqual(OLD_SHA, result["version"])
        self.assertTrue(result["private"])
        self.assertEqual(before, self.dashboard.read_bytes())
        self.assertFalse((self.root / ".workspace.lock").exists())
        self.assertFalse((self.root / sync.SYNC_STATE_PATH).exists())

    def test_lock_prevents_concurrent_ingestion_or_sync(self):
        session = FakeSession([])
        with mail_workspace._locked(self.root):
            self.assert_code("workspace_busy", "push", session)
        self.assertEqual([], session.calls)

    def test_local_write_failure_after_upload_reports_confirmed_remote_sha(self):
        session = FakeSession([repo_response(), content_response(), http_result(payload={"content": {"sha": NEW_SHA}})])
        with patch.object(mail_workspace, "_atomic_json", side_effect=OSError(PRIVATE_MARKER)):
            error = self.assert_code("local_write_failed_after_upload", "push", session)
        self.assertEqual(NEW_SHA, error.version)
        self.assertEqual(self.original, self.local())

    def test_cli_never_prints_http_diagnostics_credentials_or_exception_values(self):
        session = FakeSession([requests.ConnectionError("Authorization: " + TEST_TOKEN + PRIVATE_MARKER)])
        output = io.StringIO()
        with patch.object(sync.requests, "request", session.request), patch.dict(sync.os.environ, {"MAIL_WORKBENCH_TOKEN": TEST_TOKEN}), redirect_stdout(output):
            exit_code = sync.main(["--root", str(self.root), "status"])
        self.assertEqual(1, exit_code)
        self.assertEqual({"status": "error", "error_code": "network_error"}, json.loads(output.getvalue()))
        for value in ("Authorization", TEST_TOKEN, PRIVATE_MARKER):
            self.assertNotIn(value, output.getvalue())

    def test_http_timeout_and_connection_errors_have_safe_codes(self):
        for error, code in ((requests.ConnectionError(PRIVATE_MARKER), "network_error"),
                            (requests.Timeout(PRIVATE_MARKER), "network_timeout")):
            self.assert_code(code, "status", FakeSession([error]))

    def test_unsafe_remote_path_is_never_written_or_uploaded(self):
        remote = fixture()
        remote["messages"][0]["archive_path"] = "../elsewhere/source.json"
        session = FakeSession([repo_response(), content_response(remote)])
        self.assert_code("local_data_error", "push", session)
        self.assertEqual(self.original, self.local())
        self.assertEqual(2, len(session.calls))

    def test_first_upload_preserves_mail_exemption_chosen_after_local_extraction(self):
        for state in ("no_action", "out_of_scope"):
            with self.subTest(state=state):
                local = fixture()
                local["actions"].append({**local["actions"][0], "id": "new-second-task",
                                         "status": "done", "completed_at": "2026-09-06T08:00:00+08:00"})
                self.write_local(local)
                remote = fixture()
                remote["actions"] = []
                decision_time = "2026-09-06T09:00:00+08:00"
                remote["messages"][0].update(triage_status=state, triage_updated_at=decision_time)
                session = FakeSession([repo_response(), content_response(remote),
                                     http_result(payload={"content": {"sha": NEW_SHA}})])
                self.sync("push", session)
                payload = session.calls[-1][2]["json"]
                uploaded = json.loads(base64.b64decode(payload["content"]))
                for result in (uploaded, self.local()):
                    self.assertEqual([state, state], [row["status"] for row in result["actions"]])
                    self.assertTrue(all(row["completed_at"] is None for row in result["actions"]))
                    self.assertTrue(all(row["updated_at"] == decision_time for row in result["actions"]))
                    self.assertEqual(state, result["messages"][0]["triage_status"])

    def test_mail_exemption_never_overrides_existing_or_newer_task_decisions_on_push(self):
        for situation in ("existing-task", "existing-other-task", "newer-local-decision", "newer-mail-restoration"):
            with self.subTest(situation=situation):
                local, remote = fixture(), fixture()
                remote["messages"][0].update(triage_status="out_of_scope", triage_updated_at="2026-09-06T09:00:00+08:00")
                if situation == "existing-other-task":
                    remote["actions"][0]["id"] = "existing-other"
                elif situation in {"newer-local-decision", "newer-mail-restoration"}:
                    remote["actions"] = []
                    if situation == "newer-local-decision":
                        local["actions"][0]["updated_at"] = "2026-09-06T10:00:00+08:00"
                    else:
                        local["messages"][0].update(triage_status="pending", triage_updated_at="2026-09-06T10:00:00+08:00")
                before = copy.deepcopy(local["actions"][0])
                result = sync.merge_for_push(local, remote, self.root)
                actual = next(row for row in result["actions"] if row["id"] == before["id"])
                for key in sync.STATUS_FIELDS:
                    self.assertEqual(before[key], actual[key])


if __name__ == "__main__":
    unittest.main()
