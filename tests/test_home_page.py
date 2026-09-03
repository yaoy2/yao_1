import ast
import re
import unittest
from pathlib import Path
from urllib.parse import quote


def load_homepage_bits():
    page_source = (Path(__file__).resolve().parents[1] / "hello.py").read_text(encoding="utf-8")
    module = ast.parse(page_source)
    names = {
        "TOOLS",
        "get_homepage_tools",
        "get_homepage_pages",
        "sort_tool_key",
        "tools_for_section",
        "HOME_SECTIONS",
        "build_streamlit_page_href",
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
    namespace = {"Path": Path, "re": re, "quote": quote}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(Path("hello.py")), "exec"), namespace)
    return page_source, namespace


class HomePageTest(unittest.TestCase):
    def test_home_page_uses_apple_shell_not_command_center(self):
        page_source = (Path(__file__).resolve().parents[1] / "hello.py").read_text(encoding="utf-8")
        theme_source = (Path(__file__).resolve().parents[1] / "utils" / "ui_theme.py").read_text(encoding="utf-8")
        streamlit_config = (Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text(encoding="utf-8")

        self.assertNotIn("principle-chip", page_source)
        self.assertNotIn("command-hero", page_source)
        self.assertNotIn("工具矩阵预览", page_source)
        self.assertIn("apply_home_theme", page_source)
        self.assertIn("Don't worry. Be happy.", page_source)
        self.assertIn("lead-playful", page_source)
        self.assertIn("Fredoka", page_source)
        self.assertIn("apple-home", page_source)
        self.assertIn("nav-flyout", page_source)
        self.assertIn("build_streamlit_page_href", page_source)
        self.assertIn("tools_for_section", page_source)
        self.assertIn("locked", page_source)
        self.assertIn("build_tool_status_icon_html", page_source)
        self.assertIn("tool-lock", page_source)
        self.assertIn("tool-blocked", page_source)
        self.assertIn('target="_self"', page_source)
        self.assertIn("quote-strip", page_source)
        self.assertIn("def apply_home_theme", theme_source)
        self.assertIn("from utils.home_theme import apply_home_theme", page_source)
        from utils.home_theme import apply_home_theme as imported_home_theme
        self.assertTrue(callable(imported_home_theme))
        self.assertIn("render_sidebar_nav()", theme_source)
        self.assertIn("_load_homepage_tools", theme_source)
        self.assertIn("hello.py", theme_source)
        self.assertIn("showSidebarNavigation = false", streamlit_config)
        self.assertNotIn("st.button", page_source)
        self.assertNotIn("st.switch_page", page_source)
        self.assertNotIn("st.page_link", page_source)

    def test_tools_are_module_number_sorted_with_highest_module_first(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["get_homepage_tools"](namespace["TOOLS"])
        by_code = {tool["code"]: tool for tool in tools}
        codes = [tool["code"] for tool in tools]

        self.assertEqual("M23", tools[0]["code"])
        self.assertEqual("pages/22_23_docker_monitor.py", tools[0]["page"])
        self.assertEqual("M22", tools[1]["code"])
        self.assertEqual("pages/21_22_gpt_planner_luna_executor.py", tools[1]["page"])
        self.assertEqual("M21", tools[2]["code"])
        self.assertEqual("pages/20_21_awesome_design_md.py", tools[2]["page"])
        self.assertEqual("M20", tools[3]["code"])
        self.assertEqual("pages/19_20_ding2026.py", by_code["M20"]["page"])
        self.assertEqual("M19", tools[4]["code"])
        self.assertEqual("pages/18_19_concept_fables.py", by_code["M19"]["page"])
        self.assertEqual("M18", tools[5]["code"])
        self.assertEqual("pages/17_18_grade_workbench_guide.py", by_code["M18"]["page"])
        self.assertEqual("M17", tools[6]["code"])
        self.assertEqual("pages/16_17_grade_workbench.py", by_code["M17"]["page"])
        self.assertEqual("M15", tools[7]["code"])
        self.assertEqual("pages/15_0_email_notice.py", by_code["M15"]["page"])
        self.assertTrue(by_code["M14"]["locked"])
        self.assertEqual(codes[codes.index("M06") : codes.index("M06") + 3], ["M06", "M16", "M13"])
        self.assertEqual("pages/15_16_report_grader.py", by_code["M16"]["page"])
        self.assertTrue(by_code["M16"]["blocked"])
        self.assertTrue(by_code["M13"]["blocked"])
        blocked_codes = {tool["code"] for tool in tools if tool.get("blocked")}
        self.assertEqual({"M01", "M02", "M03", "M04", "M05", "M13", "M16"}, blocked_codes)
        self.assertEqual("M01", tools[-1]["code"])
        self.assertEqual(22, len(tools))

    def test_homepage_sections_match_approved_apple_nav(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["TOOLS"]
        by_code = {tool["code"]: tool for tool in tools}
        self.assertEqual(["行政", "教学", "个人", "archived"], list(namespace["HOME_SECTIONS"]))
        self.assertEqual("行政", by_code["M15"]["section"])
        self.assertEqual("行政", by_code["M14"]["section"])
        self.assertEqual("行政", by_code["M11"]["section"])
        self.assertEqual("行政", by_code["M08"]["section"])
        self.assertEqual("行政", by_code["M06"]["section"])
        self.assertEqual("行政", by_code["M20"]["section"])
        self.assertEqual("教学", by_code["M17"]["section"])
        self.assertEqual("教学", by_code["M18"]["section"])
        self.assertEqual("个人", by_code["M19"]["section"])
        self.assertEqual("个人", by_code["M10"]["section"])
        self.assertEqual("个人", by_code["M09"]["section"])
        self.assertEqual("个人", by_code["M07"]["section"])
        self.assertEqual("个人", by_code["M21"]["section"])
        self.assertEqual("个人", by_code["M22"]["section"])
        self.assertEqual("个人", by_code["M23"]["section"])
        self.assertEqual("archived", by_code["M13"]["section"])
        admin_codes = [tool["code"] for tool in namespace["tools_for_section"](tools, "行政")]
        teaching_codes = [tool["code"] for tool in namespace["tools_for_section"](tools, "教学")]
        archived_codes = [tool["code"] for tool in namespace["tools_for_section"](tools, "archived")]
        self.assertEqual(["M20", "M15", "M14", "M11", "M08", "M06"], admin_codes)
        self.assertEqual(["M18", "M17"], teaching_codes)
        self.assertIn("M13", archived_codes)
        self.assertNotIn("M13", admin_codes)
        self.assertNotIn("M13", [tool["code"] for tool in namespace["tools_for_section"](tools, "个人")])
        self.assertEqual("/20_ding2026", namespace["build_streamlit_page_href"]("pages/19_20_ding2026.py"))

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

        self.assertEqual("M23", tools[0]["code"])
        self.assertEqual("M22", tools[1]["code"])
        self.assertEqual("M21", tools[2]["code"])
        self.assertEqual("M20", tools[3]["code"])
        self.assertEqual("M19", tools[4]["code"])
        self.assertEqual("M18", tools[5]["code"])
        self.assertEqual("M17", tools[6]["code"])
        self.assertEqual(codes[codes.index("M06") : codes.index("M06") + 3], ["M06", "M16", "M13"])
        self.assertTrue(tools[codes.index("M16")]["blocked"])
        self.assertTrue(tools[codes.index("M13")]["blocked"])
        self.assertTrue(tools[codes.index("M05")]["blocked"])
        self.assertNotIn("M16", page1_codes)
        self.assertNotIn("M13", page1_codes)
        self.assertIn("M16", page2_codes)
        self.assertIn("M13", page2_codes)
        self.assertEqual(["M23", "M22", "M21", "M20", "M19", "M18", "M17", "M15", "M14"], page1_codes)
        self.assertEqual(["M11", "M10", "M09", "M08", "M07", "M06", "M16", "M13", "M05"], page2_codes)
        self.assertEqual(["M04", "M03", "M02", "M01"], [tool["code"] for tool in homepage_pages[2]])


if __name__ == "__main__":
    unittest.main()
