import builtins
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("filename, title", [
    ("15_16_report_grader.py", "M16 · 旧版报告评分与成绩联动 ❌"),
    ("16_17_grade_workbench.py", "M17 · 教学评分工作台 ❌"),
])
def test_retired_grade_pages_stop_before_business_imports(filename, title):
    page = Path(__file__).resolve().parents[1] / "pages" / filename
    original_import = builtins.__import__
    forbidden = {"grade_workbench", "grade_workbench_db", "grade_workbench_export", "report_grader"}

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {f"utils.{module}" for module in forbidden} or (
            name == "utils" and forbidden.intersection(fromlist or ())
        ):
            raise AssertionError(f"Retired page must not load business code: {name}")
        return original_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=guarded_import):
        app = AppTest.from_file(str(page), default_timeout=10).run()
        app.run()

    assert not app.exception
    assert app.title[0].value == title
    assert "已停用" in app.warning[0].value
    assert "archived" in app.caption[-1].value
    assert [button.label for button in app.button] == ["回到主页"]
    for element in ("file_uploader", "download_button", "data_editor", "text_input", "text_area", "metric"):
        assert not app.get(element), element
