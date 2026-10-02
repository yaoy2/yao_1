"""Exercise remote failure boundaries without starting Streamlit or touching real data."""

import ast
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_todo_db import patched_todo_storage
from tests.test_todo_backup_validation import record
from utils import todo_db
from utils.todo_backup_validation import validate_todo_backup


@pytest.fixture
def page_functions():
    page = Path(__file__).resolve().parents[1] / "pages" / "14_todos.py"
    names = {"validate_todo_remote_backup", "merge_remote_todos_from_github", "sync_todo_backup_to_github",
             "restore_todo_backup_from_github", "todo_record_snapshot", "pending_todo_sync_sha",
             "warn_todo_sync_pending", "confirm_pending_todo_sync", "prepare_todo_edit", "save_todo_due_fields", "toggle_todo_done",
             "delete_todo_record", "_date_value", "_full_date_from_compact", "add_todo_from_page"}
    nodes = [node for node in ast.parse(page.read_text(encoding="utf-8")).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    stop_error = type("StopError", (BaseException,), {})
    rerun_error = type("RerunError", (BaseException,), {})
    namespace = {"os": os, "re": re, "date": date, "datetime": datetime,
                 "tempfile": tempfile, "Path": Path, "todo_db": todo_db,
                 "validate_todo_backup": validate_todo_backup,
                 "st": SimpleNamespace(secrets={}, session_state={}, warning=Mock(), info=Mock(), error=Mock(),
                                       stop=Mock(side_effect=stop_error), rerun=Mock(side_effect=rerun_error)),
                 "github_backup_sync": SimpleNamespace(read_file_from_github=Mock(), sync_file_to_github=Mock(),
                                                       remember_local_sync_baseline=Mock(),
                                                       get_local_sync_baseline=Mock(return_value=None)),
                 "StopError": stop_error, "RerunError": rerun_error}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(page), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("remote", [
    {"ok": False, "reason": "unexpected_failure"},
    {"ok": False, "skipped": True, "reason": "missing_token"},
    {"ok": False, "reason": "missing_remote_file"},
    {"ok": True, "content": todo_db.build_markdown_backup([record()])},
    {"ok": True, "sha": "known-sha", "content": "# 待办清单备份\n- 记录数量：3\n"},
])
def test_unverified_remote_never_imports_or_uploads(page_functions, remote, tmp_path):
    page = page_functions
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        todo_db.add_todo("本机记录", record_date="2026-09-30")
        before = Path(todo_db.DB_PATH).read_bytes()
        page["github_backup_sync"].read_file_from_github.return_value = remote
        assert page["merge_remote_todos_from_github"]() is False
        assert page["sync_todo_backup_to_github"](expected_sha="known-sha") is False
        assert Path(todo_db.DB_PATH).read_bytes() == before
        page["github_backup_sync"].sync_file_to_github.assert_not_called()


def test_network_failure_never_uploads(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        todo_db.add_todo("本机记录")
        page_functions["github_backup_sync"].read_file_from_github.side_effect = RuntimeError("network unavailable")
        assert page_functions["sync_todo_backup_to_github"](expected_sha="known-sha") is False
        page_functions["github_backup_sync"].sync_file_to_github.assert_not_called()


def test_empty_local_database_never_erases_existing_remote_records(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        page_functions["github_backup_sync"].read_file_from_github.return_value = {
            "ok": True, "sha": "known-sha", "content": todo_db.build_markdown_backup([record()])}
        assert page_functions["sync_todo_backup_to_github"](expected_sha="known-sha") is False
        assert todo_db.get_todos(view="all") == []
        page_functions["github_backup_sync"].sync_file_to_github.assert_not_called()


def test_verified_snapshot_merges_uid_tombstone_and_uses_observed_sha(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        todo_db.import_todo_records([record(content="需删除的事项")])
        deleted = record(content="需删除的事项", status="deleted", is_archived=True,
                         updated_at="2026-10-01 09:00:00")
        page_functions["github_backup_sync"].read_file_from_github.return_value = {
            "ok": True, "sha": "observed-sha", "content": todo_db.build_markdown_backup([deleted])}
        page_functions["github_backup_sync"].sync_file_to_github.return_value = {"ok": True}
        assert page_functions["merge_remote_todos_from_github"]() is True
        assert page_functions["sync_todo_backup_to_github"](expected_sha="observed-sha") is True
        assert todo_db.get_todos(view="all")[0]["status"] == "deleted"
        call = page_functions["github_backup_sync"].sync_file_to_github.call_args
        assert call.kwargs["expected_sha"] == "observed-sha"


def test_cas_conflict_retains_local_record_without_retrying_unconditionally(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        todo_db.add_todo("本机新增")
        page_functions["github_backup_sync"].read_file_from_github.return_value = {
            "ok": True, "sha": "old-sha", "content": todo_db.build_markdown_backup([])}
        page_functions["github_backup_sync"].sync_file_to_github.side_effect = RuntimeError("远端数据已更新")
        assert page_functions["sync_todo_backup_to_github"](expected_sha="old-sha") is False
        assert todo_db.get_todos()[0]["content"] == "本机新增"
        page_functions["github_backup_sync"].sync_file_to_github.assert_called_once()


def test_restore_checks_snapshot_before_writing_and_remembers_version(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        page = page_functions
        page["github_backup_sync"].read_file_from_github.return_value = {
            "ok": True, "sha": "cloud-sha", "content": todo_db.build_markdown_backup([record()])}
        page["restore_todo_backup_from_github"]()
        assert validate_todo_backup(Path(todo_db.BACKUP_MD_PATH).read_text(encoding="utf-8"))[0]["id"] == 7
        page["github_backup_sync"].remember_local_sync_baseline.assert_called_once()
        assert not list(tmp_path.glob(".todo-restore-*.tmp"))


def test_corrupt_existing_backup_is_preserved_and_initialization_stops(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        backup = Path(todo_db.BACKUP_MD_PATH)
        backup.write_text("既有但已损坏的待办备份", encoding="utf-8")
        with pytest.raises(page_functions["StopError"]):
            page_functions["restore_todo_backup_from_github"]()
        assert backup.read_text(encoding="utf-8") == "既有但已损坏的待办备份"
        page_functions["github_backup_sync"].read_file_from_github.assert_not_called()


def test_invalid_remote_restore_never_creates_backup(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        page_functions["github_backup_sync"].read_file_from_github.return_value = {
            "ok": True, "sha": "cloud-sha", "content": "# 待办清单备份\n- 记录数量：3\n"}
        with pytest.raises(page_functions["StopError"]):
            page_functions["restore_todo_backup_from_github"]()
        assert not Path(todo_db.BACKUP_MD_PATH).exists()
        page_functions["github_backup_sync"].remember_local_sync_baseline.assert_not_called()


def test_existing_partial_backup_is_not_silently_trimmed_on_initialization(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        text = todo_db.build_markdown_backup([record()]).replace("记录数量：1", "记录数量：2")
        backup = Path(todo_db.BACKUP_MD_PATH)
        backup.write_text(text, encoding="utf-8")
        with pytest.raises(page_functions["StopError"]):
            page_functions["restore_todo_backup_from_github"]()
        assert backup.read_text(encoding="utf-8") == text
        page_functions["github_backup_sync"].read_file_from_github.assert_not_called()


def test_valid_but_stale_local_backup_cannot_drop_new_database_records(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        todo_db.add_todo("当前数据库中的事项")
        stale_backup = todo_db.build_markdown_backup([])
        Path(todo_db.BACKUP_MD_PATH).write_text(stale_backup, encoding="utf-8")
        page_functions["github_backup_sync"].read_file_from_github.return_value = {
            "ok": True, "sha": "cloud-sha", "content": todo_db.build_markdown_backup([])}
        assert page_functions["sync_todo_backup_to_github"](expected_sha="cloud-sha") is False
        assert todo_db.get_todos()[0]["content"] == "当前数据库中的事项"
        assert Path(todo_db.BACKUP_MD_PATH).read_text(encoding="utf-8") == stale_backup
        page_functions["github_backup_sync"].sync_file_to_github.assert_not_called()


def test_remote_change_after_edit_preflight_never_overwrites_local_edit(page_functions, tmp_path):
    page = page_functions
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        original = record()
        todo_db.import_todo_records([original])
        page["st"].session_state.update({
            "todo_revision_7": f"{original['uid']}:{original['updated_at']}",
            "todo_due_date_7": "10-02", "todo_due_time_7": "14:00"})
        changed_elsewhere = record(content="另一端修改的内容", due_date="2026-10-03", due_time="17:00",
                                   status="done", is_archived=True, updated_at="2099-01-01 00:00:00")
        remote_change = {"ok": True, "sha": "changed-sha", "content": todo_db.build_markdown_backup([changed_elsewhere])}
        page["github_backup_sync"].read_file_from_github.side_effect = [
            {"ok": True, "sha": "preflight-sha", "content": todo_db.build_markdown_backup([original])}, remote_change]
        page["save_todo_due_fields"](7)
        local = todo_db.get_todos(view="all")[0]
        assert (local["content"], local["due_date"], local["due_time"], local["status"]) == (
            original["content"], "2026-10-02", "14:00", "pending")
        assert page["st"].session_state["todo_pending_sync_sha"] == "preflight-sha"
        page["github_backup_sync"].sync_file_to_github.assert_not_called()
        unchanged = Path(todo_db.DB_PATH).read_bytes()
        page["github_backup_sync"].read_file_from_github.side_effect = None
        page["github_backup_sync"].read_file_from_github.return_value = remote_change
        assert page["merge_remote_todos_from_github"]() is False
        assert page["sync_todo_backup_to_github"]() is False
        assert Path(todo_db.DB_PATH).read_bytes() == unchanged
        page["github_backup_sync"].sync_file_to_github.assert_not_called()


def test_same_version_does_not_reimport_old_remote_over_edit_when_clocks_differ(page_functions, tmp_path):
    page = page_functions
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        original = record(updated_at="2099-01-01 00:00:00")
        todo_db.import_todo_records([original])
        page["st"].session_state.update({
            "todo_revision_7": f"{original['uid']}:{original['updated_at']}",
            "todo_due_date_7": "10-02", "todo_due_time_7": "14:00"})
        page["github_backup_sync"].read_file_from_github.return_value = {
            "ok": True, "sha": "preflight-sha", "content": todo_db.build_markdown_backup([original])}
        page["github_backup_sync"].sync_file_to_github.return_value = {"ok": True}
        page["save_todo_due_fields"](7)
        local = todo_db.get_todos(view="all")[0]
        assert local["due_date"] == "2026-10-02"
        assert local["due_time"] == "14:00"
        assert "todo_pending_sync_sha" not in page["st"].session_state
        assert page["github_backup_sync"].sync_file_to_github.call_args.kwargs["expected_sha"] == "preflight-sha"


def test_pending_version_survives_new_browser_session_from_persisted_baseline(page_functions, tmp_path):
    page = page_functions
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        original = record()
        todo_db.import_todo_records([original])
        todo_db.update_todo(7, due_time="14:00")
        before = Path(todo_db.DB_PATH).read_bytes()
        page["github_backup_sync"].get_local_sync_baseline.return_value = {
            "sha": "before-local-edit", "content": todo_db.build_markdown_backup([original])}
        page["github_backup_sync"].read_file_from_github.return_value = {
            "ok": True, "sha": "new-cloud-version", "content": todo_db.build_markdown_backup([
                record(content="另一端新内容", updated_at="2099-01-01 00:00:00")])}
        assert page["merge_remote_todos_from_github"]() is False
        assert page["st"].session_state["todo_pending_sync_sha"] == "before-local-edit"
        assert Path(todo_db.DB_PATH).read_bytes() == before
        assert page["sync_todo_backup_to_github"]() is False
        page["github_backup_sync"].sync_file_to_github.assert_not_called()


def test_failed_new_item_save_reruns_and_retry_only_syncs_existing_uuid(page_functions, tmp_path):
    page = page_functions
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        snapshot = {"ok": True, "sha": "preflight-sha", "content": todo_db.build_markdown_backup([])}
        page["github_backup_sync"].read_file_from_github.side_effect = [snapshot, RuntimeError("network unavailable")]
        with pytest.raises(page["RerunError"]):
            page["add_todo_from_page"]("需保存的新增待办", None, "")
        saved = todo_db.get_todos(view="all")
        assert len(saved) == 1
        assert page["st"].session_state["todo_quick_add_saved"] is True
        assert page["st"].session_state["todo_save_notice"] == "pending"
        assert page["st"].session_state["todo_pending_sync_sha"] == "preflight-sha"
        page["github_backup_sync"].read_file_from_github.side_effect = None
        page["github_backup_sync"].read_file_from_github.return_value = snapshot
        page["github_backup_sync"].sync_file_to_github.return_value = {"ok": True}
        assert page["sync_todo_backup_to_github"]() is True
        assert todo_db.get_todos(view="all") == saved
        assert "todo_pending_sync_sha" not in page["st"].session_state
        page["st"].rerun.assert_called_once()


def test_no_preflight_version_never_uploads_existing_database(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        todo_db.add_todo("已有事项")
        assert page_functions["sync_todo_backup_to_github"]() is False
        page_functions["github_backup_sync"].read_file_from_github.assert_not_called()
        page_functions["github_backup_sync"].sync_file_to_github.assert_not_called()


def test_pending_comparison_retains_legacy_uid_and_numeric_id_remap_compatibility(page_functions, tmp_path):
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        original = record()
        todo_db.import_todo_records([{**original, "id": 42}])
        page_functions["github_backup_sync"].get_local_sync_baseline.return_value = {
            "sha": "known-sha", "content": todo_db.build_markdown_backup([original])}
        assert page_functions["pending_todo_sync_sha"]() is None
        legacy = {key: value for key, value in original.items() if key != "uid"}
        assert page_functions["todo_record_snapshot"]([legacy]) == page_functions["todo_record_snapshot"]([
            {**legacy, "uid": todo_db.record_uid(legacy)}])


@pytest.mark.parametrize("action", ["merge_remote_todos_from_github", "sync_todo_backup_to_github"])
def test_lost_success_response_recovers_without_uploading_again(page_functions, tmp_path, action):
    page = page_functions
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        todo_db.import_todo_records([record(), record(id=8, uid="second-record", content="另一项")])
        local = todo_db.get_todos(view="all")
        # Export time, line endings, order and local numeric IDs can differ across devices.
        remote_rows = [{**row, "id": row["id"] + 100} for row in reversed(local)]
        remote = {"ok": True, "sha": "committed-sha",
                  "content": todo_db.build_markdown_backup(remote_rows).replace("\n", "\r\n")}
        page["st"].session_state.update({"todo_pending_sync_sha": "before-write-sha",
                                         "todo_sync_error": "成功响应丢失"})
        page["github_backup_sync"].read_file_from_github.return_value = remote
        before = Path(todo_db.DB_PATH).read_bytes()

        assert page[action]() is True
        assert Path(todo_db.DB_PATH).read_bytes() == before
        assert "todo_pending_sync_sha" not in page["st"].session_state
        assert "todo_sync_error" not in page["st"].session_state
        assert page["st"].session_state["todo_observed_remote_sha"] == "committed-sha"
        page["github_backup_sync"].sync_file_to_github.assert_not_called()
        page["github_backup_sync"].remember_local_sync_baseline.assert_called_once_with(
            todo_db.BACKUP_MD_PATH, "data/todo_items_backup.md", remote["content"], remote["sha"],
            secrets=page["st"].secrets, environ=os.environ)


@pytest.mark.parametrize("action", ["merge_remote_todos_from_github", "sync_todo_backup_to_github"])
def test_matching_cloud_cannot_hide_stale_local_backup(page_functions, tmp_path, action):
    page = page_functions
    with patched_todo_storage(tmp_path):
        todo_db.init_db()
        todo_db.import_todo_records([record()])
        local = todo_db.get_todos(view="all")
        Path(todo_db.BACKUP_MD_PATH).write_text(todo_db.build_markdown_backup([]), encoding="utf-8")
        page["st"].session_state["todo_pending_sync_sha"] = "before-write-sha"
        page["github_backup_sync"].read_file_from_github.return_value = {
            "ok": True, "sha": "committed-sha", "content": todo_db.build_markdown_backup(local)}

        assert page[action]() is False
        assert page["st"].session_state["todo_pending_sync_sha"] == "before-write-sha"
        page["github_backup_sync"].sync_file_to_github.assert_not_called()
        page["github_backup_sync"].remember_local_sync_baseline.assert_not_called()
