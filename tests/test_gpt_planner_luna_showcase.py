import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "21_22_gpt_planner_luna_executor.py"
SKILL_ROOT = ROOT / "gpt-planner-luna-executor"


class GptPlannerLunaShowcaseTest(unittest.TestCase):
    def test_public_skill_source_is_bundled_with_the_repository(self):
        self.assertTrue((SKILL_ROOT / "SKILL.md").is_file())
        self.assertTrue((SKILL_ROOT / "agents" / "openai.yaml").is_file())
        self.assertTrue((SKILL_ROOT / "references" / "packet-protocol.md").is_file())

    def test_m22_page_is_a_read_only_showcase(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("我做了一套“会分工”的 AI 开发流程", source)
        self.assertIn("让 GPT 去做", source)
        self.assertIn("git pull", source)
        self.assertIn("M22 只负责公开介绍", source)
        self.assertNotIn("st.button", source)
        self.assertNotIn("st.text_input", source)
        self.assertNotIn("st.selectbox", source)
        self.assertNotIn("subprocess", source)

    def test_m22_page_renders_without_operational_controls(self):
        app = AppTest.from_file(str(PAGE), default_timeout=10)
        app.run()

        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertFalse(app.text_input)
        self.assertFalse(app.selectbox)


if __name__ == "__main__":
    unittest.main()
