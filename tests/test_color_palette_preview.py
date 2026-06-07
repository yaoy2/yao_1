import importlib.util
from pathlib import Path
import unittest


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "02_9_palette.py"


def load_page_module():
    spec = importlib.util.spec_from_file_location("color_palette_preview", PAGE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ColorPalettePreviewTest(unittest.TestCase):
    def test_render_palette_showcase_combines_mood_and_library_details(self):
        page = load_page_module()
        palette = {
            "id": 7,
            "name": "复古红棕",
            "pairs": [
                {"name": "檀木红棕", "hex": "#592E2E"},
                {"name": "豆沙禁色", "hex": "#C89C85"},
                {"name": "奶雾暖白", "hex": "#F7F0EB"},
            ],
            "colors": ["#592E2E", "#C89C85", "#F7F0EB"],
            "scene": "皮具、复古穿搭、酒水品牌",
            "source": "微信公众号",
        }

        html = page.render_palette_showcase(palette)

        self.assertIn("高级感配色", html)
        self.assertIn("复古红棕", html)
        self.assertIn("主色", html)
        self.assertIn("辅助色", html)
        self.assertIn("背景色", html)
        self.assertIn("标题 / 大面积背景 / 高级感主体", html)
        self.assertIn("PPT 标题条", html)
        self.assertIn("#592E2E", html)
        self.assertIn("#C89C85", html)
        self.assertIn("#F7F0EB", html)

    def test_page_uses_supported_html_renderer(self):
        page_source = PAGE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("streamlit.components.v1", page_source)
        self.assertNotIn("components.html", page_source)
        self.assertIn("st.html(render_palette_showcase(pal))", page_source)


if __name__ == "__main__":
    unittest.main()
