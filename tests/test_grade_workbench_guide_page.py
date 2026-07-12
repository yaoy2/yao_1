from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_guide_page_loads_and_distinguishes_versions():
    page = Path(__file__).resolve().parents[1] / "pages" / "17_18_grade_workbench_guide.py"
    app = AppTest.from_file(str(page), default_timeout=10)
    app.run()
    assert not app.exception
    markdown = "\n".join(item.value for item in app.markdown)
    assert "评分工作台使用说明" in markdown
    assert "M18" in markdown
    assert "M17" in markdown
    assert "M16" in markdown
    assert "跨电脑评分数据同步尚未启用" in markdown
    assert "公开仓库" in markdown
