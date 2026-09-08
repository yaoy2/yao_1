"""Whole-email status behavior using synthetic data and mocked gateways only."""

import copy
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "23_24_mail_workbench.py"
SPEC = importlib.util.spec_from_file_location("mail_group_status_page", PAGE_PATH)
page = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(page)


def loaded_fixture(child_count=12):
    messages = [{"id": identifier, "subject": subject, "sender": "合成测试部门", "category": "教学",
                 "received_at": "2026-09-08T08:00:00+08:00", "summary": "合成摘要", "attachments": []}
                for identifier, subject in (("group-mail", "包含多个事项的合成邮件"), ("other-mail", "另一封合成邮件"))]
    actions = [{"id": f"child-{index}", "message_id": "group-mail", "title": f"合成事项 {index}",
                "status": "needs_confirmation", "due_at": None}
               for index in range(child_count)]
    actions.append({"id": "other-action", "message_id": "other-mail", "title": "其他邮件事项",
                    "status": "pending", "due_at": None})
    return {"version": "fixture-old", "source": "github", "snapshot": {
        "account": "fixture@example.invalid", "updated_at": "2026-09-08T08:00:00+08:00",
        "coverage": {}, "runs": [], "reports": [], "messages": messages, "actions": actions}}


class GroupStatusCallbackTests(unittest.TestCase):
    def setUp(self):
        self.loaded = loaded_fixture()
        self.before = copy.deepcopy(self.loaded)
        self.drafts = {"other-action": "done", "removed-action": "no_action", "child-0": "pending"}
        self.state = {"mail_loaded": self.loaded, "mail_authenticated": True,
                      "mail_action_drafts": self.drafts, "parent-choice": "out_of_scope"}
        self.fake_st = SimpleNamespace(secrets={"budget_password": "synthetic-edit-password"}, session_state=self.state)
        self.gateway = SimpleNamespace(save_action_updates=Mock(), save_message_updates=Mock(), load_snapshot=Mock())
        patcher = patch.object(page, "st", self.fake_st)
        patcher.start()
        self.addCleanup(patcher.stop)
        password = patch.object(page.budget_auth, "get_budget_password", return_value="synthetic-edit-password")
        password.start()
        self.addCleanup(password.stop)

    def callback(self, expected_version="fixture-old", message_id="group-mail"):
        page.remember_group_status(message_id, "parent-choice", self.gateway, expected_version)

    def save_response(self, updates, **kwargs):
        # The old snapshot remains the authoritative UI state while saving.
        self.assertIs(self.loaded, self.state["mail_loaded"])
        self.assertEqual(self.before, self.loaded)
        saved = copy.deepcopy(self.loaded)
        saved["version"] = "fixture-new"
        for action in saved["snapshot"]["actions"]:
            if action["id"] in updates:
                action["status"] = updates[action["id"]]
        return saved

    def test_one_save_updates_all_twelve_children_and_preserves_unrelated_drafts(self):
        expected = {f"child-{index}": "out_of_scope" for index in range(12)}
        self.gateway.save_action_updates.side_effect = self.save_response
        actual_save, scopes = page.save_drafts, []

        def capture_scope(gateway, loaded, drafts):
            # save_drafts consumes successful edits, so capture before it runs.
            scopes.append(drafts.copy())
            return actual_save(gateway, loaded, drafts)

        with patch.object(page, "save_drafts", side_effect=capture_scope) as scoped_save:
            self.callback()
        scoped_save.assert_called_once()
        self.assertEqual([expected], scopes)
        self.gateway.save_action_updates.assert_called_once()
        self.assertEqual(expected, self.gateway.save_action_updates.call_args.args[0])
        self.assertEqual("fixture-old", self.gateway.save_action_updates.call_args.kwargs["expected_version"])
        self.gateway.save_message_updates.assert_not_called()
        self.gateway.load_snapshot.assert_not_called()
        self.assertEqual(self.before, self.loaded)
        self.assertEqual("fixture-new", self.state["mail_loaded"]["version"])
        self.assertEqual({"other-action": "done", "removed-action": "no_action"}, self.drafts)
        self.assertEqual("pending", self.state["mail_loaded"]["snapshot"]["actions"][-1]["status"])
        self.assertEqual({"out_of_scope"}, {a["status"] for a in self.state["mail_loaded"]["snapshot"]["actions"][:-1]})
        self.assertIn("12", self.state["mail_save_notice"])
        self.assertNotIn("mail_save_error", self.state)

    def test_failure_keeps_every_child_choice_and_old_snapshot_without_leaking_error(self):
        self.gateway.save_action_updates.side_effect = RuntimeError("synthetic-private-backend-details")
        self.callback()
        self.gateway.save_action_updates.assert_called_once()
        self.assertEqual(self.before, self.loaded)
        self.assertIs(self.loaded, self.state["mail_loaded"])
        expected = {"other-action": "done", "removed-action": "no_action",
                    **{f"child-{index}": "out_of_scope" for index in range(12)}}
        self.assertEqual(expected, self.drafts)
        self.assertIn("mail_save_error", self.state)
        self.assertNotIn("synthetic-private", self.state["mail_save_error"])
        self.assertNotIn("mail_save_notice", self.state)

    def test_invalid_save_response_keeps_all_drafts_until_a_valid_snapshot_arrives(self):
        self.gateway.save_action_updates.return_value = {"snapshot": []}
        self.callback()
        self.assertIs(self.loaded, self.state["mail_loaded"])
        self.assertEqual(self.before, self.loaded)
        self.assertEqual("fixture-old", self.state["mail_loaded"]["version"])
        self.assertEqual(14, len(self.drafts))
        self.assertTrue(all(self.drafts[f"child-{index}"] == "out_of_scope" for index in range(12)))
        self.assertIn("mail_save_error", self.state)

    def test_stale_version_preserves_choices_and_blocks_remote_write(self):
        self.callback(expected_version="stale-render")
        self.gateway.save_action_updates.assert_not_called()
        self.assertIs(self.loaded, self.state["mail_loaded"])
        self.assertEqual(self.before, self.loaded)
        self.assertEqual(page.ERRORS["conflict"], self.state["mail_save_error"])
        self.assertTrue(all(self.drafts[f"child-{index}"] == "out_of_scope" for index in range(12)))
        self.assertEqual("done", self.drafts["other-action"])

    def test_unauthenticated_or_local_view_blocks_remote_write(self):
        for authenticated, source in ((False, "github"), (True, "local")):
            with self.subTest(authenticated=authenticated, source=source):
                self.state["mail_authenticated"] = authenticated
                self.loaded["source"] = source
                baseline = copy.deepcopy(self.loaded)
                self.callback()
                self.gateway.save_action_updates.assert_not_called()
                self.assertEqual(baseline, self.loaded)
                self.assertIn("mail_save_error", self.state)
                self.assertTrue(all(self.drafts[f"child-{index}"] == "out_of_scope" for index in range(12)))

    def test_removed_password_configuration_blocks_parent_save(self):
        with patch.object(page.budget_auth, "get_budget_password", return_value=None):
            self.callback()
        self.gateway.save_action_updates.assert_not_called()
        self.assertEqual(self.before, self.loaded)
        self.assertIn("mail_save_error", self.state)

    def test_mixed_sentinel_or_invalid_status_is_never_saved_or_put_into_drafts(self):
        before_drafts = self.drafts.copy()
        for value in ("__mixed__", "invalid-status", None):
            with self.subTest(value=value):
                self.state["parent-choice"] = value
                self.callback()
                self.gateway.save_action_updates.assert_not_called()
                self.assertEqual(before_drafts, self.drafts)
                self.assertEqual(self.before, self.loaded)

    def test_missing_message_does_not_update_other_mail(self):
        before_drafts = self.drafts.copy()
        self.callback(message_id="removed-message")
        self.gateway.save_action_updates.assert_not_called()
        self.assertEqual(before_drafts, self.drafts)
        self.assertEqual(self.before, self.loaded)
        self.assertIn("mail_save_error", self.state)

    def test_noop_parent_choice_clears_only_its_stale_drafts_without_remote_call(self):
        self.state["parent-choice"] = "needs_confirmation"
        self.callback()
        self.gateway.save_action_updates.assert_not_called()
        self.assertEqual({"other-action": "done", "removed-action": "no_action"}, self.drafts)
        self.assertEqual(self.before, self.loaded)
        self.assertNotIn("mail_save_error", self.state)


class GroupStatusControlTests(unittest.TestCase):
    def render(self, statuses, *, authenticated=True, source="github", drafts=None, context="inbox"):
        loaded = loaded_fixture(len(statuses))
        loaded["source"] = source
        actions = loaded["snapshot"]["actions"][:-1]
        for action, status in zip(actions, statuses):
            action["status"] = status
        state = {"mail_authenticated": authenticated, "mail_action_drafts": drafts or {}}
        ui = SimpleNamespace(session_state=state, selectbox=Mock(), caption=Mock())
        gateway = SimpleNamespace(save_action_updates=Mock())
        with patch.object(page, "st", ui):
            page.render_group_status_control(loaded["snapshot"]["messages"][0], actions, loaded, gateway, context=context)
        ui.selectbox.assert_called_once()
        gateway.save_action_updates.assert_not_called()
        return ui, ui.selectbox.call_args, gateway

    def test_uniform_parent_shows_six_decisions_and_callback_is_scoped_to_mail(self):
        ui, call, gateway = self.render(["pending"] * 12)
        self.assertEqual("整封邮件判断", call.args[0])
        self.assertEqual(list(page.INBOX_STATUSES), call.args[1])
        key = call.kwargs["key"]
        self.assertEqual("pending", ui.session_state[key])
        self.assertFalse(call.kwargs["disabled"])
        self.assertIs(page.remember_group_status, call.kwargs["on_change"])
        self.assertEqual(("group-mail", key, gateway, "fixture-old"), call.kwargs["args"])
        self.assertIn("12", call.kwargs["format_func"]("pending"))
        self.assertIn(page.INBOX_STATUSES["pending"], call.kwargs["format_func"]("pending"))

    def test_mixed_children_show_nonpersistable_sentinel_and_all_six_choices(self):
        ui, call, _ = self.render(["pending", "done"])
        self.assertEqual("__mixed__", ui.session_state[call.kwargs["key"]])
        self.assertEqual(["__mixed__", *page.INBOX_STATUSES], call.args[1])
        self.assertIn("状态不同", call.kwargs["format_func"]("__mixed__"))

    def test_unsaved_child_choices_are_reflected_for_editor(self):
        ui, call, _ = self.render(["pending", "pending"], drafts={"child-0": "done", "child-1": "done"})
        self.assertEqual("done", ui.session_state[call.kwargs["key"]])
        self.assertTrue(ui.caption.called)

    def test_readonly_control_is_disabled_and_displays_saved_state(self):
        for authenticated, source in ((False, "github"), (True, "local")):
            with self.subTest(authenticated=authenticated, source=source):
                ui, call, _ = self.render(["pending", "pending"], authenticated=authenticated,
                                          source=source, drafts={"child-0": "done", "child-1": "done"})
                self.assertTrue(call.kwargs["disabled"])
                self.assertEqual("pending", ui.session_state[call.kwargs["key"]])

    def test_same_mail_in_different_contexts_has_distinct_widget_keys(self):
        _, first, _ = self.render(["pending", "pending"], context="inbox")
        _, second, _ = self.render(["pending", "pending"], context="report")
        self.assertNotEqual(first.kwargs["key"], second.kwargs["key"])


class GroupStatusAppTests(unittest.TestCase):
    def test_parent_selection_updates_twelve_children_and_keeps_other_mail_draft(self):
        from streamlit.testing.v1 import AppTest

        loaded = loaded_fixture()
        for index, action in enumerate(loaded["snapshot"]["actions"][:-1]):
            action["status"] = "pending" if index % 2 else "needs_confirmation"
        original = copy.deepcopy(loaded)
        app = AppTest.from_file(str(PAGE_PATH))
        app.session_state["mail_loaded"] = loaded
        app.session_state["mail_authenticated"] = True
        app.session_state["mail_action_drafts"] = {"other-action": "done"}
        gateway = page.get_mail_gateway()
        expected = {f"child-{index}": "out_of_scope" for index in range(12)}

        def save(updates, **kwargs):
            self.assertEqual(expected, updates)
            self.assertEqual("fixture-old", kwargs["expected_version"])
            self.assertEqual(original, loaded)
            saved = copy.deepcopy(loaded)
            saved["version"] = "fixture-new"
            for action in saved["snapshot"]["actions"]:
                if action["id"] in updates:
                    action["status"] = updates[action["id"]]
            return saved

        with patch.object(page.budget_auth, "get_budget_password", return_value="synthetic-edit-password"), \
                patch.object(gateway, "load_snapshot", side_effect=AssertionError("Tests cannot read real mail")) as load, \
                patch.object(gateway, "save_action_updates", side_effect=save) as save_actions, \
                patch.object(gateway, "save_message_updates", side_effect=AssertionError("Tests cannot save message records")) as save_messages:
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
            parents = [control for control in app.tabs[0].selectbox if control.label == "整封邮件判断"]
            self.assertEqual(1, len(parents))
            self.assertEqual("__mixed__", parents[0].value)
            parents[0].set_value("out_of_scope")
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
        save_actions.assert_called_once()
        save_messages.assert_not_called()
        load.assert_not_called()
        self.assertEqual(original, loaded)
        self.assertEqual({"other-action": "done"}, app.session_state["mail_action_drafts"])
        saved = app.session_state["mail_loaded"]
        self.assertEqual("fixture-new", saved["version"])
        self.assertEqual({"out_of_scope"}, {a["status"] for a in saved["snapshot"]["actions"][:-1]})
        self.assertEqual("pending", saved["snapshot"]["actions"][-1]["status"])
        children = [control for control in app.tabs[0].selectbox
                    if control.label == "当前状态" and "_child-" in str(control.key)]
        self.assertEqual(12, len(children))
        self.assertEqual({"out_of_scope"}, {control.value for control in children})
        parent = next(control for control in app.tabs[0].selectbox if control.label == "整封邮件判断")
        self.assertEqual("out_of_scope", parent.value)


if __name__ == "__main__":
    unittest.main()
