from datetime import date
from pathlib import Path
import re

from streamlit.testing.v1 import AppTest

from utils import project_overview
from utils.project_overview import (
    build_project_rows,
    build_update_rows,
    filter_projects,
    load_public_updates,
    project_status,
)
from utils.ui_theme import _load_homepage_tools


ROOT = Path(__file__).resolve().parents[1]


def test_filter_combines_keywords_category_and_status():
    tools = _load_homepage_tools()
    assert [item["code"] for item in filter_projects(tools, "m20 月报", "行政", "current")] == ["M20"]
    assert [item["code"] for item in filter_projects(tools, status="paused")] == ["M28"]
    assert filter_projects(tools, section="行政", status="paused") == []
    assert filter_projects(tools, query="没有这个项目") == []
    assert {item["code"] for item in filter_projects(tools, query="需密码")} == {
        item["code"] for item in tools if item.get("locked")
    }
    ordered = filter_projects(tools)
    assert {item["code"] for item in ordered} == {item["code"] for item in tools}
    first_archived = next(index for index, item in enumerate(ordered) if project_status(item) == "archived")
    assert all(project_status(item) == "archived" for item in ordered[first_archived:])


def test_rows_escape_text_and_only_show_public_description_fields():
    tool = {
        "code": "M99", "title": '<img src=x onerror="bad()">', "desc": "<script>bad()</script>",
        "page": "pages/99_sample.py", "tag": "说明 & 示例", "section": "个人", "locked": True,
        "paused": True, "internal_notes": "DO_NOT_RENDER_PRIVATE_FIELDS",
    }
    html = build_project_rows([tool])
    assert '<img' not in html and '<script>' not in html
    assert "&lt;img" in html and "&lt;script&gt;" in html
    assert 'href="/sample"' in html and "需密码" in html
    assert "已暂停" in html and "查看说明" in html
    assert "DO_NOT_RENDER_PRIVATE_FIELDS" not in html
    tool["blocked"] = True
    assert project_status(tool) == "archived"
    assert "已归档" in build_project_rows([tool])


def test_public_updates_have_dates_and_public_source_links():
    updates = load_public_updates()
    assert updates
    dates = [date.fromisoformat(item["date"]) for item in updates]
    assert dates == sorted(dates, reverse=True)
    for item in updates:
        assert item["title"] and item["summary"]
        if item.get("commit"):
            assert re.fullmatch(r"[0-9a-f]{7,40}", item["commit"])
    html = build_update_rows(updates)
    links = re.findall(r'href="([^"]+)"', html)
    assert links and all(link.startswith("https://github.com/yaoy2/yao_1/commit/") for link in links)
    assert 'href=' not in build_update_rows([
        {"date": "2026-11-04", "title": "示例", "summary": "<b>文本</b>", "commit": 'bad" onclick="bad()'}
    ])


def _rows(app):
    return "\n".join(item.value for item in app.main.markdown if '<article class="overview-row">' in item.value)


def test_overview_page_filters_offline_and_exposes_navigation(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("The public overview must not fetch business records or remote repositories")

    monkeypatch.setattr("requests.sessions.Session.request", no_network)
    app = AppTest.from_file(str(ROOT / "pages/project_overview.py"), default_timeout=10).run()
    assert not app.exception
    assert _rows(app).count('<article class="overview-row">') == len(_load_homepage_tools())
    assert 'href="/project_overview"' in app.sidebar.markdown[0].value
    app.text_input[0].set_value("m20 月报").run()
    assert not app.exception
    assert _rows(app).count('<article class="overview-row">') == 1
    assert "文件分发" in _rows(app)
    app.text_input[0].set_value("")
    app.selectbox[1].select("paused").run()
    assert not app.exception
    assert _rows(app).count('<article class="overview-row">') == 1
    assert "Newspaper" in _rows(app) and "查看说明" in _rows(app)
    app.selectbox[0].select("行政").run()
    assert not app.exception
    assert not _rows(app) and app.info


def test_broken_update_file_does_not_hide_project_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(project_overview, "UPDATES_PATH", tmp_path / "missing.json")
    app = AppTest.from_file(str(ROOT / "pages/project_overview.py"), default_timeout=10).run()
    assert not app.exception
    assert _rows(app)
    assert any("更新摘要暂时无法读取" in item.value for item in app.warning)


def test_homepage_links_to_overview_without_new_module_number():
    app = AppTest.from_file(str(ROOT / "hello.py"), default_timeout=10).run()
    assert not app.exception
    html = "\n".join(item.value for item in app.main.markdown)
    assert 'href="/project_overview" target="_self">总览</a>' in html
    assert not any(item["page"] == "pages/project_overview.py" for item in _load_homepage_tools())
