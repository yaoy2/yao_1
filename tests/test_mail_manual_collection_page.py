"""Manual collection UI checks with no server, mailbox, or remote writes."""

import copy
import importlib.util
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "23_24_mail_workbench.py"
SPEC = importlib.util.spec_from_file_location("mail_manual_collection_page", PAGE_PATH)
page = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(page)


def loaded_fixture(collection=None, *, version="before", source="github"):
    snapshot = {
        "account": "test@example.invalid", "updated_at": "2026-09-09T10:00:00+08:00",
        "coverage": {}, "runs": [], "reports": [],
        "messages": [{"id": "m1", "subject": "保留原有邮件", "sender": "测试部门",
                      "received_at": "2026-09-08T09:00:00+08:00", "attachments": []}],
        "actions": [{"id": "a1", "message_id": "m1", "title": "保留原有事项", "status": "pending"}],
    }
    if collection is not None:
        snapshot["manual_collection"] = collection
    return {"snapshot": snapshot, "version": version, "source": source}


def collection_fixture(status="pending", phase="queued", **extras):
    return {"request_id": "a" * 32, "requested_at": "2026-09-09T10:00:00+08:00",
            "updated_at": "2026-09-09T10:00:00+08:00", "status": status, "phase": phase, **extras}


class ManualCollectionPageTests(unittest.TestCase):
    def callback_state(self, loaded=None):
        return {"mail_loaded": loaded or loaded_fixture(), "mail_authenticated": True,
                "mail_action_drafts": {"a1": "done"}, "mail_message_drafts": {"m2": "no_action"},
                "mail_status_a1": "done", "mail_message_status_m2": "no_action"}

    def run_callback(self, state, gateway, expected_version="before", password="fixture-password"):
        fake_st = SimpleNamespace(session_state=state, secrets={"budget_password": password})
        with patch.object(page, "st", fake_st), \
                patch.object(page.budget_auth, "get_budget_password", return_value=password):
            page.request_collection(gateway, expected_version)

    def test_callback_submits_fixed_request_once_and_keeps_all_drafts(self):
        state = self.callback_state()
        saved = loaded_fixture(collection_fixture(), version="queued")
        gateway = SimpleNamespace(request_collection=Mock(return_value=saved))
        self.run_callback(state, gateway)
        gateway.request_collection.assert_called_once()
        call = gateway.request_collection.call_args
        self.assertEqual((), call.args)
        self.assertEqual({"expected_version", "secrets", "environ"}, set(call.kwargs))
        self.assertEqual("before", call.kwargs["expected_version"])
        self.assertIs(saved, state["mail_loaded"])
        self.assertEqual({"a1": "done"}, state["mail_action_drafts"])
        self.assertEqual({"m2": "no_action"}, state["mail_message_drafts"])
        self.assertEqual("done", state["mail_status_a1"])
        self.assertNotIn("已完成", state["mail_save_notice"])
        self.run_callback(state, gateway, expected_version="queued")
        gateway.request_collection.assert_called_once()
        self.assertEqual(page.COLLECTION_BUSY_MESSAGE, state["mail_collection_error"])

    def test_permission_version_and_busy_checks_block_remote_writes(self):
        cases = [
            {"authenticated": False}, {"password": None}, {"source": "local"},
            {"version": "stale"}, {"version": ""},
            {"collection": collection_fixture()},
            {"collection": collection_fixture("running", "reviewing")},
        ]
        for case in cases:
            with self.subTest(case=case):
                loaded = loaded_fixture(case.get("collection"), source=case.get("source", "github"))
                state = self.callback_state(loaded)
                state["mail_authenticated"] = case.get("authenticated", True)
                gateway = SimpleNamespace(request_collection=Mock())
                self.run_callback(state, gateway, expected_version=case.get("version", "before"),
                                  password=case.get("password", "fixture-password"))
                gateway.request_collection.assert_not_called()
                self.assertIs(loaded, state["mail_loaded"])
                self.assertEqual({"a1": "done"}, state["mail_action_drafts"])
                self.assertTrue(state["mail_collection_error"])

    def test_failure_and_invalid_response_preserve_snapshot_and_hide_private_details(self):
        private_detail = "private.example.invalid Bearer secret-value"
        failure = RuntimeError(private_detail)
        conflict = RuntimeError(private_detail)
        conflict.code = "conflict"
        busy = RuntimeError(private_detail)
        busy.code = "collection_busy"
        for response in (failure, conflict, busy, None, {"snapshot": {}, "version": "bad"},
                         loaded_fixture(collection_fixture("success", "complete"), version="bad"),
                         loaded_fixture(collection_fixture(request_id="unsafe"), version="bad")):
            with self.subTest(response=response):
                state = self.callback_state()
                original = state["mail_loaded"]
                old_drafts = copy.deepcopy({key: value for key, value in state.items() if "drafts" in key})
                request = Mock(side_effect=response) if isinstance(response, Exception) else Mock(return_value=response)
                self.run_callback(state, SimpleNamespace(request_collection=request))
                self.assertIs(original, state["mail_loaded"])
                for key, value in old_drafts.items():
                    self.assertEqual(value, state[key])
                self.assertNotIn(private_detail, state["mail_collection_error"])
                self.assertNotIn("mail_save_notice", state)

    def test_refresh_only_reads_snapshot_and_clears_resolved_request_error(self):
        state = self.callback_state()
        state["mail_collection_error"] = "此前未能确认提交"
        saved = loaded_fixture(collection_fixture(), version="latest")
        gateway = SimpleNamespace(load_snapshot=Mock(return_value=saved), request_collection=Mock())
        with patch.object(page, "st", SimpleNamespace(session_state=state, secrets={})):
            self.assertIs(saved, page.refresh_snapshot(gateway))
        gateway.load_snapshot.assert_called_once()
        gateway.request_collection.assert_not_called()
        self.assertEqual({"a1": "done"}, state["mail_action_drafts"])
        self.assertNotIn("mail_collection_error", state)

    def test_progress_never_calls_collection_or_ai_alone_complete(self):
        for status, phase in (("pending", "queued"), ("running", "collecting"),
                              ("running", "reviewing"), ("running", "syncing"),
                              ("success", "reviewing"), ("success", "syncing")):
            with self.subTest(status=status, phase=phase):
                text = page.collection_progress({"manual_collection": collection_fixture(status, phase)})
                self.assertNotIn("已完成", text)
        pending = page.collection_progress({"manual_collection": collection_fixture()})
        self.assertIn("离线", pending)
        self.assertIn("等待", pending)
        completed = page.collection_progress({"manual_collection": collection_fixture(
            "success", "complete", message_count=4, new_message_count=0, action_count=2)})
        self.assertIn("收信、AI 整理及同步已完成", completed)
        self.assertIn("新增 0 封", completed)

    def test_failure_labels_are_fixed_and_do_not_render_remote_exception_text(self):
        from utils.mail_collection_state import COLLECTION_ERROR_CODES

        self.assertEqual(COLLECTION_ERROR_CODES, set(page.COLLECTION_ERROR_LABELS))
        for status in ("partial", "error"):
            text = page.collection_progress({"manual_collection": collection_fixture(
                status, "complete", error_code="REVIEW_TIMEOUT")})
            self.assertIn("AI 整理超时", text)
            self.assertNotIn("已完成", text)
        text = page.collection_progress({"manual_collection": collection_fixture(
            "error", "complete", error_code="Bearer private-value <img>")})
        self.assertNotIn("private-value", text)
        self.assertIn("待接收电脑核对", text)

    def test_hot_deploy_refreshes_gateway_without_request_api(self):
        gateway = page.get_mail_gateway()
        original = gateway.request_collection
        try:
            del gateway.request_collection
            self.assertTrue(callable(page.get_mail_gateway().request_collection))
        finally:
            gateway.request_collection = original


class ManualCollectionAppTests(unittest.TestCase):
    def prepare_app(self, stack, *, collection=None, authenticated=True, source="github"):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(PAGE_PATH))
        app.session_state["mail_loaded"] = loaded_fixture(collection, source=source)
        app.session_state["mail_authenticated"] = authenticated
        gateway = page.get_mail_gateway()
        stack.enter_context(patch.object(page.budget_auth, "get_budget_password", return_value="fixture-password"))
        load = stack.enter_context(patch.object(gateway, "load_snapshot", side_effect=AssertionError("No real mail reads")))
        request = stack.enter_context(patch.object(gateway, "request_collection", side_effect=AssertionError("No real writes")))
        save = stack.enter_context(patch.object(gateway, "save_action_updates", side_effect=AssertionError("No state writes")))
        save_mail = stack.enter_context(patch.object(gateway, "save_message_updates", side_effect=AssertionError("No state writes")))
        return app, load, request, save, save_mail

    def test_render_then_click_submits_once_without_changing_existing_cards(self):
        with ExitStack() as stack:
            app, load, request, save, save_mail = self.prepare_app(stack)
            request.side_effect = None
            request.return_value = loaded_fixture(collection_fixture(), version="queued")
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
            request.assert_not_called()
            load.assert_not_called()
            self.assertFalse(app.button(key="mail_request_collection").disabled)
            self.assertTrue(any("保留原有邮件" in el.value for el in app.tabs[0].markdown))
            app.button(key="mail_request_collection").click().run(timeout=15)
            self.assertEqual([], list(app.exception))
            request.assert_called_once()
            self.assertTrue(app.button(key="mail_request_collection").disabled)
            self.assertTrue(any("已排队" in el.value for el in app.caption))
            self.assertEqual("pending", app.session_state["mail_loaded"]["snapshot"]["actions"][0]["status"])
            app.run(timeout=15)
            request.assert_called_once()
            save.assert_not_called()
            save_mail.assert_not_called()

    def test_refresh_button_reads_synced_result_without_triggering_collection(self):
        with ExitStack() as stack:
            app, load, request, _, _ = self.prepare_app(stack, collection=collection_fixture("running", "reviewing"))
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
            self.assertTrue(app.button(key="mail_request_collection").disabled)
            self.assertTrue(any("AI 整理" in el.value and "尚未同步完成" in el.value for el in app.caption))
            load.side_effect = None
            load.return_value = loaded_fixture(collection_fixture("success", "complete"), version="complete")
            refresh = next(button for button in app.button if button.label == "刷新")
            self.assertIn("不会启动收信", refresh.help)
            refresh.click().run(timeout=15)
            self.assertEqual([], list(app.exception))
            load.assert_called_once()
            request.assert_not_called()
            self.assertFalse(app.button(key="mail_request_collection").disabled)
            self.assertTrue(any("收信、AI 整理及同步已完成" in el.value for el in app.caption))
            self.assertFalse(any("计划时间" in el.value for el in app.caption))

    def test_public_and_local_views_disable_collection(self):
        for authenticated, source in ((False, "github"), (True, "local")):
            with self.subTest(authenticated=authenticated, source=source), ExitStack() as stack:
                app, _, request, _, _ = self.prepare_app(stack, authenticated=authenticated, source=source)
                app.run(timeout=15)
                self.assertEqual([], list(app.exception))
                self.assertTrue(app.button(key="mail_request_collection").disabled)
                request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
