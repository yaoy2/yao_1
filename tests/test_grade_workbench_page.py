from pathlib import Path

from streamlit.testing.v1 import AppTest

from utils import grade_workbench_db


def test_first_visit_shows_task_creation_in_main_page(tmp_path, monkeypatch):
    monkeypatch.setattr(grade_workbench_db, "TASKS_DIR", tmp_path / "tasks")
    page = Path(__file__).resolve().parents[1] / "pages" / "16_17_grade_workbench.py"
    app = AppTest.from_file(str(page), default_timeout=10)
    app.run()
    assert not app.exception
    assert app.title[0].value == "教学评分工作台"
    assert any(item.value == "先创建第一个评分任务" for item in app.subheader)
    assert any(item.label == "任务名称" for item in app.text_input)
    assert any(item.label == "创建并进入评分任务" for item in app.button)
