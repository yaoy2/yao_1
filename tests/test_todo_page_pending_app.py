"""Use an isolated Streamlit test runner to verify failed-save and retry buttons."""

import hashlib
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_todo_db import patched_todo_storage
from utils import budget_auth, github_backup_sync, todo_db


def test_failed_sync_clears_submitted_input_and_retry_does_not_add_again(tmp_path):
    remote = {"content": todo_db.build_markdown_backup([]), "sha": "original-sha", "fail_once": True}

    def read_remote(*args, **kwargs):
        if remote["fail_once"] and todo_db.has_local_todos():
            remote["fail_once"] = False
            raise RuntimeError("模拟网络中断")
        return {"ok": True, "sha": remote["sha"], "content": remote["content"]}

    def publish(local_path, repo_path, message, **kwargs):
        assert kwargs["expected_sha"] == remote["sha"]
        remote["content"] = Path(local_path).read_text(encoding="utf-8")
        remote["sha"] = hashlib.sha256(remote["content"].encode("utf-8")).hexdigest()
        return {"ok": True, "sha": remote["sha"]}

    page = Path(__file__).resolve().parents[1] / "pages" / "14_todos.py"
    with patched_todo_storage(tmp_path), patch.object(budget_auth, "get_budget_password", return_value="test-only"), \
            patch.object(github_backup_sync, "read_file_from_github", side_effect=read_remote), \
            patch.object(github_backup_sync, "sync_file_to_github", side_effect=publish) as upload, \
            patch.object(github_backup_sync, "get_local_sync_baseline", return_value=None), \
            patch.object(github_backup_sync, "remember_local_sync_baseline"):
        app = AppTest.from_file(str(page), default_timeout=10)
        app.session_state["todo_authenticated"] = True
        app.run()
        assert not app.exception
        app.text_area(key="todo_quick_add_text").input("需要保留的待办")
        next(button for button in app.button if button.label == "保存待办").click().run()
        assert not app.exception
        original = todo_db.get_todos(view="all")
        assert len(original) == 1
        assert app.text_area(key="todo_quick_add_text").value == ""
        assert app.session_state["todo_pending_sync_sha"] == "original-sha"
        assert any("当前环境" in warning.value for warning in app.warning)
        upload.assert_not_called()

        # Clicking the old action again cannot resubmit the already saved body.
        next(button for button in app.button if button.label == "保存待办").click().run()
        assert not app.exception
        assert todo_db.get_todos(view="all") == original
        assert app.text_area(key="todo_quick_add_text").value == ""
        upload.assert_not_called()

        app.button(key="todo_retry_sync").click().run()
        assert not app.exception
        assert todo_db.get_todos(view="all") == original
        assert todo_db.parse_markdown_backup(remote["content"]) == original
        assert "todo_pending_sync_sha" not in app.session_state
        upload.assert_called_once()
        assert any("已保存并同步" in success.value for success in app.success)


def test_committed_save_with_lost_response_recovers_and_allows_next_item(tmp_path):
    remote = {"content": todo_db.build_markdown_backup([]), "sha": "original-sha", "lose_response": True}

    def read_remote(*args, **kwargs):
        return {"ok": True, "sha": remote["sha"], "content": remote["content"]}

    def publish(local_path, repo_path, message, **kwargs):
        assert kwargs["expected_sha"] == remote["sha"]
        remote["content"] = Path(local_path).read_text(encoding="utf-8")
        remote["sha"] = hashlib.sha256(remote["content"].encode("utf-8")).hexdigest()
        if remote["lose_response"]:
            remote["lose_response"] = False
            raise TimeoutError("云端已保存，但成功响应丢失")
        return {"ok": True, "sha": remote["sha"]}

    page = Path(__file__).resolve().parents[1] / "pages" / "14_todos.py"
    with patched_todo_storage(tmp_path), patch.object(budget_auth, "get_budget_password", return_value="test-only"), \
            patch.object(github_backup_sync, "read_file_from_github", side_effect=read_remote), \
            patch.object(github_backup_sync, "sync_file_to_github", side_effect=publish) as upload, \
            patch.object(github_backup_sync, "get_local_sync_baseline", return_value=None), \
            patch.object(github_backup_sync, "remember_local_sync_baseline"):
        app = AppTest.from_file(str(page), default_timeout=10)
        app.session_state["todo_authenticated"] = True
        app.run()
        app.text_area(key="todo_quick_add_text").input("第一次新增")
        next(button for button in app.button if button.label == "保存待办").click().run()
        assert not app.exception
        assert app.session_state["todo_pending_sync_sha"] == "original-sha"
        assert len(todo_db.parse_markdown_backup(remote["content"])) == 1

        app.button(key="todo_retry_sync").click().run()
        assert not app.exception
        assert "todo_pending_sync_sha" not in app.session_state
        upload.assert_called_once()
        assert len(todo_db.get_todos(view="all")) == 1

        app.text_area(key="todo_quick_add_text").input("恢复后继续新增")
        next(button for button in app.button if button.label == "保存待办").click().run()
        assert not app.exception
        assert upload.call_count == 2
        assert len(todo_db.get_todos(view="all")) == 2
        assert todo_db.parse_markdown_backup(remote["content"]) == todo_db.get_todos(view="all")
        assert "todo_pending_sync_sha" not in app.session_state
