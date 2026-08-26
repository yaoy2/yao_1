import ast
import unittest
from pathlib import Path


def load_homepage_bits():
    page_source = (Path(__file__).resolve().parents[1] / "hello.py").read_text(encoding="utf-8")
    module = ast.parse(page_source)
    names = {
        "TOOLS",
        "get_homepage_tools",
        "get_homepage_pages",
        "sort_tool_key",
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
        theme_source = (Path(__file__).resolve().parents[1] / "utils" / "ui_theme.py").read_text(encoding="utf-8")
        streamlit_config = (Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text(encoding="utf-8")

        self.assertNotIn("principle-chip", page_source)
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
        self.assertIn('class="tool-title"', page_source)
        self.assertIn('target="_self"', page_source)
        self.assertIn("tool-lock-spacer", page_source)
        self.assertIn("render_sidebar_nav()", theme_source)
        self.assertIn("_load_homepage_tools", theme_source)
        self.assertIn("hello.py", theme_source)
        self.assertIn("showSidebarNavigation = false", streamlit_config)
        self.assertNotIn("st.button", page_source)
        self.assertNotIn("st.switch_page", page_source)
        self.assertNotIn("st.page_link", page_source)
        pagination_render = page_source.index("f'<div class=\"pagination-dock\">")
        self.assertLess(page_source.index("for row_start in range(0, 9, 3)"), pagination_render)
        self.assertLess(pagination_render, page_source.index("quote-strip"))

    def test_tools_are_module_number_sorted_with_highest_module_first(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["get_homepage_tools"](namespace["TOOLS"])
        by_code = {tool["code"]: tool for tool in tools}
        codes = [tool["code"] for tool in tools]

        self.assertEqual("M19", tools[0]["code"])
        self.assertEqual("pages/18_19_concept_fables.py", tools[0]["page"])
        self.assertEqual("M18", tools[1]["code"])
        self.assertEqual("pages/17_18_grade_workbench_guide.py", by_code["M18"]["page"])
        self.assertEqual("M17", tools[2]["code"])
        self.assertEqual("pages/16_17_grade_workbench.py", by_code["M17"]["page"])
        self.assertEqual("M15", tools[3]["code"])
        self.assertEqual("pages/15_0_email_notice.py", by_code["M15"]["page"])
        self.assertTrue(by_code["M14"]["locked"])
        self.assertEqual(codes[codes.index("M06") : codes.index("M06") + 3], ["M06", "M16", "M05"])
        self.assertEqual("pages/15_16_report_grader.py", by_code["M16"]["page"])
        self.assertTrue(by_code["M16"]["blocked"])
        blocked_codes = {tool["code"] for tool in tools if tool.get("blocked")}
        self.assertEqual({"M01", "M02", "M03", "M04", "M05", "M16"}, blocked_codes)
        self.assertEqual("M01", tools[-1]["code"])
        self.assertEqual(18, len(tools))

    def test_homepage_order_is_module_number_driven_instead_of_filename_driven(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["get_homepage_tools"](namespace["TOOLS"])
        pages_dir = Path(__file__).resolve().parents[1] / "pages"

        actual_pages = [f"pages/{path.name}" for path in sorted(pages_dir.glob("*.py"))]
        self.assertIn("pages/15_0_email_notice.py", actual_pages)
        self.assertIn("pages/15_16_report_grader.py", actual_pages)
        self.assertNotEqual([tool["page"] for tool in tools], actual_pages)

        active_numbers = [int(tool["code"].removeprefix("M")) for tool in tools if not tool.get("blocked")]
        blocked_numbers = [int(tool["code"].removeprefix("M")) for tool in tools if tool.get("blocked")]
        self.assertEqual(sorted(active_numbers, reverse=True), active_numbers)
        self.assertEqual(sorted(blocked_numbers, reverse=True), blocked_numbers)
        self.assertTrue(all(not tool.get("blocked") for tool in tools[: len(active_numbers)]))
        self.assertFalse(Path(tools[0]["page"]).name.startswith("00_"))

    def test_homepage_keeps_blocked_cards_in_module_number_order(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["get_homepage_tools"](namespace["TOOLS"])
        homepage_pages = namespace["get_homepage_pages"](namespace["TOOLS"])
        codes = [tool["code"] for tool in tools]
        page1_codes = [tool["code"] for tool in homepage_pages[0]]
        page2_codes = [tool["code"] for tool in homepage_pages[1]]

        self.assertEqual("M19", tools[0]["code"])
        self.assertEqual("M18", tools[1]["code"])
        self.assertEqual("M17", tools[2]["code"])
        self.assertEqual("M15", tools[3]["code"])
        self.assertEqual(codes[codes.index("M06") : codes.index("M06") + 3], ["M06", "M16", "M05"])
        self.assertTrue(tools[codes.index("M16")]["blocked"])
        self.assertTrue(tools[codes.index("M05")]["blocked"])
        self.assertNotIn("M16", page1_codes)
        self.assertIn("M16", page2_codes)
        self.assertEqual(["M19", "M18", "M17", "M15", "M14", "M13", "M11", "M10", "M09"], page1_codes)
        self.assertEqual(["M08", "M07", "M06", "M16", "M05", "M04", "M03", "M02", "M01"], page2_codes)


if __name__ == "__main__":
    unittest.main()
