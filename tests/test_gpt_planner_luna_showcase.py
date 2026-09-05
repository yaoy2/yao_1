import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "21_22_gpt_planner_luna_executor.py"


class GptPlannerLunaShowcaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = AppTest.from_file(str(PAGE), default_timeout=10).run()

    def test_public_skill_source_is_bundled_with_the_repository(self):
        for skill in ("gpt-planner-luna-executor", "codex-grok-builder"):
            with self.subTest(skill=skill):
                self.assertTrue((ROOT / skill / "SKILL.md").is_file())
                self.assertTrue((ROOT / skill / "agents" / "openai.yaml").is_file())
        self.assertTrue(
            (ROOT / "gpt-planner-luna-executor" / "references" / "packet-protocol.md").is_file()
        )
        self.assertTrue((ROOT / "codex-grok-builder" / "scripts" / "invoke-grok.ps1").is_file())

    def test_rendered_page_explains_both_routes_and_evidence_limits(self):
        rendered = "\n".join(item.value for item in self.app.markdown)
        self.assertIn("我做了一套“会分工”的 AI 开发流程", rendered)
        self.assertIn("GPT / LUNA", rendered)
        self.assertIn("CODEX / GROK", rendered)
        self.assertIn("总 token 不保证减少", rendered)
        self.assertIn("主控 + 交接 + 执行 + 返工 + 验收", rendered)
        self.assertIn("没有串成完整端到端运行", rendered)
        self.assertIn("没有“全程强模型”对照", rendered)
        self.assertIn("Grok 的方案、修改范围和测试命令审批保留", rendered)
        self.assertGreaterEqual(len(self.app.expander), 2)
        for skill in ("gpt-planner-luna-executor", "codex-grok-builder", "personal-skills"):
            self.assertIn(f"https://github.com/yaoy2/yao_1/tree/main/{skill}", rendered)

    def test_sample_table_preserves_results_and_distinct_timing_boundaries(self):
        self.assertEqual(1, len(self.app.dataframe))
        rows = self.app.dataframe[0].value.set_index("独立通道样本")
        self.assertEqual(["Luna 执行", "Grok 执行", "GPT 网页规划"], list(rows.index))
        for executor in ("Luna 执行", "Grok 执行"):
            with self.subTest(executor=executor):
                self.assertEqual("12/12", rows.loc[executor, "首轮验收"])
                self.assertEqual("0", rows.loc[executor, "修复次数"])
        self.assertEqual("约 22 秒 · 执行者报告", rows.loc["Luna 执行", "耗时（统计边界不同）"])
        self.assertEqual("50.319 秒 · CLI run", rows.loc["Grok 执行", "耗时（统计边界不同）"])
        self.assertEqual("94 秒 · 网页规划", rows.loc["GPT 网页规划", "耗时（统计边界不同）"])
        self.assertEqual("不适用（仅规划）", rows.loc["GPT 网页规划", "首轮验收"])

    def test_m22_page_renders_without_operational_controls(self):
        self.assertFalse(self.app.exception)
        self.assertFalse(self.app.error)
        self.assertEqual(["回到主页"], [button.label for button in self.app.button])
        for widget in (
            "text_input", "text_area", "chat_input", "number_input", "selectbox",
            "multiselect", "radio", "checkbox", "toggle", "slider", "select_slider",
            "date_input", "time_input", "file_uploader", "data_editor",
        ):
            with self.subTest(widget=widget):
                self.assertFalse(self.app.get(widget))


if __name__ == "__main__":
    unittest.main()
