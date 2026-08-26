from utils.ui_theme import _get_sidebar_tools, _load_homepage_tools


def test_sidebar_starts_with_current_grade_tools():
    tools = _get_sidebar_tools(_load_homepage_tools())
    codes = [tool["code"] for tool in tools]
    assert "M16" not in codes[:4]
    assert codes.index("M18") < codes.index("M16")
    assert codes.index("M17") < codes.index("M16")
    assert codes[codes.index("M06") : codes.index("M06") + 3] == ["M06", "M16", "M05"]
    assert tools[codes.index("M16")]["blocked"] is True