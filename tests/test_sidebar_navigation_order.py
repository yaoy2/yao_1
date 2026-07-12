from utils.ui_theme import _get_sidebar_tools, _load_homepage_tools


def test_sidebar_keeps_replaced_m16_beside_current_grade_tools():
    tools = _get_sidebar_tools(_load_homepage_tools())
    assert [tool["code"] for tool in tools[:3]] == ["M18", "M17", "M16"]
    assert tools[2]["blocked"] is True
    assert tools[2]["second_page"] is True
