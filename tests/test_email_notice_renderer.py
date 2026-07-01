import unittest
from datetime import date

from utils.email_notice_renderer import build_notice_html, build_notice_number, text_to_body_html


class EmailNoticeRendererTest(unittest.TestCase):
    def test_text_to_body_html_wraps_non_empty_lines(self):
        html = text_to_body_html("各位老师：\n\n请按时提交材料。")

        self.assertEqual(html, "<p>各位老师：</p>\n<p>请按时提交材料。</p>")

    def test_build_notice_html_contains_core_notice_fields_and_dimensions(self):
        html = build_notice_html(
            header="成都东软学院健康医疗科技学院",
            subject="关于提交竞赛指导材料的通知",
            number=build_notice_number("41"),
            unit="健康医疗科技学院",
            date_value=date(2026, 7, 1),
            body_html="<p>各位老师：</p><p>请按时提交材料。</p>",
            table_width_pt=600,
            header_height_px=80,
        )

        self.assertIn("<title>关于提交竞赛指导材料的通知</title>", html)
        self.assertIn("成都东软学院健康医疗科技学院", html)
        self.assertIn("健康医疗科技学院通知〔2026〕41号", html)
        self.assertIn("2026年7月1日", html)
        self.assertIn("width:600pt", html)
        self.assertIn("height:80px", html)
        self.assertIn("width:526.0pt", html)
        self.assertIn("<p>请按时提交材料。</p>", html)

    def test_build_notice_number_keeps_prefix_and_suffix_while_user_enters_digits(self):
        self.assertEqual(build_notice_number("41"), "健康医疗科技学院通知〔2026〕41号")
        self.assertEqual(build_notice_number(" 041 "), "健康医疗科技学院通知〔2026〕041号")
        self.assertEqual(build_notice_number(""), "健康医疗科技学院通知〔2026〕 号")


if __name__ == "__main__":
    unittest.main()
