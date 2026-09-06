import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from utils import mail_workspace as mail


class MailWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "workspace"
        self.download = self.base / "实际下载通知.docx"
        self.download.write_bytes(b"verified attachment content")
        mail.initialize(self.root, "sample@example.edu")

    def batch(self, kind="daily", complete=True):
        return {
            "schema_version": 1, "account": "sample@example.edu", "kind": kind,
            "id": "run-1", "started_at": "2026-09-05T19:58:00+08:00",
            "finished_at": "2026-09-05T20:00:00+08:00",
            "window": {"since": "2026-09-05T00:00:00+08:00",
                       "through": "2026-09-05T20:00:00+08:00", "complete": complete},
            "messages": [{"id": "mail/../../stable-id", "received_at": "2026-09-05T18:30:00+08:00",
                          "sender": "教务部门", "subject": "提交反馈", "folder": "收件箱",
                          "category": "教学", "summary": "请教学单位提交反馈",
                          "source_url": "https://mail.nsu.edu.cn/owa/?id=123&token=never-export#secret",
                          "body_text": "原邮件完整可见正文，仅保存在本机。",
                          "attachments": [{"id": "attachment-1", "name": "../../通知.docx",
                                           "download_path": str(self.download)}]}],
            "actions": [{"id": "action-1", "message_id": "mail/../../stable-id", "title": "提交反馈",
                         "requirement": "提交教学单位反馈表", "owner": "教学单位",
                         "due_at": "2026-09-07", "due_text": "9月7日下班前", "due_basis": "邮件正文",
                         "recipient": "教务部门", "submission_method": "邮件", "status": "pending"}],
            "errors": [],
        }

    def test_real_attachment_and_snapshot_are_archived_idempotently(self):
        batch = self.batch()
        first = mail.ingest(self.root, batch)
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        second = mail.ingest(self.root, batch)
        after = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(first, second)
        self.assertEqual(before, after)
        data = mail.load_dashboard(self.root)
        self.assertEqual(1, len(data["messages"]))
        self.assertEqual(1, len(data["runs"]))
        message = data["messages"][0]
        self.assertNotIn("body_text", message)
        attachment = message["attachments"][0]
        self.assertTrue((self.root / attachment["path"]).resolve().is_relative_to(self.root))
        self.assertEqual(self.download.read_bytes(), (self.root / attachment["path"]).read_bytes())
        snapshot = json.loads((self.root / message["archive_path"]).read_text(encoding="utf-8"))
        self.assertFalse(snapshot["is_original_eml"])
        self.assertEqual(batch["messages"][0]["body_text"], snapshot["body_text"])
        self.assertEqual("success", first["status"])

    def test_changed_body_and_same_name_attachment_never_overwrite_original(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        old = mail.load_dashboard(self.root)["messages"][0]
        old_snapshot = self.root / old["archive_path"]
        old_attachment = self.root / old["attachments"][0]["path"]
        snapshot_bytes, attachment_bytes = old_snapshot.read_bytes(), old_attachment.read_bytes()
        batch["messages"][0]["body_text"] = "修改后的正文"
        self.download.write_bytes(b"new version")
        mail.ingest(self.root, batch)
        new = mail.load_dashboard(self.root)["messages"][0]
        self.assertNotEqual(old["archive_path"], new["archive_path"])
        self.assertNotEqual(old["attachments"][0]["path"], new["attachments"][0]["path"])
        self.assertEqual(snapshot_bytes, old_snapshot.read_bytes())
        self.assertEqual(attachment_bytes, old_attachment.read_bytes())

    def test_hash_deduplication_reuses_content_across_messages(self):
        batch = self.batch()
        second_message = copy.deepcopy(batch["messages"][0])
        second_message["id"] = "other-mail"
        second_message["attachments"][0]["name"] = "相同内容另一名称.docx"
        batch["messages"].append(second_message)
        mail.ingest(self.root, batch)
        messages = mail.load_dashboard(self.root)["messages"]
        self.assertEqual(messages[0]["attachments"][0]["path"], messages[1]["attachments"][0]["path"])

    def test_missing_attachment_and_sample_do_not_advance_cursor(self):
        batch = self.batch(kind="sample")
        self.assertEqual("success", mail.ingest(self.root, batch)["status"])
        self.assertIsNone(mail.status(self.root)["coverage"]["through"])
        batch["kind"] = "daily"
        batch["messages"][0]["attachments"].append({"id": "missing", "name": "未下载.xlsx", "status": "success"})
        result = mail.ingest(self.root, batch)
        self.assertEqual("partial", result["status"])
        self.assertIsNone(result["coverage"]["through"])
        self.assertEqual("missing", mail.load_dashboard(self.root)["messages"][0]["attachments"][1]["status"])

    def test_cursor_advances_after_retry_and_rejects_a_gap(self):
        batch = self.batch()
        batch["messages"][0]["attachments"][0]["download_path"] = str(self.base / "missing")
        self.assertEqual("partial", mail.ingest(self.root, batch)["status"])
        batch["messages"][0]["attachments"][0]["download_path"] = str(self.download)
        self.assertEqual("success", mail.ingest(self.root, batch)["status"])
        old_through = mail.status(self.root)["coverage"]["through"]
        gap = self.batch()
        gap.update(id="run-gap", messages=[], actions=[])
        gap["window"].update(since="2026-09-06T00:00:00+08:00", through="2026-09-06T20:00:00+08:00")
        result = mail.ingest(self.root, gap)
        self.assertEqual("partial", result["status"])
        self.assertEqual(old_through, result["coverage"]["through"])

    def test_invalid_batch_is_rejected_before_archiving(self):
        batch = self.batch()
        batch["actions"][0]["due_basis"] = ""
        before = (self.root / "dashboard.json").read_bytes()
        with self.assertRaises(ValueError):
            mail.ingest(self.root, batch)
        self.assertEqual(before, (self.root / "dashboard.json").read_bytes())
        self.assertEqual([], list((self.root / "archive").rglob("*.json")))
        batch["actions"][0]["due_basis"] = "邮件正文"
        batch["messages"][0]["received_at"] = "2026-09-04T18:30:00+08:00"
        with self.assertRaises(ValueError):
            mail.ingest(self.root, batch)

    def test_cloud_export_removes_body_secrets_and_absolute_source_paths(self):
        batch = self.batch()
        batch["password"] = "never-store-password"
        batch["messages"][0]["cookie"] = "never-store-cookie"
        batch["messages"][0]["headers_text"] = "Header: full-header-local-only"
        batch["messages"][0]["internet_message_id"] = "local-only-additional-message-id"
        mail.ingest(self.root, batch)
        output = self.base / "private-export.json"
        mail.export_snapshot(self.root, output)
        raw = output.read_text(encoding="utf-8")
        self.assertNotIn("原邮件完整可见正文", raw)
        self.assertNotIn("never-store", raw)
        self.assertNotIn("never-export", raw)
        self.assertNotIn("download_path", raw)
        self.assertNotIn("full-header-local-only", raw)
        self.assertNotIn("local-only-additional-message-id", raw)
        self.assertNotIn(str(self.download), raw)
        data = json.loads(raw)
        self.assertEqual("https://mail.nsu.edu.cn/owa/", data["messages"][0]["source_url"])
        self.assertEqual("2026-09-07", data["actions"][0]["due_at"])
        local_snapshot = json.loads((self.root / data["messages"][0]["archive_path"]).read_text(encoding="utf-8"))
        self.assertEqual("Header: full-header-local-only", local_snapshot["headers_text"])
        with self.assertRaises(ValueError):
            mail.export_snapshot(self.root, self.root / "dashboard.json")

    def test_paths_and_source_urls_are_constrained(self):
        for relative in ("../outside", "C:/escape", "a/../../escape", "a\\escape"):
            with self.assertRaises(ValueError):
                mail._inside(self.root, relative)
        for url in ("https://evil.example/owa/", "https://mail.nsu.edu.cn/other/",
                    "https://user:password@mail.nsu.edu.cn/owa/", "https://mail.nsu.edu.cn/owa/%2e%2e/file"):
            self.assertEqual("", mail.sanitize_source_url(url))
        self.assertEqual("_CON.txt", mail.safe_filename("CON.txt"))
        self.assertEqual("中文通知.docx", mail.safe_filename("中文通知.docx"))

    def test_reports_preserve_date_only_deadline_and_prior_evening_window(self):
        mail.ingest(self.root, self.batch())
        mail.generate_report(self.root, "daily", "2026-09-05T20:00:00+08:00")
        incomplete_report = mail.generate_report(self.root, "daily", "2026-09-06T20:00:00+08:00")
        self.assertFalse(incomplete_report["coverage_complete"])
        mail.generate_report(self.root, "morning", "2026-09-07T09:00:00+08:00")
        data = mail.load_dashboard(self.root)
        self.assertEqual("2026-09-05T20:00:00+08:00", data["reports"][1]["period_start"])
        markdown = data["reports"][2]["markdown"]
        self.assertIn("今日到期", markdown)
        self.assertIn("9月7日下班前", markdown)
        self.assertNotIn("17:00", markdown)
        self.assertIn("尚未覆盖完整统计窗口", markdown)

    def test_manual_status_is_not_reset_by_new_collection(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        path = self.root / "dashboard.json"
        data = mail.load_dashboard(self.root)
        data["actions"][0].update(status="done", completed_at="2026-09-06T08:00:00+08:00", updated_at="2026-09-06T08:00:00+08:00")
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        mail.ingest(self.root, batch)
        action = mail.load_dashboard(self.root)["actions"][0]
        self.assertEqual("done", action["status"])
        self.assertEqual("2026-09-06T08:00:00+08:00", action["completed_at"])

    def test_non_actionable_states_survive_recollection_and_new_actions_stay_active(self):
        batch = self.batch()
        original = batch["actions"][0]
        batch["actions"] = [{**original, "id": state, "status": state}
                            for state in ("no_action", "out_of_scope")]
        mail.ingest(self.root, batch)
        before = {action["id"]: action for action in mail.load_dashboard(self.root)["actions"]}
        batch.update(id="recollection", started_at="2026-09-06T19:58:00+08:00",
                     finished_at="2026-09-06T20:00:00+08:00")
        for action in batch["actions"]:
            action.update(status="pending", requirement="补充后的要求")
        batch["actions"].append({**original, "id": "new-notification"})
        mail.ingest(self.root, batch)
        after = {action["id"]: action for action in mail.load_dashboard(self.root)["actions"]}
        for state in ("no_action", "out_of_scope"):
            self.assertIsNone(after[state]["completed_at"])
            self.assertEqual("补充后的要求", after[state]["requirement"])
            for field in ("status", "completed_at", "updated_at"):
                self.assertEqual(before[state][field], after[state][field])
        self.assertEqual("pending", after["new-notification"]["status"])

    def test_reports_link_only_active_actions_and_export_keeps_legacy_reports_compatible(self):
        batch = self.batch()
        original = batch["actions"][0]
        batch["actions"] = [{**original, "id": state, "title": state, "status": state}
                            for state in mail.ACTION_STATUSES]
        mail.ingest(self.root, batch)
        for kind in ("daily", "morning", "weekly"):
            result = mail.generate_report(self.root, kind, "2026-09-06T20:00:00+08:00")
            report = next(row for row in mail.load_dashboard(self.root)["reports"]
                          if row["id"] == result["report_id"])
            self.assertEqual(["in_progress", "needs_confirmation", "pending"], report["action_ids"])
            self.assertEqual(3, result["active_action_count"])
            active_section = report["markdown"].split("## 待处理与时间节点\n", 1)[1].split("\n## ", 1)[0]
            for state in ("done", "no_action", "out_of_scope"):
                self.assertNotIn(state, active_section)
        data = mail.load_dashboard(self.root)
        data["reports"].append({"id": "legacy-report", "kind": "daily", "markdown": "原有简报"})
        exported = mail.public_snapshot(data, self.root)
        self.assertEqual(data["reports"][0]["action_ids"], exported["reports"][0]["action_ids"])
        self.assertNotIn("action_ids", exported["reports"][-1])
        exported["reports"][0]["action_ids"].append("export-only")
        self.assertNotIn("export-only", data["reports"][0]["action_ids"])

    def test_morning_includes_overdue_unknown_today_and_next_three_calendar_days(self):
        batch = self.batch()
        original = batch["actions"][0]
        deadlines = {"overdue": "2026-09-05", "today": "2026-09-06",
                     "third-day": "2026-09-09", "fourth-day": "2026-09-10",
                     "unknown": None}
        batch["actions"] = [{**original, "id": key, "due_at": due} for key, due in deadlines.items()]
        mail.ingest(self.root, batch)
        result = mail.generate_report(self.root, "morning", "2026-09-06T09:00:00+08:00")
        report = mail.load_dashboard(self.root)["reports"][0]
        self.assertEqual(["overdue", "today", "third-day", "unknown"], report["action_ids"])
        self.assertEqual(4, result["active_action_count"])

    def test_weekly_completed_count_uses_current_done_state_and_report_period(self):
        batch = self.batch()
        original = batch["actions"][0]
        states = [
            ("week-start", "done", "2026-08-31T00:00:00+08:00"),
            ("week-end", "done", "2026-09-06T20:00:00+08:00"),
            ("prior-week", "done", "2026-08-30T23:59:59+08:00"),
            ("future", "done", "2026-09-06T20:00:01+08:00"),
            ("declined", "no_action", "2026-09-05T20:00:00+08:00"),
            ("unrelated", "out_of_scope", "2026-09-05T20:00:00+08:00"),
            ("reopened", "pending", "2026-09-05T20:00:00+08:00"),
        ]
        batch["actions"] = [{**original, "id": key, "title": key, "status": state,
                             "completed_at": completed} for key, state, completed in states]
        mail.ingest(self.root, batch)
        result = mail.generate_report(self.root, "weekly", "2026-09-06T20:00:00+08:00")
        report = mail.load_dashboard(self.root)["reports"][0]
        completed_section = report["markdown"].split("## 本周已完成事项\n", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(2, result["completed_action_count"])
        self.assertIn("本周已完成：2 项。", completed_section)
        self.assertIn("week-start｜完成时间：2026-08-31 00:00", completed_section)
        self.assertIn("week-end｜完成时间：2026-09-06 20:00", completed_section)
        for key in ("prior-week", "future", "declined", "unrelated", "reopened"):
            self.assertNotIn(key, completed_section)
        self.assertEqual(["reopened"], report["action_ids"])

    def test_declared_hash_mismatch_does_not_archive_a_success(self):
        batch = self.batch()
        batch["messages"][0]["attachments"][0]["sha256"] = hashlib.sha256(b"different").hexdigest()
        result = mail.ingest(self.root, batch)
        self.assertEqual("partial", result["status"])
        self.assertEqual([], list((self.root / "archive").rglob(".mail-copy-*.tmp")))
        attachment = mail.load_dashboard(self.root)["messages"][0]["attachments"][0]
        self.assertEqual("error", attachment["status"])
        self.assertFalse(attachment["path"])

    def test_incomplete_attachment_inventory_blocks_cursor(self):
        batch = self.batch()
        batch["messages"][0]["expected_attachment_count"] = 2
        self.assertEqual("partial", mail.ingest(self.root, batch)["status"])
        self.assertIsNone(mail.status(self.root)["coverage"]["through"])

    def test_metadata_only_retry_retains_body_snapshot(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        before = mail.load_dashboard(self.root)["messages"][0]["archive_path"]
        del batch["messages"][0]["body_text"]
        mail.ingest(self.root, batch)
        self.assertEqual(before, mail.load_dashboard(self.root)["messages"][0]["archive_path"])
        batch["messages"][0]["id"] = "new-id-without-body"
        with self.assertRaises(ValueError):
            mail.ingest(self.root, batch)

    def test_same_day_explicit_time_can_be_overdue_without_inventing_date_only_time(self):
        batch = self.batch()
        batch["actions"][0].update(due_at="2026-09-07T08:00:00+08:00", due_text="9月7日上午8点前")
        mail.ingest(self.root, batch)
        mail.generate_report(self.root, "morning", "2026-09-07T09:00:00+08:00")
        self.assertIn("已逾期", mail.load_dashboard(self.root)["reports"][0]["markdown"])

    def test_collection_metadata_change_does_not_advance_status_version(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        before = mail.load_dashboard(self.root)["actions"][0]
        batch.update(started_at="2026-09-06T19:58:00+08:00", finished_at="2026-09-06T20:00:00+08:00")
        batch["actions"][0].update(requirement="追加了附件格式说明", status="done",
                                   completed_at="2026-09-06T19:00:00+08:00")
        mail.ingest(self.root, batch)
        after = mail.load_dashboard(self.root)["actions"][0]
        self.assertEqual("追加了附件格式说明", after["requirement"])
        for field in ("status", "completed_at", "updated_at"):
            self.assertEqual(before[field], after[field])

    def test_retained_attachment_index_cannot_hide_missing_local_file(self):
        batch = self.batch()
        mail.ingest(self.root, batch)
        path = self.root / mail.load_dashboard(self.root)["messages"][0]["attachments"][0]["path"]
        path.unlink()
        batch["messages"][0]["attachments"] = []
        result = mail.ingest(self.root, batch)
        self.assertEqual("partial", result["status"])
        self.assertEqual(1, result["incomplete_attachments"])
        self.assertFalse(result["coverage"]["complete"])

    def test_external_diagnostics_stay_local_even_if_they_contain_credential_urls(self):
        batch = self.batch()
        batch["errors"] = ["failed https://mail.nsu.edu.cn/owa/?access_token=private-sentinel"]
        batch["messages"][0]["attachments"].append({"id": "a2", "name": "未下载.pdf",
                                                   "status": "error", "error": "Authorization: Bearer private-sentinel"})
        mail.ingest(self.root, batch)
        local = mail.load_dashboard(self.root)
        public = mail.cloud_snapshot(self.root)
        self.assertIn("private-sentinel", json.dumps(local))
        self.assertNotIn("private-sentinel", json.dumps(public))
        self.assertIn("详细原因仅保存在本机运行记录", public["runs"][0]["errors"][0])

    def test_report_keeps_confirmation_status_alongside_deadline_warning(self):
        batch = self.batch()
        batch["actions"][0]["status"] = "needs_confirmation"
        mail.ingest(self.root, batch)
        mail.generate_report(self.root, "morning", "2026-09-08T09:00:00+08:00")
        markdown = mail.load_dashboard(self.root)["reports"][0]["markdown"]
        self.assertIn("待确认 · 已逾期 · 提交反馈", markdown)


if __name__ == "__main__":
    unittest.main()
