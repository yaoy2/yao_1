from utils import ui_theme
from utils.ui_theme import _get_sidebar_tools, _load_homepage_tools


def test_sidebar_starts_with_current_showcase_tools():
    tools = _get_sidebar_tools(_load_homepage_tools())
    codes = [tool["code"] for tool in tools]
    assert codes[:5] == ["M21", "M20", "M19", "M18", "M17"]
    assert codes[codes.index("M06") : codes.index("M06") + 3] == ["M06", "M16", "M13"]
    assert tools[codes.index("M16")]["blocked"] is True


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


def test_home_link_uses_streamlit_homepage_route(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(ui_theme, "st", fake_st)
    monkeypatch.setattr(ui_theme, "render_sidebar_nav", lambda: None)

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
    assert 'font-family: "SF Pro Text", "Inter"' in css
    assert "#f5f5f7" in css
    assert "#1d1d1f" in css
    assert "#0066cc" in css
    assert "rgba(57, 223, 247" not in css
    assert "!important" in css
