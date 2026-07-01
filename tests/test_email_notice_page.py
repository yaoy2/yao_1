import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EmailNoticePageTest(unittest.TestCase):
    def test_page_uses_streamlit_native_controls_for_preview_and_download(self):
        page_source = (ROOT / "pages" / "15_0_email_notice.py").read_text(encoding="utf-8")

        self.assertIn('st.form("email_notice_parse_form"', page_source)
        self.assertIn("form_submit_button", page_source)
        self.assertIn("build_notice_html", page_source)
        self.assertIn("build_notice_number", page_source)
        self.assertIn('st.text_input("通知编号数字"', page_source)
        self.assertIn('st.selectbox("落款单位"', page_source)
        self.assertIn('st.date_input("落款日期"', page_source)
        self.assertIn("st.download_button", page_source)
        self.assertIn('st.popover("查看源代码"', page_source)
        self.assertNotIn("build_prefill_script", page_source)
        self.assertNotIn("load_editor_html", page_source)

    def test_page_source_is_valid_python(self):
        page_source = (ROOT / "pages" / "15_0_email_notice.py").read_text(encoding="utf-8")

        ast.parse(page_source)


if __name__ == "__main__":
    unittest.main()
