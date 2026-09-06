"""Mail report presentation checks using synthetic text and HTML parsing only."""

import unittest
from html.parser import HTMLParser

from utils.mail_report_view import report_body_html, report_title


DAILY_REPORT = """# 2026-09-06 每日邮件简报

统计时间：2026-09-05T20:00+08:00 至 2026-09-06T20:00+08:00

覆盖状态：本统计窗口已核验完整。

## 邮件概览

- [教学] 课程反馈：请提交课程反馈材料。
- [科研] 项目进度：对照 A | B 两种方案核对。

## 待处理与时间节点

- **待确认 · 已逾期 · 提交课程反馈**｜截止：9月4日下班前（2026-09-04）｜责任：二级学院｜要求：提交 A | B 两版材料｜提交至：教务处

## 采集核对

未完成附件：1；最近成功游标：2026-09-06T20:00:00+08:00。
"""

MORNING_REPORT = """# 2026-09-07 工作日截止事项提醒

统计时间：2026-09-07T00:00+08:00 至 2026-09-07T09:00+08:00

覆盖状态：归档尚未覆盖完整统计窗口，以下仅为已读取内容。

## 待处理与时间节点

- **待处理 · 今日到期 · 提交会议材料**｜截止：9月7日下班前（2026-09-07）｜责任：行政办公室｜要求：核对会议材料｜提交至：学院办公室
- **待确认 · 时间待确认 · 核对报名要求**｜截止：未明确｜责任：待确认｜要求：核对原邮件｜提交至：待确认

## 采集核对

未完成附件：0；最近成功游标：尚无。
"""


class ParsedHTML(HTMLParser):
    """Collect tags and their visible text without depending on CSS or layout."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.stack = []
        self.text_parts = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": attrs, "parts": [], "children": []}
        if self.stack:
            self.stack[-1]["children"].append(node)
        self.nodes.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.text_parts.append(data)
        for node in self.stack:
            node["parts"].append(data)

    def tags(self, tag):
        return [node for node in self.nodes if node["tag"] == tag]

    @staticmethod
    def node_text(node):
        return "".join(node["parts"])

    @property
    def text(self):
        return "".join(self.text_parts)


class MailReportViewTests(unittest.TestCase):
    def test_daily_and_weekly_overviews_have_two_columns_without_duplicate_metadata(self):
        weekly = DAILY_REPORT.replace("每日邮件简报", "每周邮件工作汇总", 1)
        for source in (DAILY_REPORT, weekly):
            with self.subTest(title=source.splitlines()[0]):
                parsed = ParsedHTML(report_body_html(source))
                self.assertEqual([], parsed.tags("h1"))
                self.assertNotIn("统计时间：", parsed.text)
                self.assertTrue(parsed.tags("table"))
                rows = parsed.tags("tr")
                self.assertGreaterEqual(len(rows), 2)
                for row in rows:
                    cells = [node for node in row["children"] if node["tag"] in {"td", "th"}]
                    self.assertEqual(2, len(cells))
                for value in ("教学", "课程反馈", "请提交课程反馈材料。", "科研", "项目进度", "A | B"):
                    self.assertIn(value, parsed.text)

    def test_fullwidth_action_fields_keep_status_deadline_and_ascii_pipe_content(self):
        parsed = ParsedHTML(report_body_html(DAILY_REPORT))
        self.assertEqual(1, len(parsed.tags("article")))
        self.assertTrue(parsed.tags("dl"))
        action = parsed.node_text(parsed.tags("article")[0])
        for value in ("待确认", "已逾期", "提交课程反馈", "截止", "9月4日下班前", "2026-09-04",
                      "责任", "二级学院", "要求", "提交 A | B 两版材料", "提交至", "教务处"):
            self.assertIn(value, action)
        self.assertNotIn("**", action)

    def test_morning_report_keeps_unknown_and_date_only_deadlines_without_overview(self):
        for source in (MORNING_REPORT, MORNING_REPORT.replace("\n\n", "\n")):
            with self.subTest(blank_lines="\n\n" in source):
                parsed = ParsedHTML(report_body_html(source))
                self.assertFalse(parsed.tags("table"))
                self.assertEqual(2, len(parsed.tags("article")))
                for value in ("今日到期", "9月7日下班前", "2026-09-07", "时间待确认", "未明确", "核对报名要求"):
                    self.assertIn(value, parsed.text)
                for invented_time in ("17:00", "23:59", "00:00"):
                    self.assertNotIn(invented_time, parsed.text)

    def test_coverage_explanations_keep_complete_and_incomplete_meanings_distinct(self):
        complete = ParsedHTML(report_body_html("覆盖状态：本统计窗口已核验完整。")).text
        incomplete = ParsedHTML(report_body_html("覆盖状态：归档尚未覆盖完整统计窗口，以下仅为已读取内容。")).text
        self.assertNotEqual(complete, incomplete)
        self.assertRegex(complete, r"完整|核对|核验|收齐|齐全|已覆盖")
        self.assertRegex(incomplete, r"未|缺|不完整|仅|不全|部分")

    def test_collection_details_preserve_attachment_count_and_historical_cursor(self):
        parsed = ParsedHTML(report_body_html(DAILY_REPORT))
        self.assertEqual(1, len(parsed.tags("details")))
        details = parsed.node_text(parsed.tags("details")[0])
        self.assertRegex(details, r"附件[^0-9]{0,12}1(?:\D|$)")
        self.assertRegex(details, r"2026-09-06[ T]20:00")

    def test_unknown_paragraphs_preserve_text_and_escape_angle_brackets(self):
        source = "## 补充说明\n\n未知段落：保留 A | B 与 <审批中> 原文。\n下一行仍应保留。"
        parsed = ParsedHTML(report_body_html(source))
        for value in ("补充说明", "未知段落：保留 A | B 与 <审批中> 原文。", "下一行仍应保留。"):
            self.assertIn(value, parsed.text)
        self.assertFalse(parsed.tags("审批中"))

    def test_untrusted_images_links_and_html_never_create_active_elements(self):
        attack = ("![图片](https://tracker.invalid/pixel.gif) "
                  "[链接](https://tracker.invalid/open) "
                  "<img src='https://tracker.invalid/html.gif' onerror='alert(1)'> "
                  "<a href='https://tracker.invalid/html-link'>escaped-marker</a> "
                  "<script>alert('script-marker')</script> "
                  "<iframe src='https://tracker.invalid/frame'></iframe>")
        source = DAILY_REPORT.replace("请提交课程反馈材料。", attack).replace("提交 A | B 两版材料", attack)
        source += "\n![引用图片][pixel]\n[pixel]: https://tracker.invalid/reference.gif\n" + attack
        parsed = ParsedHTML(report_body_html(source))
        dangerous = {"img", "a", "script", "iframe", "object", "embed"}
        self.assertFalse(dangerous.intersection(node["tag"] for node in parsed.nodes))
        for node in parsed.nodes:
            for name, _ in node["attrs"]:
                self.assertFalse(name.startswith("on"))
                self.assertNotIn(name, {"src", "href", "srcset", "poster", "data", "action", "formaction", "background"})
        for value in ("escaped-marker", "script-marker", "https://tracker.invalid/pixel.gif",
                      "https://tracker.invalid/reference.gif"):
            self.assertIn(value, parsed.text)

    def test_report_titles_show_date_once_and_keep_title_when_date_is_missing(self):
        for title in ("2026-09-06 每日邮件简报", "每日邮件简报"):
            with self.subTest(title=title):
                display = report_title({"date": "2026-09-06", "kind": "daily", "title": title})
                self.assertEqual(1, display.count("2026-09-06"))
                self.assertIn("每日邮件简报", display)
        original = "2026-09-06 每周邮件工作汇总"
        self.assertEqual(original, report_title({"kind": "weekly", "title": original}))


if __name__ == "__main__":
    unittest.main()
