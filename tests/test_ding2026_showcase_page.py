import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "19_20_ding2026.py"


def test_m20_displays_retirement_without_old_statistics():
    app = AppTest.from_file(str(PAGE), default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "M20 · Ding2026 文件中转发放系统 ❌"
    assert "旧版已停用" in app.warning[0].value
    assert "全部作废" in app.warning[0].value
    assert "archived" in app.caption[-1].value
    assert len(app.metric) == 0


def test_m20_has_no_operational_controls_or_legacy_dependencies():
    source = PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {
        "button", "download_button", "file_uploader", "form",
        "form_submit_button", "link_button", "switch_page",
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
    assert modules == {"sys", "pathlib", "streamlit", "utils.ui_theme"}
    assert "ding2026_m20_snapshot" not in source
    assert "127.0.0.1" not in source
    assert "GoogleDrive" not in source
