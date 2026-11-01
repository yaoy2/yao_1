import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest

from integrations.file_distribution.rules import ENTRY_FILENAME, RULE_ROWS, USER_GUIDE, VERSION

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "19_20_ding2026.py"


def test_m20_displays_shared_rules_and_manual_local_entry():
    app = AppTest.from_file(str(PAGE), default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "M20 · 文件分发"
    assert any(ENTRY_FILENAME in item.value for item in app.markdown)
    assert any(USER_GUIDE.strip() == item.value for item in app.markdown)
    assert app.table[0].value.to_dict("records") == RULE_ROWS
    assert "双击程序中完成" in app.info[0].value
    assert VERSION in app.caption[-1].value
    assert len(app.warning) == 0
    assert len(app.metric) == 0


def test_m20_does_not_scan_or_move_local_files_from_the_hosted_page():
    source = PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {
        "button", "download_button", "file_uploader", "form",
        "form_submit_button", "switch_page",
    }
    calls = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "st"
    }
    assert calls.isdisjoint(forbidden_calls)
    modules = {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert modules == {
        "sys", "pathlib", "streamlit", "utils.ui_theme",
        "integrations.file_distribution.rules",
    }
    invoked_names = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert invoked_names.isdisjoint({"scan", "execute", "open"})
    attributes = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert attributes.isdisjoint({"glob", "rglob", "iterdir", "read_text", "write_text", "rename"})
    assert "ding2026_m20_snapshot" not in source
    assert "127.0.0.1" not in source
    assert "GoogleDrive" not in source
