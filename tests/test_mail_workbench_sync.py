import base64
import copy
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import mail_workbench_sync as sync
from utils import mail_workspace


OLD_SHA = "a" * 40
NEW_SHA = "b" * 40
PRIVATE_MARKER = "private-test-mail-body-do-not-log"
SENSITIVE_STDERR = b"Authorization: fake-only-sensitive-diagnostic"


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


def http_result(status=200, payload=None, returncode=None):
    body = json.dumps(payload if payload is not None else {}, ensure_ascii=False).encode("utf-8")
    stdout = f"HTTP/2.0 {status} Response\r\nContent-Type: application/json\r\nX-Test: private-header\r\n\r\n".encode("ascii") + body
    return SimpleNamespace(returncode=(0 if status < 400 else 1) if returncode is None else returncode,
                           stdout=stdout, stderr=SENSITIVE_STDERR)


def repo_response(private=True, full_name=sync.DEFAULT_REPO):
    return http_result(payload={"private": private, "full_name": full_name})


def content_response(data=None, sha=OLD_SHA):
    content = base64.b64encode(json.dumps(fixture() if data is None else data, ensure_ascii=False).encode("utf-8")).decode("ascii")
    return http_result(payload={"sha": sha, "encoding": "base64", "content": content})


class FakeRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
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

    def sync(self, command, runner, **kwargs):
        return sync.synchronize(self.root, command, runner=runner, **kwargs)

    def assert_code(self, code, command, runner, **kwargs):
        with self.assertRaises(sync.MailCommandError) as caught:
            self.sync(command, runner, **kwargs)
        self.assertEqual(code, caught.exception.code)
        self.assertNotIn(PRIVATE_MARKER, str(caught.exception))
        self.assertNotIn("Authorization", str(caught.exception))
        return caught.exception

    def test_private_repo_checked_before_contents_and_public_repo_is_rejected(self):
        for private in (False, None, "true"):
            with self.subTest(private=private):
                runner = FakeRunner([repo_response(private)])
                self.assert_code("public_repo_forbidden", "push", runner)
                self.assertEqual(1, len(runner.calls))
                self.assertEqual("repos/" + sync.DEFAULT_REPO, runner.calls[0][0][2])
                self.assertEqual(self.original, self.local())
        runner = FakeRunner([])
        self.assert_code("public_repo_forbidden", "status", runner, repo="yaoy2/yao_1")
        self.assertEqual([], runner.calls)

    def test_transferred_repository_is_not_silently_used(self):
        runner = FakeRunner([repo_response(full_name="other/private-repo")])
        self.assert_code("repository_mismatch", "status", runner)
        self.assertEqual(1, len(runner.calls))

    def test_first_empty_pull_records_version_without_changing_dashboard(self):
        original_bytes = self.dashboard.read_bytes()
        runner = FakeRunner([repo_response(), http_result(404)])
        result = self.sync("pull", runner)
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
        runner = FakeRunner([repo_response(), content_response(remote)])
        result = self.sync("pull", runner)
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
        self.assertEqual(2, len(runner.calls))

    def test_older_remote_action_never_reopens_newer_local_completion(self):
        local = fixture()
        local["actions"][0].update(status="done", updated_at="2026-09-06T12:00:00+08:00", completed_at="2026-09-06T12:00:00+08:00")
        self.write_local(local)
        runner = FakeRunner([repo_response(), content_response()])
        self.sync("pull", runner)
        self.assertEqual(local, self.local())

    def test_web_completion_survives_later_ingestion_of_changed_requirements(self):
        # The webpage edits the action after our pull, while a later collection
        # changes only its requirement text. Collection time is not a new user
        # status version and must not reopen the completed task.
        self.sync("pull", FakeRunner([repo_response(), content_response()]))
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
        runner = FakeRunner([repo_response(), content_response(remote), http_result(payload={"content": {"sha": NEW_SHA}})])
        self.sync("push", runner)
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
        runner = FakeRunner([repo_response(), content_response(remote), http_result(payload={"content": {"sha": NEW_SHA}})])
        result = self.sync("push", runner)
        command, kwargs = runner.calls[-1]
        self.assertEqual("PUT", command[command.index("--method") + 1])
        self.assertEqual("-", command[command.index("--input") + 1])
        payload = json.loads(kwargs["input"].decode("utf-8"))
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

    def test_push_preserves_remote_only_attachments_with_local_same_id_metadata(self):
        local, remote = fixture(), fixture()
        remote["messages"][0]["attachments"].append({**remote["messages"][0]["attachments"][0], "id": "f2", "name": "云端补充.xlsx"})
        remote["messages"][0]["attachments"][0]["name"] = "远端旧名.xlsx"
        merged = sync.merge_for_push(local, remote, self.root)
        items = {item["id"]: item for item in merged["messages"][0]["attachments"]}
        self.assertEqual({"f1", "f2"}, set(items))
        self.assertEqual("材料.xlsx", items["f1"]["name"])

    def test_create_initial_snapshot_omits_sha_and_uploads_only_whitelist(self):
        runner = FakeRunner([repo_response(), http_result(404), http_result(201, {"content": {"sha": NEW_SHA}})])
        self.sync("push", runner)
        payload = json.loads(runner.calls[-1][1]["input"])
        self.assertNotIn("sha", payload)
        snapshot = json.loads(base64.b64decode(payload["content"]))
        self.assertNotIn("body_text", snapshot["messages"][0])
        self.assertNotIn("download_path", snapshot["messages"][0]["attachments"][0])

    def test_put_409_or_422_does_not_retry_or_modify_local_data(self):
        for status in (409, 422):
            with self.subTest(status=status):
                before = self.dashboard.read_bytes()
                runner = FakeRunner([repo_response(), content_response(), http_result(status, {"message": PRIVATE_MARKER})])
                self.assert_code("conflict", "push", runner)
                self.assertEqual(before, self.dashboard.read_bytes())
                self.assertEqual(3, len(runner.calls))
                self.assertFalse((self.root / sync.SYNC_STATE_PATH).exists())

    def test_permission_and_schema_failures_stop_before_any_local_or_remote_write(self):
        for status, code in ((401, "unauthorized"), (403, "forbidden"), (404, "repo_not_found")):
            runner = FakeRunner([http_result(status, {"message": PRIVATE_MARKER})])
            self.assert_code(code, "pull", runner)
            self.assertEqual(self.original, self.local())
        invalid = fixture()
        invalid["schema_version"] = 2
        runner = FakeRunner([repo_response(), content_response(invalid)])
        self.assert_code("invalid_snapshot", "push", runner)
        self.assertEqual(self.original, self.local())
        self.assertEqual(2, len(runner.calls))

    def test_wrong_remote_account_is_rejected_without_state_merge(self):
        remote = fixture()
        remote["account"] = "other@example.edu.cn"
        runner = FakeRunner([repo_response(), content_response(remote)])
        self.assert_code("workspace_mismatch", "pull", runner)
        self.assertEqual(self.original, self.local())

    def test_runner_uses_byte_input_without_shell_or_credential_arguments(self):
        runner = FakeRunner([repo_response(), content_response(), http_result(payload={"content": {"sha": NEW_SHA}})])
        self.sync("push", runner)
        for command, kwargs in runner.calls:
            self.assertIs(kwargs["shell"], False)
            self.assertIs(kwargs["text"], False)
            self.assertTrue(kwargs["capture_output"])
            self.assertNotIn("Authorization", " ".join(command))
            self.assertEqual("github.com", command[command.index("--hostname") + 1])
        self.assertIsInstance(runner.calls[-1][1]["input"], bytes)

    def test_status_returns_only_safe_counts_and_does_not_mutate_local_files(self):
        before = self.dashboard.read_bytes()
        runner = FakeRunner([repo_response(), content_response()])
        result = self.sync("status", runner)
        self.assertEqual({"status", "repo", "branch", "private", "version", "message_count", "action_count", "run_count", "report_count"}, set(result))
        self.assertEqual(OLD_SHA, result["version"])
        self.assertTrue(result["private"])
        self.assertEqual(before, self.dashboard.read_bytes())
        self.assertFalse((self.root / ".workspace.lock").exists())
        self.assertFalse((self.root / sync.SYNC_STATE_PATH).exists())

    def test_lock_prevents_concurrent_ingestion_or_sync(self):
        runner = FakeRunner([])
        with mail_workspace._locked(self.root):
            self.assert_code("workspace_busy", "push", runner)
        self.assertEqual([], runner.calls)

    def test_local_write_failure_after_upload_reports_confirmed_remote_sha(self):
        runner = FakeRunner([repo_response(), content_response(), http_result(payload={"content": {"sha": NEW_SHA}})])
        with patch.object(mail_workspace, "_atomic_json", side_effect=OSError(PRIVATE_MARKER)):
            error = self.assert_code("local_write_failed_after_upload", "push", runner)
        self.assertEqual(NEW_SHA, error.version)
        self.assertEqual(self.original, self.local())

    def test_cli_never_prints_raw_gh_diagnostics_or_exception_values(self):
        runner = FakeRunner([SimpleNamespace(returncode=1, stdout=b"", stderr=SENSITIVE_STDERR)])
        output = io.StringIO()
        with patch.object(subprocess, "run", runner), redirect_stdout(output):
            exit_code = sync.main(["--root", str(self.root), "status"])
        self.assertEqual(1, exit_code)
        self.assertEqual({"status": "error", "error_code": "gh_failed"}, json.loads(output.getvalue()))
        self.assertNotIn("Authorization", output.getvalue())
        self.assertNotIn(PRIVATE_MARKER, output.getvalue())

    def test_missing_gh_and_timeout_have_safe_codes(self):
        for error, code in ((FileNotFoundError(PRIVATE_MARKER), "gh_not_found"),
                            (subprocess.TimeoutExpired("gh", 35, output=PRIVATE_MARKER), "gh_timeout")):
            runner = FakeRunner([error])
            self.assert_code(code, "status", runner)

    def test_unsafe_remote_path_is_never_written_or_uploaded(self):
        remote = fixture()
        remote["messages"][0]["archive_path"] = "../elsewhere/source.json"
        runner = FakeRunner([repo_response(), content_response(remote)])
        self.assert_code("local_data_error", "push", runner)
        self.assertEqual(self.original, self.local())
        self.assertEqual(2, len(runner.calls))


if __name__ == "__main__":
    unittest.main()
