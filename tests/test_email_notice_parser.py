import unittest

from utils.email_notice_parser import parse_notice_text


class EmailNoticeParserTest(unittest.TestCase):
    def test_parse_typical_notice_with_number_unit_and_chinese_date(self):
        raw_text = """
成都东软学院科研管理部通知

关于组织申报2026年度校级科研项目的通知

科研通知〔2026〕41号

各学院、各部门：
为进一步加强科研项目培育，现组织开展2026年度校级科研项目申报工作。
请各单位于7月10日前完成材料报送。

成都东软学院科研管理部
2026年7月1日
"""

        parsed = parse_notice_text(raw_text)

        self.assertEqual(parsed["header"], "成都东软学院科研管理部通知")
        self.assertEqual(parsed["subject"], "关于组织申报2026年度校级科研项目的通知")
        self.assertEqual(parsed["number"], "科研通知〔2026〕41号")
        self.assertEqual(parsed["unit"], "成都东软学院科研管理部")
        self.assertEqual(parsed["date"], "2026-07-01")
        self.assertIn("各学院、各部门：", parsed["body_text"])
        self.assertIn("<p>为进一步加强科研项目培育，现组织开展2026年度校级科研项目申报工作。</p>", parsed["body_html"])
        self.assertNotIn("科研通知〔2026〕41号", parsed["body_text"])
        self.assertNotIn("2026年7月1日", parsed["body_text"])

    def test_parse_notice_without_number_uses_subject_as_first_non_header_line(self):
        raw_text = """
学院工作通知
关于提交竞赛指导材料的通知

各位老师：
请于本周五前提交相关材料。

健康医疗科技学院
2026年6月30日
"""

        parsed = parse_notice_text(raw_text)

        self.assertEqual(parsed["header"], "学院工作通知")
        self.assertEqual(parsed["subject"], "关于提交竞赛指导材料的通知")
        self.assertEqual(parsed["number"], "")
        self.assertEqual(parsed["unit"], "健康医疗科技学院")
        self.assertEqual(parsed["date"], "2026-06-30")
        self.assertEqual(parsed["body_text"], "各位老师：\n请于本周五前提交相关材料。")


if __name__ == "__main__":
    unittest.main()
