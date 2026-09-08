"""Filing choices and progress are verified with synthetic mail and no I/O."""

import copy
import importlib.util
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "23_24_mail_workbench.py"
SPEC = importlib.util.spec_from_file_location("mail_filing_page", PAGE_PATH)
page = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(page)


def filing(status="pending", **fields):
    return {"request_id": "fixture-request", "requested_at": "2026-09-08T08:00:00+08:00",
            "updated_at": "2026-09-08T08:00:00+08:00", "status": status,
            "destination": "邮件存档/2026-09-08 合成通知", "saved_count": 0, "total_count": 2,
            "error_count": 0, "error_codes": [], **fields}


def loaded_fixture(*, filing_status="partial", no_actions=False):
    message = {"id": "mail-fixture", "subject": "合成存档通知", "sender": "合成部门",
               "received_at": "2026-09-08T08:00:00+08:00", "summary": "用于测试的摘要",
               "category": "教学", "attachments": [], "filing": filing(filing_status, saved_count=1, error_count=1)}
    if no_actions:
        message["triage_status"] = "archived"
    actions = ([] if no_actions else [{"id": "action-one", "message_id": "mail-fixture", "status": "archived",
                                      "title": "合成事项", "due_at": None}])
    return {"version": "fixture-v1", "source": "github", "snapshot": {
        "account": "fixture@example.invalid", "updated_at": "2026-09-08T08:00:00+08:00",
        "coverage": {}, "runs": [], "reports": [], "messages": [message], "actions": actions}}


class FilingDisplayTests(unittest.TestCase):
    def test_seven_statuses_include_filing_separately_from_done(self):
        self.assertEqual(7, len(page.STATUSES))
        self.assertEqual(7, len(page.INBOX_STATUSES))
        self.assertEqual("存档", page.STATUSES["archived"])
        self.assertEqual("存档", page.INBOX_STATUSES["archived"])
        self.assertIn("存档", page.INBOX_VIEWS)
        self.assertNotIn("archived", page.ACTIVE_STATUSES)

    def test_fresh_page_refreshes_a_cached_six_status_module(self):
        legacy = {key: value for key, value in page.mail_action_status.STATUS_LABELS.items() if key != "archived"}
        with patch.object(page.mail_action_status, "STATUS_LABELS", legacy):
            spec = importlib.util.spec_from_file_location("mail_filing_hot_reload_fixture", PAGE_PATH)
            refreshed = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(refreshed)
            self.assertEqual("存档", refreshed.STATUSES["archived"])
            self.assertIn("archived", refreshed.ARCHIVED_STATUSES)

    def test_gateway_refreshes_a_cached_module_without_filing_api(self):
        gateway = page.get_mail_gateway()
        original = gateway.save_filing_requests
        del gateway.save_filing_requests
        try:
            refreshed = page.get_mail_gateway()
            self.assertTrue(callable(refreshed.save_filing_requests))
            self.assertIn("archived", refreshed.ALLOWED_STATUSES)
        finally:
            gateway.save_filing_requests = original

    def test_archived_mail_has_its_own_filter_without_joining_done_or_unrelated(self):
        messages = [{"id": status, "triage_status": status} for status in page.STATUSES]
        archived = page.filter_inbox_messages(messages, [], "存档")
        self.assertEqual(["archived"], [message["id"] for message in archived])
        self.assertNotIn("archived", {m["id"] for m in page.filter_inbox_messages(messages, [], "已办")})
        self.assertNotIn("archived", {m["id"] for m in page.filter_inbox_messages(messages, [], "不相关")})
        self.assertIn("archived", {m["id"] for m in page.filter_inbox_messages(messages, [], "相关")})

    def test_archived_child_is_filterable_without_hiding_mixed_mail_active_children(self):
        messages = [{"id": "mixed"}, {"id": "done"}]
        actions = [{"id": "archived", "message_id": "mixed", "status": "archived"},
                   {"id": "active", "message_id": "mixed", "status": "pending"},
                   {"id": "done", "message_id": "done", "status": "done"}]
        self.assertEqual(["mixed"], [m["id"] for m in page.filter_inbox_messages(messages, actions, "存档")])
        self.assertEqual(["mixed"], [m["id"] for m in page.filter_inbox_messages(messages, actions, "待办")])
        now = datetime(2026, 9, 8, tzinfo=page.BJT)
        self.assertEqual(["archived"], [a["id"] for a in page.filter_actions(actions, messages, "存档", now)])
        self.assertEqual(["done"], [a["id"] for a in page.filter_actions(actions, messages, "已办归档", now)])

    def test_all_three_status_controls_offer_filing_and_explain_whole_email_scope(self):
        loaded = loaded_fixture()
        message = loaded["snapshot"]["messages"][0]
        action = loaded["snapshot"]["actions"][0]
        ui = SimpleNamespace(session_state={"mail_authenticated": True}, selectbox=Mock(), caption=Mock())
        gateway = SimpleNamespace(save_action_updates=Mock(), save_message_updates=Mock(), save_filing_requests=Mock())
        with patch.object(page, "st", ui):
            page.render_status_control(action, loaded, gateway, context="single", labels=page.INBOX_STATUSES)
            page.render_message_status_control(message, loaded, gateway)
            page.render_group_status_control(message, [action, {**action, "id": "second"}], loaded, gateway)
        self.assertEqual(3, ui.selectbox.call_count)
        for call in ui.selectbox.call_args_list:
            self.assertIn("archived", call.args[1])
            self.assertIn("整封邮件的全部附件", call.kwargs["help"])
            self.assertIn("接收电脑需在线", call.kwargs["help"])
        gateway.save_action_updates.assert_not_called()
        gateway.save_message_updates.assert_not_called()
        gateway.save_filing_requests.assert_not_called()

    def test_archived_selection_without_worker_result_does_not_claim_saved_files(self):
        self.assertEqual("", page.filing_progress({"triage_status": "archived"}))
        progress = page.filing_progress({"filing": filing("pending", saved_count=2, total_count=2)})
        self.assertIn("等待本机保存", progress)
        self.assertNotIn("已保存", progress)

    def test_success_requires_consistent_counts_and_safe_destination(self):
        result = filing("success", saved_count=2, total_count=2)
        self.assertEqual("存档 · 已保存 2 份附件", page.filing_progress({"filing": result}))
        for changes in ({"saved_count": 1}, {"error_count": 1}, {"saved_count": True},
                        {"total_count": "2"}, {"destination": "C:/unrelated/file"}):
            with self.subTest(changes=changes):
                progress = page.filing_progress({"filing": {**result, **changes}})
                self.assertNotIn("已保存", progress)
                self.assertIn("待核对", progress)

    def test_verified_zero_attachments_needs_no_destination_or_directory(self):
        message = {"id": "empty-fixture", "filing": filing("success", saved_count=0, total_count=0, destination="")}
        self.assertEqual("存档 · 已确认无附件", page.filing_progress(message))
        ui = SimpleNamespace(session_state={}, text=Mock(), caption=Mock(), button=Mock(), error=Mock())
        with patch.object(page, "st", ui):
            page.render_filing_details(message, loaded_fixture(), Mock(), context="inbox")
        text = " ".join(call.args[0] for call in ui.text.call_args_list)
        self.assertIn("原邮件无附件，无需保存文件", text)
        self.assertNotIn("E:\\", text)
        self.assertNotIn("待本机确认", text)
        ui.button.assert_not_called()

    def test_failure_details_explain_empty_attachment_and_keep_retry_available(self):
        loaded = loaded_fixture()
        message = loaded["snapshot"]["messages"][0]
        message["filing"]["error_codes"] = ["ATTACHMENT_EMPTY"]
        ui = SimpleNamespace(session_state={"mail_authenticated": True}, text=Mock(), caption=Mock(), button=Mock(), error=Mock())
        with patch.object(page, "st", ui):
            page.render_filing_details(message, loaded, Mock(), context="inbox")
        captions = " ".join(call.args[0] for call in ui.caption.call_args_list)
        self.assertIn("邮件中的附件为空，未保存空文件", captions)
        self.assertNotIn("ATTACHMENT_EMPTY", captions)
        self.assertEqual("重试存档", ui.button.call_args.args[0])

    def test_fixed_failure_codes_have_short_safe_reasons(self):
        for code, expected in (("SOURCE_CORRUPT", "损坏"), ("SOURCE_MISSING", "缺失"),
                               ("SOURCE_AUTH_REQUIRED", "邮箱认证"), ("DESTINATION_UNAVAILABLE", "目录暂不可用")):
            with self.subTest(code=code):
                reasons = page.filing_failure_reasons({"filing": filing("error", error_codes=[code])})
                self.assertIn(expected, " ".join(reasons))
        unknown = page.filing_failure_reasons({"filing": filing("error", error_codes=["synthetic-private-server-detail"])})
        self.assertNotIn("synthetic-private", " ".join(unknown))

    def test_partial_error_and_cancelled_have_distinct_progress(self):
        partial = page.filing_progress({"filing": filing("partial", saved_count=1, error_count=1)})
        self.assertIn("1/2", partial)
        self.assertIn("附件待补", partial)
        self.assertEqual("存档 · 未保存", page.filing_progress({"filing": filing("error")}))
        self.assertIn("已取消", page.filing_progress({"filing": filing("cancelled")}))

    def test_destination_is_constructed_only_below_the_known_filing_directory(self):
        self.assertEqual(r"E:\GoogleDrive\Ding2026", page.filing_destination("."))
        root_message = {"filing": filing("success", destination=".", saved_count=2, total_count=2)}
        self.assertEqual("存档 · 已保存 2 份附件", page.filing_progress(root_message))
        self.assertEqual(r"E:\GoogleDrive\Ding2026\邮件存档\2026-09-08 合成通知",
                         page.filing_destination("邮件存档/2026-09-08 合成通知"))
        for path in ("E:/GoogleDrive/Ding2026/邮件存档/notice", "C:/private/notice", "//host/share/notice",
                     "../邮件存档/notice", "邮件存档/../notice", "邮件存档/./notice", "邮件存档//notice",
                     "其他目录/notice", "邮件存档/notice:stream", "邮件存档/.. /notice", "邮件存档/notice\x00"):
            with self.subTest(path=path):
                self.assertIsNone(page.filing_destination(path))

    def test_rendering_partial_progress_only_wires_retry_and_never_writes(self):
        loaded = loaded_fixture()
        message = loaded["snapshot"]["messages"][0]
        ui = SimpleNamespace(session_state={"mail_authenticated": True}, text=Mock(), caption=Mock(), button=Mock(), error=Mock())
        gateway = SimpleNamespace(save_filing_requests=Mock())
        with patch.object(page, "st", ui):
            page.render_filing_details(message, loaded, gateway, context="inbox")
        ui.button.assert_called_once()
        call = ui.button.call_args
        self.assertEqual("重试存档", call.args[0])
        self.assertFalse(call.kwargs["disabled"])
        self.assertIs(page.retry_filing, call.kwargs["on_click"])
        self.assertEqual(("mail-fixture", gateway, "fixture-v1"), call.kwargs["args"])
        self.assertTrue(any("Google Drive 同步" in c.args[0] for c in ui.caption.call_args_list))
        gateway.save_filing_requests.assert_not_called()

    def test_readonly_retry_is_disabled_and_unsafe_cloud_path_is_not_echoed(self):
        for authenticated, source in ((False, "github"), (True, "local")):
            with self.subTest(authenticated=authenticated, source=source):
                loaded = loaded_fixture()
                loaded["source"] = source
                loaded["snapshot"]["messages"][0]["filing"]["destination"] = "C:/private/unsafe-fixture"
                ui = SimpleNamespace(session_state={"mail_authenticated": authenticated}, text=Mock(), caption=Mock(), button=Mock(), error=Mock())
                with patch.object(page, "st", ui):
                    page.render_filing_details(loaded["snapshot"]["messages"][0], loaded, Mock(), context="inbox")
                self.assertTrue(ui.button.call_args.kwargs["disabled"])
                self.assertNotIn("unsafe-fixture", " ".join(c.args[0] for c in ui.text.call_args_list))


class FilingRetryTests(unittest.TestCase):
    def setUp(self):
        self.loaded = loaded_fixture()
        self.before = copy.deepcopy(self.loaded)
        self.state = {"mail_loaded": self.loaded, "mail_authenticated": True,
                      "mail_action_drafts": {"unrelated": "done"}, "mail_filing_errors": {"mail-fixture": "上次保存失败"}}
        self.ui = SimpleNamespace(session_state=self.state, secrets={"budget_password": "synthetic-password"})
        self.gateway = SimpleNamespace(save_filing_requests=Mock(), save_action_updates=Mock(), save_message_updates=Mock())
        for patcher in (patch.object(page, "st", self.ui),
                        patch.object(page.budget_auth, "get_budget_password", return_value="synthetic-password")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def retry(self, expected_version="fixture-v1"):
        page.retry_filing("mail-fixture", self.gateway, expected_version)

    def test_retry_uses_cas_and_replaces_only_after_valid_save_without_changing_drafts(self):
        def save(message_ids, **kwargs):
            self.assertEqual(["mail-fixture"], message_ids)
            self.assertEqual("fixture-v1", kwargs["expected_version"])
            self.assertEqual(self.before, self.loaded)
            self.assertIs(self.loaded, self.state["mail_loaded"])
            saved = copy.deepcopy(self.loaded)
            saved["version"] = "fixture-v2"
            saved["snapshot"]["messages"][0]["filing"] = filing("pending")
            return saved

        self.gateway.save_filing_requests.side_effect = save
        self.retry()
        self.gateway.save_filing_requests.assert_called_once()
        self.gateway.save_action_updates.assert_not_called()
        self.gateway.save_message_updates.assert_not_called()
        self.assertEqual(self.before, self.loaded)
        self.assertEqual("fixture-v2", self.state["mail_loaded"]["version"])
        self.assertEqual({"unrelated": "done"}, self.state["mail_action_drafts"])
        self.assertNotIn("mail-fixture", self.state["mail_filing_errors"])
        self.assertIn("等待本机保存", self.state["mail_save_notice"])

    def test_stale_version_or_lost_edit_access_never_calls_remote(self):
        for version, authenticated, source in (("stale", True, "github"), ("fixture-v1", False, "github"),
                                                ("fixture-v1", True, "local")):
            with self.subTest(version=version, authenticated=authenticated, source=source):
                self.loaded["source"] = source
                self.state["mail_authenticated"] = authenticated
                self.retry(version)
                self.gateway.save_filing_requests.assert_not_called()
                self.assertIs(self.loaded, self.state["mail_loaded"])
                self.assertIn("mail-fixture", self.state["mail_filing_errors"])

    def test_removed_password_blocks_retry_before_remote_request(self):
        with patch.object(page.budget_auth, "get_budget_password", return_value=None):
            self.retry()
        self.gateway.save_filing_requests.assert_not_called()

    def test_removed_archived_status_or_finished_request_is_not_requeued(self):
        self.loaded["snapshot"]["actions"][0]["status"] = "pending"
        self.retry()
        self.gateway.save_filing_requests.assert_not_called()
        self.loaded["snapshot"]["actions"][0]["status"] = "archived"
        self.loaded["snapshot"]["messages"][0]["filing"]["status"] = "success"
        self.retry()
        self.gateway.save_filing_requests.assert_not_called()

    def test_retry_failure_keeps_previous_result_and_safe_error_for_next_render(self):
        self.gateway.save_filing_requests.side_effect = RuntimeError("synthetic-sensitive-server-detail")
        self.retry()
        self.assertIs(self.loaded, self.state["mail_loaded"])
        self.assertEqual(self.before, self.loaded)
        self.assertEqual({"unrelated": "done"}, self.state["mail_action_drafts"])
        self.assertNotIn("synthetic-sensitive", self.state["mail_filing_errors"]["mail-fixture"])
        self.assertNotIn("mail_save_notice", self.state)

    def test_invalid_response_does_not_erase_previous_result(self):
        self.gateway.save_filing_requests.return_value = {"snapshot": {}}
        self.retry()
        self.assertIs(self.loaded, self.state["mail_loaded"])
        self.assertEqual(self.before, self.loaded)
        self.assertIn("mail-fixture", self.state["mail_filing_errors"])

    def test_no_action_mail_uses_its_own_archived_triage_status_for_retry(self):
        loaded = loaded_fixture(no_actions=True)
        self.state["mail_loaded"] = loaded
        saved = copy.deepcopy(loaded)
        saved["version"] = "fixture-v2"
        self.gateway.save_filing_requests.return_value = saved
        self.retry()
        self.gateway.save_filing_requests.assert_called_once()


class FilingAppTests(unittest.TestCase):
    def test_retry_button_requeues_only_on_click_and_then_shows_pending_progress(self):
        from streamlit.testing.v1 import AppTest

        loaded = loaded_fixture()
        original = copy.deepcopy(loaded)
        app = AppTest.from_file(str(PAGE_PATH))
        app.session_state["mail_loaded"] = loaded
        app.session_state["mail_authenticated"] = True
        gateway = page.get_mail_gateway()

        def save(message_ids, **kwargs):
            self.assertEqual(["mail-fixture"], message_ids)
            self.assertEqual("fixture-v1", kwargs["expected_version"])
            saved = copy.deepcopy(loaded)
            saved["version"] = "fixture-v2"
            saved["snapshot"]["messages"][0]["filing"] = filing("pending")
            return saved

        with patch.object(page.budget_auth, "get_budget_password", return_value="synthetic-password"), \
                patch.object(gateway, "load_snapshot", side_effect=AssertionError("No real mail reads")) as load, \
                patch.object(gateway, "save_filing_requests", side_effect=save) as retry, \
                patch.object(gateway, "save_action_updates", side_effect=AssertionError("Retry must not change action state")), \
                patch.object(gateway, "save_message_updates", side_effect=AssertionError("Retry must not change message state")):
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
            retry.assert_not_called()
            button = next(button for button in app.tabs[0].button if button.label == "重试存档")
            self.assertFalse(button.disabled)
            button.click()
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
        retry.assert_called_once()
        load.assert_not_called()
        self.assertEqual(original, loaded)
        self.assertEqual("archived", app.session_state["mail_loaded"]["snapshot"]["actions"][0]["status"])
        self.assertEqual("pending", app.session_state["mail_loaded"]["snapshot"]["messages"][0]["filing"]["status"])
        self.assertIn("等待本机保存", " ".join(element.value for element in app.tabs[0].caption))
        self.assertFalse(any(button.label == "重试存档" for button in app.tabs[0].button))

    def test_single_child_archive_queues_all_mail_attachments_without_claiming_completion(self):
        from streamlit.testing.v1 import AppTest

        loaded = loaded_fixture()
        message = loaded["snapshot"]["messages"][0]
        message.pop("filing")
        loaded["snapshot"]["actions"][0]["status"] = "pending"
        loaded["snapshot"]["actions"].append({"id": "action-two", "message_id": "mail-fixture", "status": "pending",
                                                 "title": "第二个合成事项", "due_at": None})
        app = AppTest.from_file(str(PAGE_PATH))
        app.session_state["mail_loaded"] = loaded
        app.session_state["mail_authenticated"] = True
        gateway = page.get_mail_gateway()

        def save(updates, **kwargs):
            self.assertEqual({"action-one": "archived"}, updates)
            saved = copy.deepcopy(loaded)
            saved["version"] = "fixture-v2"
            saved["snapshot"]["actions"][0]["status"] = "archived"
            saved["snapshot"]["messages"][0]["filing"] = filing("pending", destination="")
            return saved

        with patch.object(page.budget_auth, "get_budget_password", return_value="synthetic-password"), \
                patch.object(gateway, "load_snapshot", side_effect=AssertionError("No real mail reads")) as load, \
                patch.object(gateway, "save_action_updates", side_effect=save) as save_action, \
                patch.object(gateway, "save_message_updates", side_effect=AssertionError("No message writes")), \
                patch.object(gateway, "save_filing_requests", side_effect=AssertionError("Initial rendering cannot request retries")) as retries:
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
            control = next(c for c in app.tabs[0].selectbox if "_action-one_" in str(c.key))
            self.assertIn("存档", control.options)
            control.set_value("archived")
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
        save_action.assert_called_once()
        retries.assert_not_called()
        load.assert_not_called()
        saved = app.session_state["mail_loaded"]
        self.assertEqual(["archived", "pending"], [a["status"] for a in saved["snapshot"]["actions"]])
        captions = " ".join(element.value for element in app.tabs[0].caption)
        self.assertIn("等待本机保存", captions)
        self.assertNotIn("已保存 2 份附件", captions)
        parent = next(c for c in app.tabs[0].selectbox if c.label == "整封邮件判断")
        self.assertEqual("__mixed__", parent.value)


if __name__ == "__main__":
    unittest.main()
