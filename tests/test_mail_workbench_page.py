"""Page logic checks without starting a Streamlit application or reading mail."""

import importlib.util
import copy
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "23_24_mail_workbench.py"
SPEC = importlib.util.spec_from_file_location("mail_workbench_page", PAGE_PATH)
page = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(page)


class StopPage(BaseException):
    pass


class MailWorkbenchPageTests(unittest.TestCase):
    def test_hot_deploy_refreshes_pre_triage_report_module(self):
        original = page.mail_report_view.report_action_records
        try:
            del page.mail_report_view.report_action_records
            reloaded_page = importlib.util.module_from_spec(SPEC)
            SPEC.loader.exec_module(reloaded_page)
            self.assertTrue(callable(reloaded_page.report_action_records))
        finally:
            page.mail_report_view.report_action_records = original

    def test_hot_deploy_refreshes_old_status_validator_before_saving(self):
        gateway = page.get_mail_gateway()
        with patch.object(gateway, "ALLOWED_STATUSES", frozenset({"pending", "in_progress", "done", "needs_confirmation"})):
            refreshed = page.get_mail_gateway()
            self.assertTrue(set(page.STATUSES).issubset(refreshed.ALLOWED_STATUSES))

    def test_hot_deploy_refreshes_gateway_missing_mail_decision_api(self):
        gateway = page.get_mail_gateway()
        original = gateway.save_message_updates
        try:
            del gateway.save_message_updates
            self.assertTrue(callable(page.get_mail_gateway().save_message_updates))
        finally:
            gateway.save_message_updates = original

    def test_timezone_filter_uses_beijing_receipt_date(self):
        messages = [
            {"id": "before", "received_at": "2026-09-05T15:59:00Z", "category": "教学"},
            {"id": "after", "received_at": "2026-09-05T16:01:00Z", "category": "教学"},
            {"id": "other", "received_at": "2026-09-06T09:00:00+08:00", "category": "科研"},
        ]
        selected = page.filter_messages(messages, date(2026, 9, 6), date(2026, 9, 6), "教学")
        self.assertEqual(["after"], [item["id"] for item in selected])

    def test_date_only_deadline_is_not_overdue_at_start_of_day(self):
        now = datetime(2026, 9, 6, 9, tzinfo=page.BJT)
        actions = [
            {"id": "date", "due_at": "2026-09-06", "status": "pending"},
            {"id": "late", "due_at": "2026-09-06T08:00:00+08:00", "status": "pending"},
            {"id": "done", "due_at": "2026-09-05", "status": "done"},
            {"id": "unknown", "due_at": None, "due_text": "尽快", "status": "pending"},
            {"id": "invalid", "due_at": "下周", "status": "needs_confirmation"},
        ]
        self.assertEqual(["late"], [item["id"] for item in page.filter_actions(actions, [], "逾期", now)])
        self.assertEqual({"unknown", "invalid"}, {item["id"] for item in page.filter_actions(actions, [], "待确认", now)})
        self.assertIn("具体时刻以截止原文为准", page.display_time("2026-09-06", deadline=True))
        self.assertNotIn("23:59", page.display_time("2026-09-06", deadline=True))

    def test_due_views_do_not_require_recent_receipt(self):
        actions = [{"id": "old", "message_id": "m", "due_at": "2026-09-07", "status": "pending"}]
        messages = [{"id": "m", "received_at": "2026-08-01", "category": "教学"}]
        selected = page.filter_actions(actions, messages, "未来7天", datetime(2026, 9, 6, tzinfo=page.BJT), "教学")
        self.assertEqual(["old"], [item["id"] for item in selected])

    def test_closed_categories_never_enter_active_or_due_views(self):
        actions = [{"id": status, "status": status, "due_at": "2026-09-06"} for status in page.STATUSES]
        now = datetime(2026, 9, 6, 9, tzinfo=page.BJT)
        self.assertEqual({"pending", "in_progress"}, {a["id"] for a in page.filter_actions(actions, [], "我的待办", now)})
        for view in ("未完成", "今天", "未来7天"):
            with self.subTest(view=view):
                self.assertEqual(page.ACTIVE_STATUSES, {a["id"] for a in page.filter_actions(actions, [], view, now)})
        for view, status in (("已办归档", "done"), ("无需处理", "no_action"), ("不相关业务", "out_of_scope")):
            self.assertEqual([status], [a["id"] for a in page.filter_actions(actions, [], view, now)])
        self.assertEqual({"needs_confirmation"}, {a["id"] for a in page.filter_actions(actions, [], "待确认", now)})

    def test_report_ids_keep_link_to_reclassified_and_updated_actions(self):
        actions = [{"id": "a", "title": "补充后标题", "status": "out_of_scope"},
                   {"id": "b", "title": "其他事项", "status": "pending"}]
        linked, missing = page.linked_report_actions({"action_ids": ["a", "missing"]}, actions)
        self.assertEqual(["a"], [item["id"] for item in linked])
        self.assertEqual(1, missing)

    def test_legacy_report_requires_unique_full_field_match_and_does_not_mutate_history(self):
        markdown = "## 待处理与时间节点\n\n- **待确认 · 交表**｜截止：下班前（2026-09-07）｜责任：学院｜要求：核对 A | B｜提交至：教务部\n"
        report = {"markdown": markdown}
        action = {"id": "a", "title": "交表", "due_text": "下班前", "due_at": "2026-09-07",
                  "owner": "学院", "requirement": "核对 A | B", "recipient": "教务部", "status": "no_action"}
        linked, missing = page.linked_report_actions(report, [action])
        self.assertEqual([action], linked)
        self.assertEqual(0, missing)
        ambiguous = [action, {**action, "id": "b"}]
        self.assertEqual(([], 1), page.linked_report_actions(report, ambiguous))
        self.assertEqual(([], 1), page.linked_report_actions(report, [{**action, "requirement": "新的要求"}]))
        self.assertEqual(markdown, report["markdown"])

    def test_source_links_reject_other_hosts_credentials_and_unknown_queries(self):
        good = "https://mail.nsu.edu.cn/owa/?ae=Item&a=Open&t=IPM.Note&id=sample%2Fid"
        self.assertEqual(good, page.safe_source_url(good))
        for value in [
            "http://mail.nsu.edu.cn/owa/", "https://mail.nsu.edu.cn.example.org/owa/",
            "https://user:example@ mail.nsu.edu.cn/owa/", "https://user:example@mail.nsu.edu.cn/owa/",
            "https://mail.nsu.edu.cn/owa/?token=example", "https://mail.nsu.edu.cn/owa/?redirect=https://example.org",
            "https://mail.nsu.edu.cn/owa/other", "https://mail.nsu.edu.cn/owa/#example",
        ]:
            with self.subTest(value=value):
                self.assertIsNone(page.safe_source_url(value))

    def test_attachment_index_never_exposes_absolute_or_traversal_paths(self):
        self.assertEqual("2026-09-06/message/report.docx", page.relative_archive_path("2026-09-06\\message\\report.docx"))
        for value in ["C:\\private\\mail.docx", "../mail.docx", "/private/mail.docx", "//server/share/mail.docx", "C:mail.docx"]:
            self.assertEqual("需补充相对位置", page.relative_archive_path(value))

    def test_homepage_and_actual_item_links_have_distinct_labels(self):
        self.assertEqual("打开学校邮箱", page.source_link_label("https://mail.nsu.edu.cn/owa/"))
        self.assertEqual("打开学校邮箱", page.source_link_label("https://mail.nsu.edu.cn/owa/?id=folder"))
        self.assertEqual("打开原邮件", page.source_link_label("https://mail.nsu.edu.cn/owa/?ae=Item&id=message"))
        self.assertIsNone(page.source_link_label("https://example.org/"))

    def test_sample_only_snapshot_never_appears_fully_collected(self):
        snapshot = {"coverage": {"complete": True, "since": "2026-09-01", "through": "2026-09-06"},
                    "runs": [{"kind": "sample", "status": "success"}]}
        self.assertIn("试跑数据", page.coverage_warning(snapshot))
        self.assertIn("试跑数据", page.snapshot_status_html(snapshot))
        self.assertIn("不代表全量", page.run_status_label(snapshot["runs"][0]))

    def test_full_window_does_not_hide_incomplete_historical_attachment(self):
        snapshot = {"coverage": {"complete": True, "since": "2026-09-05", "through": "2026-09-06"},
                    "runs": [{"kind": "sample", "status": "partial"}, {"kind": "daily", "status": "success"}],
                    "messages": [{"received_at": "2026-09-01", "attachments": [{"status": "error"}]},
                                 {"received_at": "2026-09-06", "attachments": [{"status": "success"}]}]}
        self.assertIsNone(page.coverage_warning(snapshot))
        self.assertEqual(1, page.incomplete_attachment_count(snapshot["messages"]))
        self.assertIn("失败", page.ATTACHMENT_STATUSES["error"])
        self.assertIn("已完成时段核对", page.snapshot_status_html(snapshot))
        self.assertIn("1 份附件待补", page.snapshot_status_html(snapshot))

    def test_missing_coverage_dates_do_not_look_complete_in_compact_status(self):
        snapshot = {"coverage": {"complete": True}, "runs": [{"kind": "daily", "status": "success"}]}
        self.assertIn("采集待补全", page.snapshot_status_html(snapshot))

    def test_missing_password_keeps_public_browsing_but_disables_previous_edit_session(self):
        fake_st = SimpleNamespace(secrets={}, session_state={"mail_authenticated": True},
                                  caption=Mock(), stop=Mock(side_effect=StopPage))
        with patch.object(page, "st", fake_st), patch.object(page.budget_auth, "get_budget_password", return_value=None):
            self.assertFalse(page.render_edit_access())
        fake_st.stop.assert_not_called()
        self.assertNotIn("mail_authenticated", fake_st.session_state)

    def test_main_loads_public_summary_without_an_edit_session(self):
        columns = [MagicMock(), MagicMock(), MagicMock()]
        columns[1].button.return_value = False
        fake_st = SimpleNamespace(set_page_config=Mock(), title=Mock(), markdown=Mock(), caption=Mock(),
                                  columns=Mock(return_value=columns), button=Mock(), session_state={})
        with patch.object(page, "st", fake_st), patch.object(page, "render_home_link"), \
                patch.object(page, "render_edit_access", return_value=False), \
                patch.object(page, "refresh_snapshot", side_effect=StopPage) as load:
            with self.assertRaises(StopPage):
                page.main()
            load.assert_called_once()
        fake_st.button.assert_not_called()

    def test_initial_page_renders_mail_and_original_status_without_opening_a_report(self):
        from streamlit.testing.v1 import AppTest

        snapshot = {"account": "test@example.invalid", "updated_at": "2026-09-06T09:00:00+08:00",
                    "coverage": {}, "runs": [], "reports": [],
                    "messages": [{"id": "m1", "subject": "首页测试邮件", "sender": "测试部门",
                                  "received_at": "2026-08-01T09:00:00+08:00", "summary": "展开后查看的邮件重点", "attachments": []},
                                 {"id": "m2", "subject": "没有事项的邮件", "received_at": "2026-09-01T09:00:00+08:00", "attachments": []}],
                    "actions": [{"id": "a1", "message_id": "m1", "title": "测试事项", "status": "out_of_scope"}]}
        app = AppTest.from_file(str(PAGE_PATH))
        app.session_state["mail_loaded"] = {"snapshot": snapshot, "version": "fixture", "source": "github"}
        app.session_state["mail_authenticated"] = True
        gateway = page.get_mail_gateway()
        with patch.object(page.budget_auth, "get_budget_password", return_value="test-edit-password"), \
                patch.object(gateway, "load_snapshot", side_effect=AssertionError("Test must not read real mail")), \
                patch.object(gateway, "save_action_updates", side_effect=AssertionError("Render must not save mail")) as save, \
                patch.object(gateway, "save_message_updates", side_effect=AssertionError("Render must not save mail")) as save_mail:
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
            # Both tabs can show the same mail without sharing a widget key.
            next(element for element in app.radio if element.label == "待办视图").set_value("全部")
            app.run(timeout=15)
        self.assertEqual([], list(app.exception))
        self.assertEqual("邮件列表", app.tabs[0].label)
        inbox_html = " ".join(element.value for element in app.tabs[0].markdown)
        self.assertIn("首页测试邮件", inbox_html)
        self.assertNotIn("展开后查看的邮件重点", inbox_html)
        self.assertTrue(any("展开后查看的邮件重点" in element.value for element in app.tabs[0].text))
        self.assertIn("没有事项的邮件", inbox_html)
        statuses = [element for element in app.tabs[0].selectbox if element.label == "当前状态"]
        self.assertEqual(2, len(statuses))
        self.assertEqual({"out_of_scope", "needs_confirmation"}, {element.value for element in statuses})
        self.assertIn("相关 · 待办", statuses[0].options)
        save.assert_not_called()
        save_mail.assert_not_called()

    def test_anonymous_status_save_is_blocked_before_any_remote_call(self):
        loaded = {"snapshot": {"actions": [{"id": "a", "status": "pending"}]}, "version": "old", "source": "github"}
        drafts = {"a": "done"}
        fake_st = SimpleNamespace(secrets={}, session_state={})
        gateway = SimpleNamespace(save_action_updates=Mock())
        with patch.object(page, "st", fake_st):
            with self.assertRaises(PermissionError):
                page.save_drafts(gateway, loaded, drafts)
        gateway.save_action_updates.assert_not_called()
        self.assertEqual({"a": "done"}, drafts)

    def test_removed_password_configuration_blocks_status_save(self):
        loaded = {"snapshot": {"actions": [{"id": "a", "status": "pending"}]}, "version": "old", "source": "github"}
        fake_st = SimpleNamespace(secrets={}, session_state={"mail_authenticated": True})
        gateway = SimpleNamespace(save_action_updates=Mock())
        with patch.object(page, "st", fake_st), patch.object(page.budget_auth, "get_budget_password", return_value=None):
            with self.assertRaises(PermissionError):
                page.save_drafts(gateway, loaded, {"a": "done"})
        gateway.save_action_updates.assert_not_called()

    def test_conflict_keeps_user_draft_and_original_version(self):
        loaded = {"snapshot": {"actions": [{"id": "a", "status": "pending"}]}, "version": "old-sha", "source": "github"}
        drafts = {"a": "done"}
        state = {"mail_loaded": loaded, "mail_action_drafts": drafts, "mail_authenticated": True}
        fake_st = SimpleNamespace(secrets={"budget_password": "test-edit-password"}, session_state=state)
        conflict = RuntimeError("safe conflict")
        gateway = SimpleNamespace(save_action_updates=Mock(side_effect=conflict))
        with patch.object(page, "st", fake_st):
            with self.assertRaises(RuntimeError):
                page.save_drafts(gateway, loaded, drafts)
        self.assertEqual({"a": "done"}, drafts)
        self.assertEqual("old-sha", state["mail_loaded"]["version"])
        self.assertEqual("old-sha", gateway.save_action_updates.call_args.kwargs["expected_version"])

    def test_success_replaces_snapshot_and_clears_only_saved_edits(self):
        loaded = {"snapshot": {"actions": [{"id": "a", "status": "pending"}]}, "version": "old", "source": "github"}
        saved = {"snapshot": {"actions": [{"id": "a", "status": "done"}]}, "version": "new", "source": "github"}
        drafts = {"a": "done", "removed": "in_progress"}
        fake_st = SimpleNamespace(secrets={"budget_password": "test-edit-password"}, session_state={"mail_status_a": "done", "mail_authenticated": True})
        gateway = SimpleNamespace(save_action_updates=Mock(return_value=saved))
        with patch.object(page, "st", fake_st):
            self.assertTrue(page.save_drafts(gateway, loaded, drafts))
        self.assertEqual("new", fake_st.session_state["mail_loaded"]["version"])
        self.assertEqual({"removed": "in_progress"}, drafts)
        self.assertNotIn("mail_status_a", fake_st.session_state)

    def test_refresh_preserves_user_drafts(self):
        fake_st = SimpleNamespace(secrets={}, session_state={"mail_action_drafts": {"a": "done"}})
        loaded = {"snapshot": {"actions": []}, "version": "latest", "source": "github"}
        gateway = SimpleNamespace(load_snapshot=Mock(return_value=loaded))
        with patch.object(page, "st", fake_st):
            self.assertEqual(loaded, page.refresh_snapshot(gateway))
        self.assertEqual({"a": "done"}, fake_st.session_state["mail_action_drafts"])

    def test_dropdown_saves_only_selected_item_then_moves_to_its_archive_group(self):
        for status in page.ARCHIVED_STATUSES:
            with self.subTest(status=status):
                loaded = {"snapshot": {"actions": [{"id": "a", "status": "pending"}, {"id": "b", "status": "pending"}]},
                          "version": "old", "source": "github"}
                saved = copy.deepcopy(loaded)
                saved["version"] = "new"
                saved["snapshot"]["actions"][0]["status"] = status
                drafts = {"b": "done"}
                state = {"mail_loaded": loaded, "mail_authenticated": True, "mail_action_drafts": drafts, "choice": status}
                fake_st = SimpleNamespace(secrets={"budget_password": "test-edit-password"}, session_state=state)
                gateway = SimpleNamespace(save_action_updates=Mock(return_value=saved))
                with patch.object(page, "st", fake_st):
                    page.remember_status("a", "choice", gateway, "old")
                self.assertEqual({"a": status}, gateway.save_action_updates.call_args.args[0])
                self.assertEqual({"b": "done"}, drafts)
                self.assertEqual("new", state["mail_loaded"]["version"])
                self.assertIn("移入", state["mail_save_notice"])

    def test_dropdown_failure_preserves_original_active_item_and_user_choice(self):
        loaded = {"snapshot": {"actions": [{"id": "a", "status": "pending"}]}, "version": "old", "source": "github"}
        state = {"mail_loaded": loaded, "mail_authenticated": True, "choice": "out_of_scope"}
        fake_st = SimpleNamespace(secrets={"budget_password": "test-edit-password"}, session_state=state)
        gateway = SimpleNamespace(save_action_updates=Mock(side_effect=RuntimeError("private details must stay hidden")))
        with patch.object(page, "st", fake_st):
            page.remember_status("a", "choice", gateway, "old")
        self.assertEqual("pending", state["mail_loaded"]["snapshot"]["actions"][0]["status"])
        self.assertEqual({"a": "out_of_scope"}, state["mail_action_drafts"])
        self.assertNotIn("mail_save_notice", state)
        self.assertNotIn("private details", state["mail_save_error"])

    def test_callback_cannot_write_from_stale_render_or_unauthenticated_session(self):
        for authenticated, version in ((True, "stale"), (False, "current")):
            with self.subTest(authenticated=authenticated, version=version):
                loaded = {"snapshot": {"actions": [{"id": "a", "status": "pending"}]}, "version": "current", "source": "github"}
                state = {"mail_loaded": loaded, "mail_authenticated": authenticated, "choice": "done"}
                fake_st = SimpleNamespace(secrets={"budget_password": "test-edit-password"}, session_state=state)
                gateway = SimpleNamespace(save_action_updates=Mock())
                with patch.object(page, "st", fake_st):
                    page.remember_status("a", "choice", gateway, version)
                gateway.save_action_updates.assert_not_called()
                self.assertEqual("pending", loaded["snapshot"]["actions"][0]["status"])

    def test_mail_text_cannot_become_a_tracking_image(self):
        text = "![image](https://example.org/tracker) <img src='https://example.org/'>"
        escaped = page.plain_label(text)
        self.assertIn(r"\!\[image\]\(", escaped)
        self.assertIn(r"\<img", escaped)


if __name__ == "__main__":
    unittest.main()
