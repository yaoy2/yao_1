from utils.ui_theme import _get_sidebar_tools, _load_homepage_tools


def test_sidebar_starts_with_current_grade_tools():
    tools = _get_sidebar_tools(_load_homepage_tools())
    assert [tool["code"] for tool in tools[:4]] == ["M18", "M17", "M16", "M15"]
    assert tools[2]["blocked"] is True
