import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "assets" / "email_notice_editor.html"


class EmailNoticeStandaloneHtmlTest(unittest.TestCase):
    def setUp(self):
        self.html = HTML_PATH.read_text(encoding="utf-8")

    def test_shareable_file_is_self_contained(self):
        self.assertTrue(HTML_PATH.exists())
        self.assertIn("<!DOCTYPE html>", self.html)
        self.assertIn('charset="UTF-8"', self.html)
        self.assertNotRegex(self.html, r"<script[^>]+src=")
        self.assertNotRegex(self.html, r"<link[^>]+href=['\"]https?://")
        self.assertNotIn("cdn.", self.html.lower())

    def test_shareable_file_includes_editor_and_college_defaults(self):
        self.assertIn("function parseNoticeText", self.html)
        self.assertIn("function saveHtmlFile", self.html)
        self.assertIn("function generateFinalHtml", self.html)
        self.assertIn("一键识别并填入", self.html)
        self.assertIn("成都东软学院健康医疗科技学院", self.html)
        self.assertIn("健康医疗科技学院通知〔2026〕", self.html)
        self.assertIn("健康医疗科技学院党政办", self.html)
        self.assertIn("保存HTML文件", self.html)
        self.assertIn("用浏览器打开即可", self.html)

    def test_parser_javascript_matches_python_notice_rules(self):
        start = self.html.index("var DEFAULT_HEADER")
        end = self.html.index("function recognizeNotice")
        parser_js = self.html[start:end]
        self.assertIn("function parseNoticeText", parser_js)
        self.assertIn("function extractNoticeNumberDigits", parser_js)
        self.assertIn("function textToBodyHtml", parser_js)

        node = _find_node()
        if not node:
            self.skipTest("本机没有 node，跳过 JavaScript 解析器执行检查")

        script = r"""
const assert = require("assert");
""" + parser_js + r"""
const typical = parseNoticeText(`
关于组织申报2026年度校级科研项目的通知

科研通知〔2026〕41号

各学院、各部门：
为进一步加强科研项目培育，现组织开展2026年度校级科研项目申报工作。
请各单位于7月10日前完成材料报送。

成都东软学院科研管理部
2026年7月1日
`);
assert.strictEqual(typical.header, "成都东软学院健康医疗科技学院");
assert.strictEqual(typical.subject, "关于组织申报2026年度校级科研项目的通知");
assert.strictEqual(typical.number, "科研通知〔2026〕41号");
assert.strictEqual(typical.unit, "成都东软学院科研管理部");
assert.strictEqual(typical.date, "2026-07-01");
assert.ok(typical.bodyText.includes("各学院、各部门："));
assert.ok(!typical.bodyText.includes("科研通知〔2026〕41号"));
assert.strictEqual(extractNoticeNumberDigits(typical.number), "41");
assert.strictEqual(buildNoticeNumber("41"), "健康医疗科技学院通知〔2026〕41号");
assert.strictEqual(
    textToBodyHtml("各位老师：\n\n一、材料要求\n请按时提交材料。"),
    "<p>各位老师：</p>\n<p><b>一、材料要求</b></p>\n<p>请按时提交材料。</p>"
);

const withoutNumber = parseNoticeText(`
关于提交竞赛指导材料的通知

各位老师：
请于本周五前提交相关材料。

健康医疗科技学院
2026年6月30日
`);
assert.strictEqual(withoutNumber.subject, "关于提交竞赛指导材料的通知");
assert.strictEqual(withoutNumber.number, "");
assert.strictEqual(withoutNumber.unit, "健康医疗科技学院");
assert.strictEqual(withoutNumber.date, "2026-06-30");
assert.strictEqual(withoutNumber.bodyText, "各位老师：\n请于本周五前提交相关材料。");
console.log("ok");
"""
        completed = subprocess.run(
            [node, "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=completed.stderr or completed.stdout,
        )
        self.assertIn("ok", completed.stdout)


def _find_node():
    for candidate in ("node", "nodejs"):
        try:
            completed = subprocess.run(
                [candidate, "-v"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError:
            continue
        if completed.returncode == 0:
            return candidate
    return None


if __name__ == "__main__":
    unittest.main()
