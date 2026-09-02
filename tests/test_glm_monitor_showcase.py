import ast
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "22_23_glm_monitor.py"


class GlmMonitorShowcaseTest(unittest.TestCase):
    def test_m23_page_renders_the_monitoring_flow_without_controls(self):
        app = AppTest.from_file(str(PAGE), default_timeout=10)
        app.run()

        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual("M23 · GLM 促销雷达", app.title[0].value)
        rendered = "\n".join(item.value for item in app.markdown)
        for text in ("Docker", "官方渠道", "去重", "钉钉", "只读展示"):
            self.assertIn(text, rendered)
        self.assertNotIn("Windows 桌面通知", rendered)
        self.assertNotIn("每小时扫描", rendered)
        self.assertEqual(1, len(app.sidebar.markdown))
        self.assertEqual(["回到主页"], [button.label for button in app.button])
        self.assertFalse(app.text_input)
        self.assertFalse(app.selectbox)
        self.assertFalse(app.checkbox)
        self.assertFalse(app.file_uploader)

    def test_m23_page_cannot_import_or_invoke_operational_dependencies(self):
        tree = ast.parse(PAGE.read_text(encoding="utf-8"))
        imported_roots = set()
        called_names = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    called_names.add(f"{node.func.value.id}.{node.func.attr}")
                elif isinstance(node.func, ast.Name):
                    called_names.add(node.func.id)

        self.assertEqual({"streamlit", "utils"}, imported_roots)
        self.assertIn("render_home_link()", PAGE.read_text(encoding="utf-8"))
        self.assertNotIn("include_sidebar", PAGE.read_text(encoding="utf-8"))
        self.assertTrue(
            called_names.issubset(
                {
                    "st.set_page_config",
                    "render_home_link",
                    "st.markdown",
                    "st.title",
                    "st.expander",
                }
            ),
            called_names,
        )


if __name__ == "__main__":
    unittest.main()
