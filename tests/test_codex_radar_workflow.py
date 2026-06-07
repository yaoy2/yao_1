import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "codex-radar.yml"


class CodexRadarWorkflowTest(unittest.TestCase):
    def test_radar_workflow_syncs_main_before_writing_data(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        sync_index = workflow.index("git pull --ff-only origin main")
        run_index = workflow.index("python -m codex_radar_lite.cli")

        self.assertLess(sync_index, run_index)

    def test_radar_workflow_rebases_before_push_and_skips_empty_push(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        no_change_index = workflow.index("No radar data changes to commit.")
        rebase_index = workflow.index("git pull --rebase origin main")
        push_index = workflow.index("git push")

        self.assertLess(no_change_index, push_index)
        self.assertLess(rebase_index, push_index)


if __name__ == "__main__":
    unittest.main()
