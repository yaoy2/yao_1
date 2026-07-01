import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_page_helpers():
    page_source = (ROOT / "pages" / "15_0_email_notice.py").read_text(encoding="utf-8")
    module = ast.parse(page_source)
    names = {"build_prefill_script"}
    selected = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {"json": __import__("json")}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "pages/15_0_email_notice.py", "exec"), namespace)
    return page_source, namespace


class EmailNoticePageTest(unittest.TestCase):
    def test_paste_input_is_wrapped_in_form_to_avoid_component_reruns(self):
        page_source, _namespace = load_page_helpers()

        self.assertIn('st.form("email_notice_parse_form"', page_source)
        self.assertIn("form_submit_button", page_source)
        self.assertNotIn('st.button("一键识别并填入"', page_source)

    def test_prefill_script_retries_refresh_after_component_load(self):
        _page_source, namespace = load_page_helpers()

        script = namespace["build_prefill_script"](
            {
                "header": "成都东软学院健康医疗科技学院",
                "subject": "关于测试通知的通知",
                "number": "科研通知〔2026〕41号",
                "unit": "健康医疗科技学院",
                "date": "2026-07-01",
                "body_html": "<p>正文</p>",
            }
        )

        self.assertIn("function refreshEditorPreview()", script)
        self.assertIn("setTimeout(refreshEditorPreview, 0)", script)
        self.assertIn("setTimeout(refreshEditorPreview, 150)", script)

    def test_editor_asset_has_direct_bootstrap_fallback(self):
        html = (ROOT / "assets" / "email_notice_editor.html").read_text(encoding="utf-8")

        self.assertIn("function initEditor()", html)
        self.assertIn("document.readyState === 'loading'", html)
        self.assertIn("initEditor();", html)


if __name__ == "__main__":
    unittest.main()
