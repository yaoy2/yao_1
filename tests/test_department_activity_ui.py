"""Exercise autosave callbacks with ordinary state dictionaries; no app/server runs."""

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.test_department_activity import sample_budget, TODAY
from utils import department_activity as activity
from utils import department_activity_ui as ui


class InlineRosterAutosaveTest(unittest.TestCase):
    def setUp(self):
        data = activity.set_reimbursed_months(sample_budget(), [1, 3], TODAY)
        self.state = {
            "budget": {"data": data, "version": "v1", "source": "github"},
            "grid": activity.roster_editor_columns(data),
            "editor": {"edited_rows": {}, "added_rows": [], "deleted_rows": []},
        }
        fake_st = SimpleNamespace(session_state=self.state, secrets={}, rerun=Mock())
        self.st_patch = patch.object(ui, "st", fake_st)
        self.st_patch.start()
        self.addCleanup(self.st_patch.stop)

    def save_result(self, data, snapshot, **kwargs):
        return {"data": copy.deepcopy(data), "version": snapshot["version"] + "x", "source": "github"}

    def test_autosave_updates_metrics_before_render_without_resetting_editor(self):
        base = self.state["grid"]
        edits = self.state["editor"]
        edits["edited_rows"] = {0: {"9月": None}}
        with patch.object(activity, "save_budget", side_effect=self.save_result) as save:
            ui._autosave_roster("budget", "grid", "editor")
        self.assertEqual(1, save.call_count)
        self.assertEqual(270, activity.summarize(self.state["budget"]["data"], TODAY)["total"])
        self.assertEqual(180, activity.summarize(self.state["budget"]["data"], TODAY)["balance"])
        self.assertIs(base, self.state["grid"])
        self.assertIs(edits, self.state["editor"])
        self.assertNotIn("budget_draft", self.state)
        self.assertNotIn("budget_editor_error", self.state)
        ui.st.rerun.assert_not_called()

    def test_successive_changes_use_latest_saved_version_and_original_grid(self):
        self.state["editor"]["edited_rows"] = {0: {"9月": None}}
        with patch.object(activity, "save_budget", side_effect=self.save_result) as save:
            ui._autosave_roster("budget", "grid", "editor")
            self.state["editor"]["edited_rows"][1] = {"9月": "李四更名"}
            ui._autosave_roster("budget", "grid", "editor")
            ui._autosave_roster("budget", "grid", "editor")
        self.assertEqual(2, save.call_count)
        self.assertEqual("v1x", save.call_args_list[1].args[1]["version"])
        self.assertEqual(["李四更名", "王五", "赵六"], self.state["budget"]["data"]["months"]["9"])

    def test_save_failure_keeps_draft_and_base_for_retry(self):
        original = self.state["budget"]
        self.state["editor"]["edited_rows"] = {4: {"9月": "新教师"}}
        with patch.object(activity, "save_budget", side_effect=RuntimeError("远端数据已更新")):
            ui._autosave_roster("budget", "grid", "editor")
        self.assertIs(original, self.state["budget"])
        self.assertIn("远端数据已更新", self.state["budget_editor_error"])
        self.assertEqual(5, len(self.state["budget_draft"]["months"]["9"]))
        self.assertEqual({4: {"9月": "新教师"}}, self.state["editor"]["edited_rows"])
        with patch.object(activity, "save_budget", side_effect=self.save_result):
            ui._autosave_roster("budget", "grid", "editor")
        self.assertEqual(5, len(self.state["budget"]["data"]["months"]["9"]))
        self.assertNotIn("budget_editor_error", self.state)

    def test_blank_added_rows_do_not_generate_backup_commits(self):
        self.state["editor"]["added_rows"] = [{}]
        with patch.object(activity, "save_budget") as save:
            ui._autosave_roster("budget", "grid", "editor")
        save.assert_not_called()

    def test_reimbursement_save_keeps_inline_editor_basis(self):
        grid, edits = self.state["grid"], self.state["editor"]
        snapshot = self.state["budget"]
        updated = activity.set_reimbursed_months(snapshot["data"], [1, 2, 3], TODAY)
        with patch.object(activity, "save_budget", side_effect=self.save_result):
            ui._save(updated, snapshot, "budget")
        self.assertIs(grid, self.state["grid"])
        self.assertIs(edits, self.state["editor"])
        self.assertEqual([1, 2, 3], self.state["budget"]["data"]["reimbursed_months"])
        ui.st.rerun.assert_called_once()

    def test_returning_to_page_rebuilds_grid_from_saved_roster(self):
        self.state["editor"]["edited_rows"] = {0: {"9月": None}}
        with patch.object(activity, "save_budget", side_effect=self.save_result):
            ui._autosave_roster("budget", "grid", "editor")
        old_grid = self.state["grid"]
        self.assertIs(old_grid, ui._editor_base("budget", "grid", "editor"))
        self.state.pop("editor")  # What the app does after leaving this page.
        restored = ui._editor_base("budget", "grid", "editor")
        self.assertIsNot(old_grid, restored)
        self.assertEqual(["李四", "王五", "赵六"], restored["9月"][:3])
        self.state["editor"] = {"edited_rows": {0: {"9月": "更正李四"}}}
        with patch.object(activity, "save_budget", side_effect=self.save_result):
            ui._autosave_roster("budget", "grid", "editor")
        self.assertEqual(["更正李四", "王五", "赵六"], self.state["budget"]["data"]["months"]["9"])

    def test_returning_to_page_retains_failed_save_draft(self):
        self.state["editor"]["edited_rows"] = {4: {"9月": "新教师"}}
        with patch.object(activity, "save_budget", side_effect=RuntimeError("网络失败")):
            ui._autosave_roster("budget", "grid", "editor")
        self.state.pop("editor")
        restored = ui._editor_base("budget", "grid", "editor")
        self.assertEqual("新教师", restored["9月"][4])
        self.state["editor"] = {}
        with patch.object(activity, "save_budget", side_effect=self.save_result):
            ui._autosave_roster("budget", "grid", "editor")
        self.assertEqual(5, len(self.state["budget"]["data"]["months"]["9"]))
        self.assertNotIn("budget_editor_error", self.state)


if __name__ == "__main__":
    unittest.main()
