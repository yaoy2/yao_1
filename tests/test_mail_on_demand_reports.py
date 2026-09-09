"""Report filing counts use current choices, never unsaved attachment indexes."""

import copy
import tempfile
import unittest
from pathlib import Path

from utils import mail_workspace as mail
from utils.mail_filing_state import validate_filing


AT = "2026-09-09T20:00:00+08:00"


def receipt(status="pending", *, saved=0, total=0):
    failed = status in {"partial", "error"}
    return validate_filing({
        "request_id": "a" * 32, "requested_at": "2026-09-08T09:00:00+08:00",
        "updated_at": "2026-09-08T10:00:00+08:00", "status": status,
        "destination": "." if saved else "", "saved_count": saved, "total_count": total,
        "error_count": int(failed), "error_codes": ["ATTACHMENT_MISSING"] if failed else [],
    })


def message(identifier, *, selected=False, filing=None, attachment_status="not_requested", **fields):
    result = {"id": identifier, "received_at": "2026-09-09T08:00:00+08:00",
              "category": "教学", "subject": "合成通知", "summary": "合成摘要",
              "triage_status": "archived" if selected else "pending",
              "attachments": [{"id": identifier + "-file", "status": attachment_status}], **fields}
    if filing is not None:
        result["filing"] = filing
    return result


class OnDemandReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "workspace"
        mail.initialize(self.root, "synthetic@example.invalid")
        self.data = mail.load_dashboard(self.root)
        self.data["collection_storage"] = "on_demand"
        self.data["coverage"] = {"since": "2026-09-07T00:00:00+08:00", "through": AT,
                                 "complete": True, "note": ""}

    def report(self, kind="daily"):
        before = copy.deepcopy(self.data)
        mail._atomic_json(self.root / "dashboard.json", self.data)
        mail.generate_report(self.root, kind, AT)
        after = mail.load_dashboard(self.root)
        for key in ("messages", "actions", "coverage", "runs"):
            self.assertEqual(before[key], after[key])
        return after["reports"][-1]["markdown"]

    def assert_counts(self, markdown, *, requests=0, waiting=0, incomplete=0, complete=0, saved=0):
        self.assertIn(f"当前存档请求：{requests} 封；等待保存：{waiting} 封；"
                      f"存档待补：{incomplete} 封；保存完成：{complete} 封。", markdown)
        self.assertIn(f"当前所选存档回执已保存附件：{saved} 个", markdown)
        self.assertNotIn("未完成附件", markdown)

    def test_unselected_not_requested_and_legacy_missing_never_count_as_failed(self):
        self.data["messages"] = [message("new"), message("old", attachment_status="missing"),
                                  message("old-error", attachment_status="error")]
        for kind in ("daily", "morning", "weekly"):
            with self.subTest(kind=kind):
                markdown = self.report(kind)
                self.assert_counts(markdown)
                self.assertNotIn("下载失败", markdown)

    def test_partial_and_error_count_once_per_currently_selected_mail(self):
        self.data["messages"] = [
            message("partial", filing=receipt("partial", saved=1, total=2)),
            message("error", selected=True, filing=receipt("error", total=1)),
        ]
        self.data["actions"] = [
            {"id": "child-one", "message_id": "partial", "status": "archived"},
            {"id": "child-two", "message_id": "partial", "status": "archived"},
        ]
        self.assert_counts(self.report(), requests=2, incomplete=2, saved=1)

    def test_pending_and_selected_without_receipt_wait_without_failure(self):
        self.data["messages"] = [
            message("pending", selected=True, filing=receipt()),
            message("not-queued", selected=True, attachment_status="missing"),
        ]
        self.assert_counts(self.report(), requests=2, waiting=2)

    def test_cancelled_choices_and_receipts_are_excluded_even_with_stale_results(self):
        self.data["messages"] = [
            message("unselected-error", filing=receipt("error", total=1)),
            message("unselected-saved", filing=receipt("success", saved=3, total=3)),
            message("cancelled", selected=True, filing=receipt("cancelled")),
            message("stale-triage", selected=True, filing=receipt("partial", saved=1, total=2)),
        ]
        # Once a mail has actions, current action choices supersede old triage.
        self.data["actions"] = [{"id": "changed-child", "message_id": "stale-triage", "status": "done"}]
        self.assert_counts(self.report())

    def test_successful_empty_mail_is_normal_and_older_saved_count_is_not_today(self):
        self.data["messages"] = [
            message("empty", selected=True, filing=receipt("success"), attachments=[]),
            message("older", selected=True, filing=receipt("success", saved=2, total=2),
                    received_at="2026-09-01T08:00:00+08:00"),
        ]
        markdown = self.report()
        self.assert_counts(markdown, requests=2, complete=2, saved=2)
        self.assertIn("其中无附件邮件：1 封，已完成核对，0 个附件为正常结果。", markdown)
        self.assertIn("含此前保存，不代表本统计时段新增保存量", markdown)
        self.assertIn("最近成功游标：" + AT + "。", markdown)

    def test_full_and_legacy_modes_preserve_attachment_counting(self):
        self.data["messages"] = [message("unsaved"), message("missing", attachment_status="missing"),
                                  message("saved", attachment_status="success")]
        for mode in (None, "full"):
            with self.subTest(mode=mode):
                if mode is None:
                    self.data.pop("collection_storage", None)
                else:
                    self.data["collection_storage"] = mode
                markdown = self.report()
                self.assertIn("未完成附件：2；最近成功游标：" + AT + "。", markdown)
                self.assertNotIn("当前存档请求", markdown)
                self.assertNotIn("保存方式：", markdown)


if __name__ == "__main__":
    unittest.main()
