"""Page logic checks without starting a Streamlit application or reading mail."""

import importlib.util
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "23_24_mail_workbench.py"
SPEC = importlib.util.spec_from_file_location("mail_workbench_page", PAGE_PATH)
page = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(page)


class StopPage(BaseException):
    pass


class MailWorkbenchPageTests(unittest.TestCase):
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
        self.assertIn("只有样本试跑", page.coverage_warning(snapshot))
        self.assertIn("不代表全量", page.run_status_label(snapshot["runs"][0]))

    def test_full_window_does_not_hide_incomplete_historical_attachment(self):
        snapshot = {"coverage": {"complete": True, "since": "2026-09-05", "through": "2026-09-06"},
                    "runs": [{"kind": "sample", "status": "partial"}, {"kind": "daily", "status": "success"}],
                    "messages": [{"received_at": "2026-09-01", "attachments": [{"status": "error"}]},
                                 {"received_at": "2026-09-06", "attachments": [{"status": "success"}]}]}
        self.assertIsNone(page.coverage_warning(snapshot))
        self.assertEqual(1, page.incomplete_attachment_count(snapshot["messages"]))
        self.assertIn("失败", page.ATTACHMENT_STATUSES["error"])

    def test_missing_password_keeps_public_browsing_but_disables_previous_edit_session(self):
        fake_st = SimpleNamespace(secrets={}, session_state={"mail_authenticated": True},
                                  caption=Mock(), stop=Mock(side_effect=StopPage))
        with patch.object(page, "st", fake_st), patch.object(page.budget_auth, "get_budget_password", return_value=None):
            self.assertFalse(page.render_edit_access())
        fake_st.stop.assert_not_called()
        self.assertNotIn("mail_authenticated", fake_st.session_state)

    def test_main_loads_public_summary_without_an_edit_session(self):
        columns = [SimpleNamespace(button=Mock(return_value=False)), SimpleNamespace(button=Mock(return_value=False))]
        fake_st = SimpleNamespace(set_page_config=Mock(), title=Mock(), markdown=Mock(), caption=Mock(),
                                  columns=Mock(return_value=columns), session_state={})
        with patch.object(page, "st", fake_st), patch.object(page, "render_home_link"), \
                patch.object(page, "render_edit_access", return_value=False), \
                patch.object(page, "refresh_snapshot", side_effect=StopPage) as load:
            with self.assertRaises(StopPage):
                page.main()
            load.assert_called_once()
        columns[1].button.assert_not_called()

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

    def test_mail_text_cannot_become_a_tracking_image(self):
        text = "![image](https://example.org/tracker) <img src='https://example.org/'>"
        escaped = page.plain_label(text)
        self.assertIn(r"\!\[image\]\(", escaped)
        self.assertIn(r"\<img", escaped)


if __name__ == "__main__":
    unittest.main()
