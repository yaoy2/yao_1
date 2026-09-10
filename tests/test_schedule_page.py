import ast
import html
import json
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from bs4 import BeautifulSoup

from tests.test_home_page import load_homepage_bits
from utils.schedule_docx import is_physical_education


ROOT = Path(__file__).resolve().parents[1]


def load_schedule_functions():
    path = ROOT / "pages" / "07_6_schedule.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {"PROJECT_ROOT", "DATA_DIR", "SCHEDULE_TERM", "SCHEDULE_CACHE_PATH", "CATEGORY_CACHE_PATH", "SCHEDULE_METADATA_PATH", "WEEKDAYS", "PERIODS", "CATEGORY_ORDER", "COUNCIL_MEMBERS"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) or (
        isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets)
    )]
    namespace = {"__file__": str(path), "Path": Path, "html": html, "json": json, "defaultdict": defaultdict}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class SchedulePageTest(unittest.TestCase):
    def setUp(self):
        self.page = load_schedule_functions()
        self.records = self.page["load_schedule_records"]()

    def test_current_cache_contains_only_this_term_without_sports_or_stale_teachers(self):
        metadata = json.loads((ROOT / "data" / "schedule_metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(253, len(self.records))
        self.assertEqual({"2026-2027-1"}, {r["term"] for r in self.records})
        self.assertFalse(any(is_physical_education(r["course"]) for r in self.records))
        teachers = {teacher for r in self.records for teacher in r["teachers"]}
        self.assertEqual(51, len(teachers))
        self.assertEqual(set(metadata["teachers"]), teachers)
        self.assertEqual(set(self.page["build_teacher_category_map"](self.records)), teachers)
        categories = json.loads((ROOT / "data" / "teacher_category_cache.json").read_text(encoding="utf-8"))
        self.assertEqual(set(categories), teachers)
        self.assertEqual(4, sum(r["source_truncated"] for r in self.records))

    def test_old_semester_cache_cannot_reappear(self):
        self.page["_load_cache"] = lambda path: [{"term": "2025-2026-2"}, {"course": "旧课表"}]
        self.assertEqual([], self.page["load_schedule_records"]())

    def test_teacher_and_council_filters_keep_late_lessons(self):
        grid = self.page["build_period_grid"](self.records, "全部教师")
        for record in self.records:
            for period in range(record["start_period"], record["end_period"] + 1):
                self.assertIn(record, grid[record["weekday"]][period])
        self.assertTrue(any(grid[day][14] for day in self.page["WEEKDAYS"]))
        teacher_grid = self.page["build_period_grid"](self.records, "高静")
        self.assertTrue(all("高静" in r["teachers"] for day in teacher_grid.values() for items in day.values() for r in items))
        council = [r for r in self.records if self.page["record_matches_filter"](r, "院务会")]
        self.assertTrue(council)
        self.assertTrue(all(set(r["teachers"]) & self.page["COUNCIL_MEMBERS"] for r in council))

    def test_grid_keeps_m06_layout_and_separate_week_room_details(self):
        first = dict(self.records[0], teachers=["示例教师"], teacher_label="示例教师", course="同一课程", weekday="星期四", start_period=6, end_period=8, week_text="1-8周", classroom="F3102", class_group="第一班")
        second = dict(first, week_text="9-16周", classroom="F3201", class_group="第二班")
        calls = []
        self.page["st"] = SimpleNamespace(markdown=lambda body, **kwargs: calls.append(body))
        grid = self.page["build_period_grid"]([first, second], "全部教师")
        self.page["render_grid"](grid, {})
        soup = BeautifulSoup(calls[-1], "html.parser")
        self.assertEqual(14, len(soup.select("tbody tr")))
        self.assertEqual(["节次", *self.page["WEEKDAYS"]], [th.get_text() for th in soup.select("th")])
        cell = soup.select("tbody tr")[5].find_all("td")[4]
        self.assertEqual(4, len(cell.select(".dept-col")))
        cards = cell.select("details")
        self.assertEqual(2, len(cards))
        self.assertIn("1-8周", cards[0].get_text())
        self.assertIn("F3102", cards[0].get_text())
        self.assertNotIn("F3201", cards[0].get_text())
        self.assertIn("9-16周", cards[1].get_text())
        self.assertIn("第二班", cards[1].get_text())

    def test_source_text_is_escaped_and_truncation_is_visible(self):
        record = dict(self.records[0], course="<script>alert(1)</script>", source_truncated=True)
        card = self.page["_card_html"](record)
        self.assertNotIn("<script>", card)
        self.assertIn("&lt;script&gt;", card)
        self.assertIn("原表信息已省略", card)

    def test_existing_m06_entry_is_updated_without_adding_another_module(self):
        _source, namespace = load_homepage_bits()
        entry = next(tool for tool in namespace["TOOLS"] if tool["code"] == "M06")
        self.assertEqual("课表查询-2026-2027-1", entry["title"])
        self.assertEqual("pages/07_6_schedule.py", entry["page"])


if __name__ == "__main__":
    unittest.main()
