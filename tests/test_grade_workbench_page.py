from pathlib import Path

from streamlit.testing.v1 import AppTest

from utils import grade_workbench_db


def test_first_visit_shows_retirement_notice_without_creating_task(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    monkeypatch.setattr(grade_workbench_db, "TASKS_DIR", tasks_dir)
    page = Path(__file__).resolve().parents[1] / "pages" / "16_17_grade_workbench.py"
    app = AppTest.from_file(str(page), default_timeout=10)
    app.run()
    assert not app.exception
    assert app.title[0].value == "M17 · 教学评分工作台 ❌"
    assert "已停用" in app.warning[0].value
    assert not app.text_input
    assert [button.label for button in app.button] == ["回到主页"]
    assert not tasks_dir.exists()
