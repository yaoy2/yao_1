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

    def test_tools_are_module_number_sorted_with_grade_guide_first(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["get_homepage_tools"](namespace["TOOLS"])

        self.assertEqual("M18", tools[0]["code"])
        self.assertEqual("pages/17_18_grade_workbench_guide.py", tools[0]["page"])
        self.assertEqual("M17", tools[1]["code"])
        self.assertEqual("pages/16_17_grade_workbench.py", tools[1]["page"])
        self.assertEqual("M16", tools[2]["code"])
        self.assertEqual("pages/15_16_report_grader.py", tools[2]["page"])
        self.assertTrue(tools[2]["blocked"])
        self.assertEqual("M15", tools[3]["code"])
        self.assertEqual("pages/15_0_email_notice.py", tools[3]["page"])
        self.assertEqual("M14", tools[4]["code"])
        self.assertTrue(tools[4]["locked"])
        self.assertEqual("M13", tools[5]["code"])
        self.assertEqual("M12", tools[6]["code"])
        self.assertTrue(tools[6]["blocked"])
        blocked_codes = {tool["code"] for tool in tools if tool.get("blocked")}
        self.assertEqual({"M01", "M02", "M03", "M04", "M05", "M12", "M16"}, blocked_codes)
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

        module_numbers = [int(tool["code"].removeprefix("M")) for tool in tools]
        self.assertEqual(sorted(module_numbers, reverse=True), module_numbers)
        self.assertFalse(Path(tools[0]["page"]).name.startswith("00_"))

    def test_homepage_keeps_blocked_cards_in_module_number_order(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["get_homepage_tools"](namespace["TOOLS"])
        homepage_pages = namespace["get_homepage_pages"](namespace["TOOLS"])

        self.assertEqual("M18", tools[0]["code"])
        self.assertEqual("M17", tools[1]["code"])
        self.assertEqual("M16", tools[2]["code"])
        self.assertTrue(tools[2]["blocked"])
        self.assertEqual("M15", tools[3]["code"])
        self.assertEqual("M14", tools[4]["code"])
        self.assertEqual("M13", tools[5]["code"])
        self.assertEqual("M12", tools[6]["code"])
        self.assertTrue(tools[6]["blocked"])
        self.assertEqual("M09", tools[9]["code"])
        self.assertEqual("M08", tools[10]["code"])
        self.assertEqual("M05", tools[13]["code"])
        self.assertTrue(tools[13]["blocked"])
        self.assertEqual(["M18", "M17", "M16", "M15", "M14", "M13", "M12", "M11", "M10"], [tool["code"] for tool in homepage_pages[0]])
        self.assertEqual(["M09", "M08", "M07", "M06", "M05", "M04", "M03", "M02", "M01"], [tool["code"] for tool in homepage_pages[1]])


if __name__ == "__main__":
    unittest.main()
