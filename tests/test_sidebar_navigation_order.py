from utils.ui_theme import _get_sidebar_tools, _load_homepage_tools


def test_sidebar_puts_stock_portal_before_current_grade_tools():
    tools = _get_sidebar_tools(_load_homepage_tools())
    assert [tool["code"] for tool in tools[:4]] == ["M19", "M18", "M17", "M16"]
    assert tools[3]["blocked"] is True
