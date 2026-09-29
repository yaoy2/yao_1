"""Exercise date edits and passive refresh without running the page or using real data."""

import ast
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def page_functions():
    page = Path(__file__).resolve().parents[1] / "pages" / "14_todos.py"
    names = {"_date_value", "_compact_date_label", "_full_date_from_compact",
             "save_todo_due_fields", "refresh_todos_if_needed"}
    nodes = [node for node in ast.parse(page.read_text(encoding="utf-8")).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {
        "date": date, "datetime": datetime,
        "st": SimpleNamespace(session_state={}, warning=Mock()),
        "todo_db": SimpleNamespace(today=lambda: date(2026, 9, 30), update_todo=Mock()),
        "sync_todo_backup_to_github": Mock(),
        "merge_remote_todos_from_github": Mock(return_value=True),
        "monotonic": Mock(return_value=100.0),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(page), "exec"), namespace)
    return namespace


def test_old_year_remains_visible_and_save_preserves_it(page_functions):
    page = page_functions
    assert page["_compact_date_label"]("2025-12-31") == "2025-12-31"
    assert page["_compact_date_label"]("2026-12-31") == "12-31"
    page["prepare_todo_edit"] = Mock(return_value={"due_date": "2025-12-31"})
    page["st"].session_state.update(todo_due_date_1="12-31", todo_due_time_1="17:00")
    page["save_todo_due_fields"](1)
    page["todo_db"].update_todo.assert_called_once_with(1, due_date="2025-12-31", due_time="17:00")


def test_leap_date_uses_actual_year_and_invalid_edit_does_not_clear_date(page_functions):
    page = page_functions
    assert page["_full_date_from_compact"]("02-29", 2024) == "2024-02-29"
    assert page["_full_date_from_compact"]("02-29", 2026) == ""
    page["prepare_todo_edit"] = Mock(return_value={"due_date": "2026-12-31"})
    page["st"].session_state.update(todo_due_date_1="02-30", todo_due_time_1="17:00")
    page["save_todo_due_fields"](1)
    page["todo_db"].update_todo.assert_not_called()
    page["sync_todo_backup_to_github"].assert_not_called()
    page["st"].warning.assert_called_once()


def test_passive_refresh_is_throttled_and_retries_after_failure(page_functions):
    page = page_functions
    page["refresh_todos_if_needed"]()
    page["refresh_todos_if_needed"]()
    page["merge_remote_todos_from_github"].assert_called_once()
    page["monotonic"].return_value = 130.0
    page["merge_remote_todos_from_github"].return_value = False
    page["refresh_todos_if_needed"]()
    page["refresh_todos_if_needed"]()
    assert page["merge_remote_todos_from_github"].call_count == 3
