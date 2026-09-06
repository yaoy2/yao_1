"""Inbox behavior checks without starting Streamlit or accessing real mail."""

import copy
import importlib.util
import unittest
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import Mock, patch


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "23_24_mail_workbench.py"
SPEC = importlib.util.spec_from_file_location("mail_inbox_page", PAGE_PATH)
page = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(page)


def message(identifier="m1", **fields):
    return {"id": identifier, "subject": "材料报送", "sender": "教务部门",
            "summary": "请核对材料", "category": "教学",
            "received_at": "2026-09-06T08:00:00+08:00", "attachments": [], **fields}


def action(identifier="a1", message_id="m1", status="pending", **fields):
    return {"id": identifier, "message_id": message_id, "title": "核对材料",
            "status": status, "due_at": None, **fields}


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = []

    def handle_starttag(self, tag, attrs):
        self.names.append(tag)


class Region:
    def __init__(self, ui, expandable=False):
        self.ui = ui
        self.expandable = expandable

    def __enter__(self):
        self.ui.expander_depth += int(self.expandable)
        return self

    def __exit__(self, *args):
        self.ui.expander_depth -= int(self.expandable)

    def __getattr__(self, name):
        return getattr(self.ui, name)


class InboxUI:
    """Record visible text and editor wiring, without evaluating callbacks."""

    def __init__(self, authenticated=True):
        self.session_state = {"mail_authenticated": authenticated}
        self.events = []
        self.expander_depth = 0

    def record(self, kind, value, **kwargs):
        self.events.append({"kind": kind, "value": value, "kwargs": kwargs,
                            "expander_depth": self.expander_depth})

    def container(self, **kwargs):
        return Region(self)

    def columns(self, sizes, **kwargs):
        return [Region(self) for _ in sizes]

    def expander(self, label, **kwargs):
        self.record("expander", label, **kwargs)
        return Region(self, expandable=True)

    def popover(self, label, **kwargs):
        return Region(self, expandable=True)

    def markdown(self, value, **kwargs):
        self.record("markdown", value, **kwargs)

    def caption(self, value, **kwargs):
        self.record("caption", value, **kwargs)

    def text(self, value, **kwargs):
        self.record("text", value, **kwargs)

    def info(self, value, **kwargs):
        self.record("info", value, **kwargs)

    def selectbox(self, label, options, **kwargs):
        self.record("selectbox", label, options=list(options), **kwargs)
        return self.session_state.get(kwargs.get("key"), list(options)[0])

    def radio(self, label, options, **kwargs):
        self.record("radio", label, options=list(options), **kwargs)
        return list(options)[0]

    def text_input(self, label, **kwargs):
        return ""

    def checkbox(self, label, **kwargs):
        return False

    def button(self, label, **kwargs):
        self.record("button", label, **kwargs)
        return False


class MailInboxViewTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 6, 9, tzinfo=page.BJT)

    def test_default_includes_old_unrelated_and_undated_mail(self):
        messages = [message("old", received_at="2026-01-01T08:00:00+08:00"),
                    message("unrelated"), message("undated", received_at=None)]
        actions = [action("old-task", "old"), action("other-task", "unrelated", "out_of_scope")]
        selected = page.filter_inbox_messages(messages, actions)
        self.assertEqual(["unrelated", "old", "undated"], [item["id"] for item in selected])
        self.assertEqual("全部", page.INBOX_VIEWS[0])
        self.assertEqual(set(page.STATUSES), set(page.INBOX_STATUSES))

    def test_multiple_actions_match_once_without_rewriting_saved_decisions(self):
        messages = [message("mixed"), message("other")]
        actions = [action("a1", "mixed", "pending"), action("a2", "mixed", "in_progress"),
                   action("a3", "mixed", "done"), action("a4", "mixed", "out_of_scope")]
        before = copy.deepcopy((messages, actions))
        for view in ("待办", "已办", "不相关", "相关"):
            with self.subTest(view=view):
                self.assertEqual(["mixed"], [item["id"] for item in
                                           page.filter_inbox_messages(messages, actions, view)])
        self.assertEqual(before, (messages, actions))

    def test_mail_without_actions_is_unjudged_not_assumed_unnecessary(self):
        messages = [message()]
        self.assertEqual(messages, page.filter_inbox_messages(messages, [], "全部"))
        self.assertEqual(messages, page.filter_inbox_messages(messages, [], "待判断"))
        for view in ("相关", "待办", "已办", "无需处理", "不相关"):
            with self.subTest(view=view):
                self.assertEqual([], page.filter_inbox_messages(messages, [], view))

    def test_search_matches_subject_sender_summary_category_and_linked_requirements(self):
        messages = [message("target", subject="Budget 汇总", sender="学院办公室",
                            summary="请核对经费", category="预算"), message("other")]
        actions = [action(message_id="target", title="核实台账", requirement="附上决算说明")]
        for query in (" budget ", "学院办公室", "经费", "预算", "核实台账", "决算说明"):
            with self.subTest(query=query):
                self.assertEqual(["target"], [item["id"] for item in
                                            page.filter_inbox_messages(messages, actions, query=query)])
        self.assertEqual([], page.filter_inbox_messages(messages, actions, query="没有这个词"))

    def test_optional_receipt_dates_use_beijing_time_and_combine_with_category(self):
        messages = [message("before", received_at="2026-09-05T15:59:00Z"),
                    message("inside", received_at="2026-09-05T16:01:00Z"),
                    message("other-category", category="科研"),
                    message("missing", received_at=None)]
        selected = page.filter_inbox_messages(messages, [], start=date(2026, 9, 6),
                                             end=date(2026, 9, 6), category="教学")
        self.assertEqual(["inside"], [item["id"] for item in selected])
        self.assertEqual(3, len(page.filter_inbox_messages(messages, [], category="教学")))

    def test_untrusted_text_cannot_create_html_or_markdown_links_and_images(self):
        payload = '<img src=x onerror=alert(1)> ![图](https://invalid.test/p) [链接](https://invalid.test/)'
        mail = message(subject=payload, sender=payload, summary=payload, category=payload)
        for actions in ([], [action(requirement=payload)]):
            with self.subTest(has_action=bool(actions)):
                output = page.inbox_message_html(mail, actions, self.now)
                tags = Tags()
                tags.feed(output)
                self.assertFalse(set(tags.names) & {"a", "img", "script", "iframe"})
                self.assertIn("&lt;img", output)
                self.assertNotRegex(output, r"!?\[[^\]]*\]\(")

    def test_active_deadlines_are_highlighted_without_false_archive_overdue(self):
        for state in page.STATUSES:
            with self.subTest(state=state):
                output = page.inbox_message_html(message(), [action(status=state, due_at="2026-09-05")], self.now)
                if state in page.ACTIVE_STATUSES:
                    self.assertIn("已逾期", output)
                    self.assertIn("mail-inbox-urgent", output)
                else:
                    self.assertNotIn("已逾期", output)
                    self.assertNotIn("mail-inbox-urgent", output)

    def test_date_only_today_is_not_overdue_and_archived_deadline_does_not_win(self):
        actions = [action("archived", status="done", due_at="2026-09-01"),
                   action("current", due_at="2026-09-06")]
        output = page.inbox_message_html(message(), actions, self.now)
        self.assertIn("今日截止", output)
        self.assertIn("09-06", output)
        self.assertNotIn("已逾期", output)
        self.assertIn("2 项事项", output)

    def test_unknown_deadline_is_explicit_only_for_active_items(self):
        self.assertIn("截止待确认", page.inbox_message_html(message(), [action()], self.now))
        self.assertNotIn("截止待确认", page.inbox_message_html(message(), [], self.now))
        self.assertNotIn("已逾期", page.inbox_message_html(message(), [action(due_at="下周")], self.now))

    def render_mail(self, actions, *, authenticated=True, source="github"):
        mail = message(subject="首屏邮件主题", summary="首屏邮件摘要")
        snapshot = {"messages": [mail], "actions": actions}
        before = copy.deepcopy(snapshot)
        ui, gateway = InboxUI(authenticated), Mock()
        loaded = {"snapshot": snapshot, "version": "current-version", "source": source}
        with patch.object(page, "st", ui):
            page.render_inbox_message(mail, snapshot, loaded, gateway, self.now)
        self.assertEqual(before, snapshot)
        gateway.save_action_updates.assert_not_called()
        return ui, gateway

    def test_subject_summary_and_editor_are_visible_without_expanding_details(self):
        ui, gateway = self.render_mail([action()])
        visible = " ".join(event["value"] for event in ui.events
                           if event["kind"] == "markdown" and event["expander_depth"] == 0)
        self.assertIn("首屏邮件主题", visible)
        self.assertIn("首屏邮件摘要", visible)
        controls = [event for event in ui.events if event["kind"] == "selectbox"]
        self.assertEqual(1, len(controls))
        control = controls[0]
        self.assertEqual(0, control["expander_depth"])
        self.assertIs(page.remember_status, control["kwargs"]["on_change"])
        self.assertEqual("a1", control["kwargs"]["args"][0])
        self.assertIs(gateway, control["kwargs"]["args"][2])
        self.assertEqual("current-version", control["kwargs"]["args"][3])
        self.assertFalse(control["kwargs"]["disabled"])

    def test_mixed_mail_has_distinct_controls_with_original_saved_states(self):
        ui, _ = self.render_mail([action("pending-id"), action("done-id", status="done"),
                                  action("other-mail", message_id="m2")])
        controls = [event["kwargs"] for event in ui.events if event["kind"] == "selectbox"]
        self.assertEqual(["pending-id", "done-id"], [control["args"][0] for control in controls])
        self.assertEqual(2, len({control["key"] for control in controls}))
        self.assertEqual(["pending", "done"], [ui.session_state[control["key"]] for control in controls])
        self.assertTrue(all(control["on_change"] is page.remember_status for control in controls))

    def test_no_action_mail_has_visible_explanation_without_status_or_save_controls(self):
        ui, _ = self.render_mail([])
        self.assertTrue(any(event["value"] == "尚未提取处理事项" and event["expander_depth"] == 0
                            for event in ui.events))
        self.assertFalse(any(event["kind"] in {"selectbox", "button"} for event in ui.events))
        self.assertNotIn("mail_action_drafts", ui.session_state)

    def test_status_controls_stay_readonly_without_authentication_or_with_local_preview(self):
        for authenticated, source in ((False, "github"), (True, "local_readonly")):
            with self.subTest(authenticated=authenticated, source=source):
                ui, _ = self.render_mail([action()], authenticated=authenticated, source=source)
                controls = [event for event in ui.events if event["kind"] == "selectbox"]
                self.assertEqual(1, len(controls))
                self.assertTrue(controls[0]["kwargs"]["disabled"])

    def test_opening_inbox_renders_all_mail_without_default_date_restriction(self):
        messages = [message("old", subject="很早的邮件", received_at="2026-01-01T08:00:00+08:00"),
                    message("unrelated", subject="不相关邮件"), message("no-action", subject="尚未提取的邮件")]
        snapshot = {"messages": messages, "actions": [action("a1", "old"),
                                                      action("a2", "unrelated", "out_of_scope")]}
        loaded = {"snapshot": snapshot, "version": "current-version", "source": "github"}
        ui = InboxUI()
        with patch.object(page, "st", ui):
            page.render_inbox(snapshot, loaded, Mock(), self.now)
        visible = " ".join(event["value"] for event in ui.events
                           if event["kind"] == "markdown" and event["expander_depth"] == 0)
        for mail in messages:
            self.assertIn(mail["subject"], visible)


if __name__ == "__main__":
    unittest.main()
