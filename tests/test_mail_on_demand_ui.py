"""On-demand attachment UI checks with synthetic records and no remote I/O."""

import copy
import importlib.util
import unittest
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils.mail_mime import parse_message


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "23_24_mail_workbench.py"
SPEC = importlib.util.spec_from_file_location("mail_on_demand_page", PAGE_PATH)
page = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(page)


def message(identifier="mail-one", **fields):
    return {"id": identifier, "subject": "按需存档合成通知", "sender": "合成部门", "category": "教学",
            "received_at": "2026-09-08T08:00:00+08:00", "summary": "合成摘要",
            "attachments": [{"id": "attachment-one", "name": "合成附件.pdf", "status": "not_requested"}], **fields}


def snapshot():
    return {"account": "fixture@example.invalid", "collection_storage": "on_demand",
            "updated_at": "2026-09-08T10:00:00+08:00",
            "coverage": {"complete": True, "since": "2026-09-01T00:00:00+08:00", "through": "2026-09-08T10:00:00+08:00"},
            "runs": [{"kind": "daily", "status": "success"}], "reports": [], "messages": [message()],
            "actions": [{"id": "action-one", "message_id": "mail-one", "status": "pending", "title": "合成事项"}]}


def filing_failure(status="error"):
    return {"request_id": "fixture-request", "requested_at": "2026-09-08T09:00:00+08:00",
            "updated_at": "2026-09-08T09:10:00+08:00", "status": status, "destination": "",
            "saved_count": 0, "total_count": 1, "error_count": 1, "error_codes": ["ATTACHMENT_EMPTY"]}


class OnDemandSummaryTests(unittest.TestCase):
    def test_unrequested_attachments_are_not_incomplete_or_failed_in_top_bar(self):
        data = snapshot()
        html = page.snapshot_status_html(data)
        self.assertIn("附件按需存档", html)
        self.assertNotIn("份附件待补", html)
        self.assertNotIn("封存档待补", html)
        self.assertNotIn("现有附件均已归档", html)
        self.assertEqual(0, page.incomplete_attachment_count(data["messages"]))
        self.assertEqual("未选择存档", page.ATTACHMENT_STATUSES["not_requested"])

    def test_on_demand_top_bar_does_not_count_unselected_legacy_missing_files(self):
        data = snapshot()
        data["messages"][0]["attachments"][0]["status"] = "missing"
        html = page.snapshot_status_html(data)
        self.assertIn("附件按需存档", html)
        self.assertNotIn("附件待补", html)
        self.assertNotIn("封存档待补", html)

    def test_real_filing_errors_count_once_per_still_archived_mail(self):
        data = snapshot()
        data["messages"][0]["filing"] = filing_failure()
        data["actions"][0]["status"] = "archived"
        data["actions"].append({"id": "second-child", "message_id": "mail-one", "status": "archived"})
        data["messages"].extend([message("no-actions", triage_status="archived", filing=filing_failure("partial")),
                                 message("cancelled-choice", triage_status="pending", filing=filing_failure()),
                                 message("stale-triage", triage_status="archived", filing=filing_failure())])
        data["actions"].append({"id": "changed-child", "message_id": "stale-triage", "status": "done"})
        self.assertEqual(2, page.incomplete_filing_count(data["messages"], data["actions"]))
        self.assertIn("2 封存档待补", page.snapshot_status_html(data))

    def test_pending_and_success_requests_do_not_show_failure_count(self):
        data = snapshot()
        data["actions"][0]["status"] = "archived"
        for status in ("pending", "success", "cancelled"):
            with self.subTest(status=status):
                data["messages"][0]["filing"] = filing_failure(status)
                self.assertNotIn("封存档待补", page.snapshot_status_html(data))

    def test_legacy_mode_retains_existing_attachment_completeness_display(self):
        data = snapshot()
        data.pop("collection_storage")
        data["messages"][0]["attachments"][0]["status"] = "missing"
        self.assertIn("1 份附件待补", page.snapshot_status_html(data))
        data["messages"][0]["attachments"][0]["status"] = "success"
        self.assertIn("现有附件均已归档", page.snapshot_status_html(data))

    def test_on_demand_incomplete_collection_warning_is_not_an_unsaved_attachment_warning(self):
        data = snapshot()
        data["coverage"]["complete"] = False
        warning = page.coverage_warning(data)
        self.assertIn("采集时段仍待核对", warning)
        self.assertNotIn("附件", warning)


class OnDemandAttachmentIndexTests(unittest.TestCase):
    def ui(self):
        return SimpleNamespace(caption=Mock(), dataframe=Mock(), info=Mock())

    def test_unrequested_index_has_no_failure_banner_or_error_but_preserves_history(self):
        data = snapshot()
        attachments = data["messages"][0]["attachments"]
        attachments[0]["error"] = "fixture-previous-technical-error"
        attachments.append({"id": "history", "name": "历史附件.pdf", "status": "success",
                            "path": "archive/previous/历史附件.pdf", "sha256": "a" * 64, "size": 12})
        before = copy.deepcopy(data)
        ui = self.ui()
        with patch.object(page, "st", ui):
            page.render_attachments(data["messages"], snapshot=data)
        captions = " ".join(call.args[0] for call in ui.caption.call_args_list)
        self.assertIn("选择存档后才保存附件", captions)
        self.assertIn("保留此前的归档记录", captions)
        self.assertNotIn("待补", captions)
        rows = ui.dataframe.call_args.args[0]
        self.assertEqual("未选择存档", rows[0]["状态"])
        self.assertEqual("", rows[0]["失败原因"])
        self.assertEqual("已归档并核验", rows[1]["状态"])
        self.assertEqual("archive/previous/历史附件.pdf", rows[1]["本机相对位置"])
        self.assertEqual(before, data)

    def test_requested_filing_failure_still_has_an_index_notice(self):
        data = snapshot()
        data["messages"][0]["filing"] = filing_failure()
        data["actions"][0]["status"] = "archived"
        ui = self.ui()
        with patch.object(page, "st", ui):
            page.render_attachments(data["messages"], snapshot=data)
        captions = " ".join(call.args[0] for call in ui.caption.call_args_list)
        self.assertIn("1 封存档待补", captions)

    def test_normal_state_and_filing_choices_do_not_change_between_modes(self):
        options = []
        for mode in (None, "on_demand"):
            data = snapshot()
            data["collection_storage"] = mode
            loaded = {"snapshot": data, "source": "github", "version": "fixture"}
            ui = SimpleNamespace(session_state={"mail_authenticated": True}, selectbox=Mock(), caption=Mock())
            with patch.object(page, "st", ui):
                page.render_status_control(data["actions"][0], loaded, Mock(), context="inbox", labels=page.INBOX_STATUSES)
            options.append(ui.selectbox.call_args.args[1])
        self.assertEqual(options[0], options[1])
        self.assertEqual(7, len(options[0]))
        self.assertIn("archived", options[0])


class OnDemandAppTests(unittest.TestCase):
    def test_unselected_mail_has_no_filing_warning_and_no_initial_network_write(self):
        from streamlit.testing.v1 import AppTest

        data = snapshot()
        original = copy.deepcopy(data)
        app = AppTest.from_file(str(PAGE_PATH))
        app.session_state["mail_loaded"] = {"snapshot": data, "source": "github", "version": "fixture"}
        app.session_state["mail_authenticated"] = True
        gateway = page.get_mail_gateway()
        with patch.object(page.budget_auth, "get_budget_password", return_value="synthetic-password"), \
                patch.object(gateway, "load_snapshot", side_effect=AssertionError("No real mail reads")) as load, \
                patch.object(gateway, "save_action_updates", side_effect=AssertionError("No action writes")) as save_action, \
                patch.object(gateway, "save_message_updates", side_effect=AssertionError("No message writes")) as save_message, \
                patch.object(gateway, "save_filing_requests", side_effect=AssertionError("No filing requests")) as file_request:
            app.run(timeout=15)
            self.assertEqual([], list(app.exception))
        text = " ".join(element.value for element in [*app.markdown, *app.caption, *app.error, *app.warning])
        self.assertIn("附件按需存档", text)
        self.assertIn("平时只整理摘要与待办", text)
        self.assertNotIn("份附件待补", text)
        self.assertNotIn("封存档待补", text)
        self.assertNotIn("归档失败", text)
        self.assertEqual([], list(app.error))
        self.assertEqual([], list(app.warning))
        control = next(control for control in app.tabs[0].selectbox if control.label == "当前状态")
        self.assertEqual("pending", control.value)
        self.assertIn("存档", control.options)
        self.assertEqual(original, data)
        for mock in (load, save_action, save_message, file_request):
            mock.assert_not_called()


class OnDemandMimeContractTests(unittest.TestCase):
    def test_structure_flag_is_independent_of_empty_attachment_content(self):
        message = EmailMessage()
        message.set_content("Synthetic fixture body")
        message.add_attachment(b"", maintype="application", subtype="octet-stream", filename="empty.xlsx")
        message.set_boundary("fixture-structure-boundary")
        raw = message.as_bytes()
        args = {"received_at": "2026-09-08T08:00:00+08:00", "folder": "INBOX", "source_url": ""}
        parsed = parse_message(raw, **args)
        self.assertIs(True, parsed["mime_structure_complete"])
        self.assertIs(False, parsed["attachments_complete"])
        truncated = raw.removesuffix(b"--fixture-structure-boundary--\n")
        self.assertNotEqual(raw, truncated)
        self.assertIs(False, parse_message(truncated, **args)["mime_structure_complete"])


if __name__ == "__main__":
    unittest.main()
