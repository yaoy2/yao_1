import re

import pytest

from utils import ui_theme
from utils.ui_theme import _get_sidebar_tools, _load_homepage_tools
from unittest.mock import patch


def test_navigation_cache_refreshes_when_homepage_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_theme, "__file__", str(tmp_path / "utils" / "ui_theme.py"))
    homepage = tmp_path / "hello.py"
    homepage.write_text('TOOLS = [{"title": "First", "code": "M01"}]', encoding="utf-8")
    ui_theme._parse_homepage_tools.cache_clear()
    with patch.object(ui_theme.ast, "parse", wraps=ui_theme.ast.parse) as parse:
        first = _load_homepage_tools()
        first[0]["title"] = "Local edit"
        assert _load_homepage_tools()[0]["title"] == "First"
        assert parse.call_count == 1
        homepage.write_text('TOOLS = [{"title": "Second title", "code": "M02"}]', encoding="utf-8")
        assert _load_homepage_tools()[0]["code"] == "M02"
        assert parse.call_count == 2


def test_sidebar_pins_frequent_tools_before_other_modules():
    tools = _get_sidebar_tools(_load_homepage_tools())
    codes = [tool["code"] for tool in tools]
    assert codes[:4] == ["M15", "M14", "M08", "M06"]
    assert codes[4:10] == ["M25", "M23", "M22", "M21", "M19", "M18"]
    assert codes[codes.index("M07") : codes.index("M07") + 6] == ["M07", "M24", "M20", "M17", "M16", "M13"]
    assert tools[codes.index("M24")]["blocked"] is True
    assert tools[codes.index("M16")]["blocked"] is True
    assert tools[codes.index("M17")]["blocked"] is True
    assert tools[codes.index("M20")]["blocked"] is True
    assert tools[codes.index("M11")]["blocked"] is True
    assert codes[codes.index("M13") + 1] == "M11"


class _FakeSidebar:
    def __init__(self):
        self.markdown_calls = []

    def markdown(self, body, **kwargs):
        self.markdown_calls.append((body, kwargs))


class _FakeContainer:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.sidebar = _FakeSidebar()
        self.markdown_calls = []
        self.container_keys = []
        self.button_calls = []
        self.switch_page_calls = []

    def markdown(self, body, **kwargs):
        self.markdown_calls.append((body, kwargs))

    def container(self, *, key):
        self.container_keys.append(key)
        return _FakeContainer()

    def button(self, label, **kwargs):
        self.button_calls.append((label, kwargs))
        return True

    def switch_page(self, page):
        self.switch_page_calls.append(page)


@pytest.mark.parametrize("code, title", [
    ("M11", "Recorder_笔记"),
    ("M16", "旧版报告评分与成绩联动"),
    ("M17", "教学评分工作台"),
])
def test_retired_tool_shows_cross_to_right_of_title_without_lock(monkeypatch, code, title):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(ui_theme, "st", fake_st)

    ui_theme.render_sidebar_nav()

    nav_body, _kwargs = fake_st.sidebar.markdown_calls[0]
    retired_link = re.search(
        rf'<a class="custom-nav-item"[^>]*title="{re.escape(code)} · {re.escape(title)}">.*?</a>',
        nav_body,
        re.DOTALL,
    ).group(0)
    assert f'<span class="custom-nav-label">{title}</span>' in retired_link
    assert '<span class="custom-nav-marks"> ❌</span>' in retired_link
    assert retired_link.index(f"{title}</span>") < retired_link.index("❌")
    assert retired_link.count("❌") == 1
    assert "🔒" not in retired_link
    assert "已停用" in retired_link


def test_home_link_uses_streamlit_homepage_route(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(ui_theme, "st", fake_st)
    monkeypatch.setattr(ui_theme, "_load_homepage_tools", lambda: [])

    ui_theme.render_home_link()

    assert fake_st.container_keys == ["home-link-fixed"]
    assert fake_st.button_calls == [
        (
            "回到主页",
            {
                "icon": "🏠",
                "width": "content",
            },
        )
    ]
    assert fake_st.switch_page_calls == ["hello.py"]
    css = "\n".join(body for body, _kwargs in fake_st.markdown_calls)
    assert ".st-key-home-link-fixed" in css
    assert 'href="/"' not in css


def test_sidebar_matches_homepage_apple_visual_tokens(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(ui_theme, "st", fake_st)
    monkeypatch.setattr(
        ui_theme,
        "_load_homepage_tools",
        lambda: [
            {
                "title": "示例工具",
                "code": "M21",
                "tag": "视觉资产",
                "page": "pages/20_21_awesome_design_md.py",
            }
        ],
    )

    ui_theme.render_sidebar_nav()

    assert len(fake_st.sidebar.markdown_calls) == 1
    nav_body, nav_kwargs = fake_st.sidebar.markdown_calls[0]
    assert nav_kwargs == {"unsafe_allow_html": True}
    assert "custom-nav-brand-mark" in nav_body
    assert "示例工具" in nav_body

    css = "\n".join(body for body, _kwargs in fake_st.markdown_calls)
    assert '[data-testid="stSidebar"] .custom-nav-item' in css
    assert '--font-text: "SF Pro Text", "Inter"' in css
    assert 'font-family: var(--font-text)' in css
    assert "#f5f5f7" in css
    assert "#1d1d1f" in css
    assert "#0066cc" in css
    assert "rgba(57, 223, 247" not in css
    assert "!important" in css
