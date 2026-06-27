import ast
import re
import unittest
from pathlib import Path


def load_homepage_bits():
    page_source = (Path(__file__).resolve().parents[1] / "hello.py").read_text(encoding="utf-8")
    module = ast.parse(page_source)
    names = {
        "TOOLS",
        "get_homepage_tools",
        "get_homepage_pages",
    }
    selected = [
        node
        for node in module.body
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)
        )
        or (isinstance(node, ast.FunctionDef) and node.name in names)
    ]
    namespace = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(Path("hello.py")), "exec"), namespace)
    return page_source, namespace


class HomePageTest(unittest.TestCase):
    def test_home_page_uses_command_center_copy_and_pagination(self):
        page_source = (Path(__file__).resolve().parents[1] / "hello.py").read_text(encoding="utf-8")

        self.assertNotIn("干他妈的", page_source)
        self.assertNotIn("principle-chip", page_source)
        self.assertNotIn("十一个工具，分页进入", page_source)
        self.assertIn("前方没有胜利，挺住意味一切", page_source)
        self.assertIn("page_tools = homepage_pages[page_index]", page_source)
        self.assertIn("for row_start in range(0, 9, 3)", page_source)
        self.assertIn("build_pagination_html", page_source)
        self.assertIn("build_streamlit_page_href", page_source)
        self.assertIn("module_page", page_source)
        self.assertIn("pagination-bar", page_source)
        self.assertIn("pagination-dock", page_source)
        self.assertIn("locked", page_source)
        self.assertIn("build_tool_title_html", page_source)
        self.assertIn("build_tool_status_icon_html", page_source)
        self.assertIn("tool-lock", page_source)
        self.assertIn("tool-blocked", page_source)
        self.assertIn("🔒", page_source)
        self.assertNotIn(">锁</span>", page_source)
        pagination_render = page_source.index("f'<div class=\"pagination-dock\">")
        self.assertLess(page_source.index("for row_start in range(0, 9, 3)"), pagination_render)
        self.assertLess(pagination_render, page_source.index("quote-strip"))
        self.assertNotIn("st.radio(\"工具分页\"", page_source)
        self.assertNotIn("进入线上版", page_source)
        self.assertNotIn("Local Port 8501", page_source)
        self.assertNotIn("status-band", page_source)
        self.assertNotIn("首页入口固定为 3x3", page_source)
        self.assertIn('class="tool-title"', page_source)
        self.assertIn('target="_self"', page_source)
        self.assertIn("build_tool_status_icon_html", page_source)
        self.assertIn("tool-lock-spacer", page_source)
        self.assertNotIn("st.button", page_source)
        self.assertNotIn("st.switch_page", page_source)
        self.assertNotIn("tool-title-link", page_source)
        self.assertNotIn("tool-title-ghost", page_source)
        self.assertNotIn("tool-enter-link", page_source)
        self.assertNotIn("tool-card-link", page_source)
        self.assertNotIn("st.page_link", page_source)
        self.assertNotIn("READY", page_source)

    def test_tools_are_newest_first_and_oldest_on_second_page(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["TOOLS"]

        self.assertEqual("LLM 余额管理", tools[0]["title"])
        self.assertEqual("M13", tools[0]["code"])
        self.assertEqual("Codex雷达", tools[1]["title"])
        self.assertEqual("M12", tools[1]["code"])
        self.assertEqual("Recorder_笔记", tools[2]["title"])
        self.assertTrue(tools[2]["locked"])
        self.assertEqual("灵感便签盒", tools[3]["title"])
        budget_tool = next(tool for tool in tools if tool["title"] == "预算速记台账")
        self.assertTrue(budget_tool["locked"])
        blocked_codes = {tool["code"] for tool in tools if tool.get("blocked")}
        self.assertEqual({"M01", "M02", "M03", "M04", "M05"}, blocked_codes)
        self.assertEqual("报告评分", tools[-1]["title"])
        self.assertEqual("pages/12_1_scoring❌.py", tools[-1]["page"])
        self.assertTrue(tools[-1]["blocked"])
        self.assertEqual(13, len(tools))
        self.assertEqual(9, len(tools[:9]))

    def test_page_files_are_sorted_by_created_date_newest_first(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["TOOLS"]
        pages_dir = Path(__file__).resolve().parents[1] / "pages"

        created_values = [tool["created"] for tool in tools]
        self.assertEqual(sorted(created_values, reverse=True), created_values)

        expected_pages = [tool["page"] for tool in tools]
        actual_pages = [f"pages/{path.name}" for path in sorted(pages_dir.glob("*.py"))]
        self.assertEqual(expected_pages, actual_pages)

        for sort_index, tool in enumerate(tools):
            page_name = Path(tool["page"]).name
            module_number = int(tool["code"].removeprefix("M"))
            self.assertTrue(
                page_name.startswith(f"{sort_index:02d}_{module_number}_"),
                f"{page_name} should use sidebar sort index {sort_index:02d} and module number {module_number}",
            )

    def test_homepage_defers_red_x_cards_without_changing_nav_order(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["TOOLS"]
        homepage_pages = namespace["get_homepage_pages"](tools)

        self.assertEqual("M13", tools[0]["code"])
        self.assertEqual("M01", tools[-1]["code"])
        self.assertEqual("M06", homepage_pages[0][-1]["code"])
        self.assertEqual(["M05", "M04", "M03", "M02", "M01"], [tool["code"] for tool in homepage_pages[1]])
        self.assertTrue(all(not tool.get("blocked") for tool in homepage_pages[0]))
        self.assertTrue(all(tool.get("blocked") for tool in homepage_pages[1]))


if __name__ == "__main__":
    unittest.main()
