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

    def test_tools_are_metadata_sorted_with_todo_first(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["get_homepage_tools"](namespace["TOOLS"])

        self.assertEqual("待办清单", tools[0]["title"])
        self.assertEqual("M14", tools[0]["code"])
        self.assertEqual("pages/14_todos.py", tools[0]["page"])
        self.assertTrue(tools[0]["locked"])
        self.assertEqual("M13", tools[1]["code"])
        self.assertEqual("M11", tools[2]["code"])
        blocked_codes = {tool["code"] for tool in tools if tool.get("blocked")}
        self.assertEqual({"M01", "M02", "M03", "M04", "M05", "M12"}, blocked_codes)
        self.assertEqual("M01", tools[-1]["code"])
        self.assertEqual(14, len(tools))

    def test_homepage_order_is_metadata_driven_instead_of_filename_driven(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["get_homepage_tools"](namespace["TOOLS"])
        pages_dir = Path(__file__).resolve().parents[1] / "pages"

        actual_pages = [f"pages/{path.name}" for path in sorted(pages_dir.glob("*.py"))]
        self.assertIn("pages/14_todos.py", actual_pages)
        self.assertNotEqual([tool["page"] for tool in tools], actual_pages)

        active_tools = [tool for tool in tools if not tool.get("blocked")]
        active_sort_keys = [(tool["created"], int(tool["code"].removeprefix("M"))) for tool in active_tools]
        self.assertEqual(sorted(active_sort_keys, reverse=True), active_sort_keys)
        self.assertFalse(Path(tools[0]["page"]).name.startswith("00_"))

    def test_homepage_defers_red_x_cards_to_later_page(self):
        _page_source, namespace = load_homepage_bits()
        tools = namespace["get_homepage_tools"](namespace["TOOLS"])
        homepage_pages = namespace["get_homepage_pages"](namespace["TOOLS"])

        self.assertEqual("M14", tools[0]["code"])
        self.assertEqual("M01", tools[-1]["code"])
        self.assertEqual("M06", homepage_pages[0][-1]["code"])
        self.assertEqual(["M12", "M05", "M04", "M03", "M02", "M01"], [tool["code"] for tool in homepage_pages[1]])
        self.assertTrue(all(not tool.get("blocked") for tool in homepage_pages[0]))
        self.assertTrue(all(tool.get("blocked") for tool in homepage_pages[1]))


if __name__ == "__main__":
    unittest.main()
