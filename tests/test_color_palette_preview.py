import importlib.util
from pathlib import Path
import unittest


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "02_9、🎨_配色方案预览.py"


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
            "name": "夜空墨蓝",
            "pairs": [
                {"name": "夜幕蓝", "hex": "#162A46"},
                {"name": "香槟银", "hex": "#D8D0C1"},
                {"name": "珍珠白", "hex": "#F8F6F2"},
            ],
            "colors": ["#162A46", "#D8D0C1", "#F8F6F2"],
            "scene": "西装男装、星级会所",
            "source": "微信公众号",
        }

        html = page.render_palette_showcase(palette)

        self.assertIn("高级感配色", html)
        self.assertIn("夜空墨蓝", html)
        self.assertIn("主色", html)
        self.assertIn("辅助色", html)
        self.assertIn("背景色", html)
        self.assertIn("标题 / 大面积背景 / 高级感主体", html)
        self.assertIn("PPT 标题条", html)
        self.assertIn("#162A46", html)
        self.assertIn("#D8D0C1", html)
        self.assertIn("#F8F6F2", html)


if __name__ == "__main__":
    unittest.main()
