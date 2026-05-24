import ast
import re
import unittest
from pathlib import Path


class HomePageTest(unittest.TestCase):
    def test_home_page_uses_command_center_copy_and_pagination(self):
        page_source = (Path(__file__).resolve().parents[1] / "hello.py").read_text(encoding="utf-8")

        self.assertIn("干他妈的", page_source)
        self.assertIn("前方没有胜利，挺住意味一切", page_source)
        self.assertIn("page_tools = TOOLS[page_index * 9 : page_index * 9 + 9]", page_source)
        self.assertIn("for row_start in range(0, 9, 3)", page_source)

    def test_tools_are_newest_first_and_oldest_on_second_page(self):
        page_source = (Path(__file__).resolve().parents[1] / "hello.py").read_text(encoding="utf-8")
        match = re.search(r"TOOLS = (\[.*?\])\n\n\ndef build_terminal_preview_html", page_source, re.S)
        self.assertIsNotNone(match)

        tools = ast.literal_eval(match.group(1))

        self.assertEqual("灵感便签盒", tools[0]["title"])
        self.assertEqual("报告评分", tools[-1]["title"])
        self.assertEqual(10, len(tools))
        self.assertEqual(9, len(tools[:9]))


if __name__ == "__main__":
    unittest.main()
