"""Keep the public overview independent of private QQ data and receiver services."""

import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest


PAGE = Path(__file__).resolve().parents[1] / "pages" / "30_31_qq_archive.py"


def test_qq_overview_loads_with_navigation_and_discloses_acceptance_limits():
    app = AppTest.from_file(str(PAGE), default_timeout=10).run()

    assert not app.exception
    assert not app.error
    assert app.title[0].value == "M31 · QQ 归档机器人"
    assert "非实时运行状态" in app.caption[0].value
    rendered = "\n".join(item.value for item in app.markdown)
    for boundary in (
        "群内 AI 回复待验收",
        "另一成员发言、第二个群仍待实测",
        "登录自启未启用",
        "D 电脑同步回读待验收",
        "不读取群聊、不持有密钥",
        "QQ 实际推送的正文与附件",
    ):
        assert boundary in rendered
    assert len(app.sidebar.markdown) == 1
    assert [button.label for button in app.button] == ["回到主页"]
    assert not app.text_input
    assert not app.file_uploader
    assert not app.selectbox
    assert not app.checkbox


def test_qq_overview_uses_only_static_display_calls():
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    allowed_calls = {
        "render_home_link",
        "st.set_page_config",
        "st.markdown",
        "st.title",
        "st.caption",
        "st.expander",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert [(item.name, item.asname) for item in node.names] == [("streamlit", "st")]
        elif isinstance(node, ast.ImportFrom):
            assert node.module == "utils.ui_theme"
            assert [(item.name, item.asname) for item in node.names] == [("render_home_link", None)]
        elif isinstance(node, ast.Call):
            assert ast.unparse(node.func) in allowed_calls
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            raise AssertionError("The public overview must not embed service logic")
