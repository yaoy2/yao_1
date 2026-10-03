import ast
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils import budget_db, web_memo_db
from utils.data_sync_validation import validate_backup


ROOT = Path(__file__).resolve().parents[1]


class PageStopped(BaseException):
    pass


def page_functions(filename, **namespace):
    tree = ast.parse((ROOT / "pages" / filename).read_text(encoding="utf-8"))
    functions = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)], type_ignores=[])
    result = {"os": os, "re": re, "validate_backup": validate_backup, **namespace}
    exec(compile(functions, filename, "exec"), result)
    return result


def fake_streamlit():
    return SimpleNamespace(secrets={}, session_state={}, error=Mock(), info=Mock(), warning=Mock(),
                           stop=Mock(side_effect=PageStopped))


def memo(record_id=7, content="正文", **changes):
    return {"id": record_id, "memo_date": "2026-10-02", "content": content,
            "category": "摘录", "tags": ["材料"], "palette_name": "默认色卡",
            "display_order": record_id, "is_archived": False, **changes}


def expense(record_id=7, amount=12.5, **changes):
    return {"id": record_id, "record_date": "2026-10-02", "category": "学生实践费",
            "unit": "", "spender": "", "description": "测试耗材", "amount": amount,
            "reimbursement_status": "未报销", "created_at": "2026-10-02 10:00:00",
            "updated_at": "2026-10-02 10:00:00", **changes}


class MemoRestoreTest(unittest.TestCase):
    def test_date_headings_in_body_round_trip_without_splitting_records(self):
        bodies = ["## 2026-10-01\n\n昨天的内容\n\n## 2026-10-02\n\n今天的内容",
                  "先写内容\n\n## 2026-10-03", "另一条记录\n\n末段"]
        records = [memo(index + 1, body) for index, body in enumerate(bodies)]
        backup = web_memo_db.build_markdown_backup(records) + "\n\n"
        self.assertEqual(records, web_memo_db.parse_markdown_backup(backup))
        self.assertEqual(records, validate_backup("data/web_memos_backup.md", backup))

    def test_current_footer_wins_over_header_and_footer_style_body_text(self):
        bodies = ["- 分类：正文\n- 标签：无\n### 内容\n正文",
                  "- ID：99\n- 分类：正文\n- 标签：无\n### 内容\n正文\n\n## 2026-10-01\n日期小标题",
                  "正文\n- 分类：正文分类\n- 标签：正文标签\n\n## 2026-10-01\n日期小标题"]
        records = [memo(index + 1, body) for index, body in enumerate(bodies)]
        backup = web_memo_db.build_markdown_backup(records)
        self.assertEqual(records, web_memo_db.parse_markdown_backup(backup))

    def test_header_metadata_backups_preserve_body_dates_and_later_records(self):
        text = ("## 2026-10-02\n- ID：7\n- 分类：摘录\n- 标签：材料\n### 内容\n\n"
                "正文\n\n## 2026-10-01\n\n日期小标题\n- 分类：正文分类\n- 标签：正文标签\n\n"
                "## 2026-10-03\n- ID：8\n- 分类：工作记录\n- 标签：记录\n### 内容\n\n第二条\n\n")
        records = web_memo_db.parse_markdown_backup(text)
        self.assertEqual([7, 8], [record["id"] for record in records])
        self.assertEqual("正文\n\n## 2026-10-01\n\n日期小标题\n- 分类：正文分类\n- 标签：正文标签", records[0]["content"])
        self.assertEqual("摘录", records[0]["category"])
        self.assertEqual("第二条", records[1]["content"])

    def test_legacy_footer_without_ids_preserves_date_headings(self):
        text = ("## 2026-10-02\n\n正文\n\n## 2026-10-01\n\n日期小标题\n\n"
                "- 分类：摘录\n- 标签：材料\n- 色卡：默认色卡\n\n"
                "## 2026-10-03\n\n第二条\n\n- 分类：工作记录\n- 标签：记录\n\n")
        records = web_memo_db.parse_markdown_backup(text)
        self.assertEqual(2, len(records))
        self.assertEqual("正文\n\n## 2026-10-01\n\n日期小标题", records[0]["content"])
        self.assertEqual("第二条", records[1]["content"])

    def test_markdown_round_trip_preserves_lists_metadata_style_text_headings_and_blank_lines(self):
        body = "第一段\n\n- 第一项\n- 分类：这是正文中的分类说明\n- 标签：这是正文\n\n## 工作说明\n\n最后一段\n- 尾部列表"
        record = memo(content=body, is_archived=True)
        restored = web_memo_db.parse_markdown_backup(web_memo_db.build_markdown_backup([record]))
        self.assertEqual(1, len(restored))
        self.assertEqual(body, restored[0]["content"])
        self.assertEqual(record, restored[0])

    def test_explicit_content_section_keeps_metadata_style_body_lines(self):
        text = "## 2026-10-02\n- ID：7\n- 分类：摘录\n- 标签：材料\n### 内容\n\n- 分类：正文\n\n- 普通正文"
        records = web_memo_db.parse_markdown_backup(text)
        self.assertEqual("- 分类：正文\n\n- 普通正文", records[0]["content"])
        self.assertEqual("摘录", records[0]["category"])

    def test_restore_snapshot_preserves_nonsequential_ids_hidden_records_and_next_id(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(web_memo_db, "DB_PATH", str(Path(tmpdir) / "memos.db")), patch.object(web_memo_db, "BACKUP_MD_PATH", str(Path(tmpdir) / "memos.md")):
            web_memo_db.init_db()
            records = [memo(7, "- 项目\n\n正文"), memo(23, "隐藏记录", is_archived=True)]
            web_memo_db.restore_synced_records(records)
            restored = web_memo_db.get_memos(include_archived=True)
            self.assertEqual({7, 23}, {record["id"] for record in restored})
            self.assertEqual(1, len(web_memo_db.get_memos()))
            self.assertEqual("- 项目\n\n正文", next(record for record in restored if record["id"] == 7)["content"])
            web_memo_db.add_memo("2026-10-02", "新记录", classify=False)
            self.assertGreater(web_memo_db.get_memos()[0]["id"], 23)

    def test_invalid_or_duplicate_memo_snapshot_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(web_memo_db, "DB_PATH", str(Path(tmpdir) / "memos.db")), patch.object(web_memo_db, "BACKUP_MD_PATH", str(Path(tmpdir) / "memos.md")):
            web_memo_db.init_db()
            web_memo_db.restore_synced_records([memo(7, "保留原记录")])
            for records in ([memo(8), memo(0)], [memo(8), memo(8)]):
                with self.subTest(records=records), self.assertRaises(Exception):
                    web_memo_db.restore_synced_records(records)
                self.assertEqual("保留原记录", web_memo_db.get_memos()[0]["content"])


class MemoPageSyncTest(unittest.TestCase):
    def setUp(self):
        self.st = fake_streamlit()
        self.sync = Mock()
        self.functions = page_functions("03_10_memos.py", st=self.st, github_backup_sync=self.sync,
                                        web_memo_db=web_memo_db, memo_displayed_snapshot=None)

    def test_merge_accepts_remote_edit_when_local_unchanged(self):
        result = self.functions["merge_memo_snapshots"]([memo()], [memo(content="远端新正文")], [memo()])
        self.assertEqual("远端新正文", result[0]["content"])

    def test_merge_preserves_local_edit_when_remote_unchanged(self):
        result = self.functions["merge_memo_snapshots"]([memo(content="本地新正文")], [memo()], [memo()])
        self.assertEqual("本地新正文", result[0]["content"])

    def test_merge_retains_independent_new_records(self):
        result = self.functions["merge_memo_snapshots"]([memo(), memo(8, "本机新增")], [memo(), memo(9, "远端新增")], [memo()])
        self.assertEqual({7, 8, 9}, {record["id"] for record in result})

    def test_same_id_different_new_record_is_a_conflict(self):
        for baseline in (None, [memo()]):
            with self.subTest(baseline=baseline), self.assertRaises(RuntimeError):
                self.functions["merge_memo_snapshots"]([memo(), memo(8, "本机新增")], [memo(), memo(8, "远端新增")], baseline)

    def test_same_record_edited_on_both_sides_is_a_conflict(self):
        with self.assertRaises(RuntimeError):
            self.functions["merge_memo_snapshots"]([memo(content="本地改")], [memo(content="远端改")], [memo()])

    def test_sync_uses_the_version_that_was_read(self):
        self.st.session_state["memo_remote_snapshot"] = {"sha": "read-version"}
        self.functions["read_memo_remote_snapshot"] = Mock(return_value={"sha": "read-version", "records": [memo()]})
        self.sync.sync_file_to_github.return_value = {"ok": True, "sha": "new-version"}
        with patch.object(web_memo_db, "get_memos", return_value=[memo()]):
            self.functions["sync_web_memo_backup_to_github"]()
        self.assertEqual("read-version", self.sync.sync_file_to_github.call_args.kwargs["expected_sha"])

    def test_remote_race_and_read_failure_never_upload(self):
        self.st.session_state["memo_remote_snapshot"] = {"sha": "read-version"}
        for reading in (Mock(return_value={"sha": "changed", "records": [memo()]}), Mock(side_effect=RuntimeError("offline"))):
            with self.subTest(reading=reading):
                self.functions["read_memo_remote_snapshot"] = reading
                with self.assertRaises(PageStopped):
                    self.functions["sync_web_memo_backup_to_github"]()
                self.sync.sync_file_to_github.assert_not_called()

    def test_stale_displayed_form_is_stopped_before_local_write(self):
        self.functions["memo_displayed_snapshot"] = {"sha": "old"}
        self.st.session_state["memo_remote_snapshot"] = {"sha": "new"}
        self.functions["read_memo_remote_snapshot"] = Mock(return_value={"sha": "new"})
        with self.assertRaises(PageStopped):
            self.functions["require_memo_remote_unchanged"]()

    def test_corrupt_backup_count_stops_read(self):
        self.sync.read_file_from_github.return_value = {"ok": True, "sha": "v", "content": "# 灵感便签盒备份\n- 记录数量：1\n"}
        with self.assertRaises((RuntimeError, ValueError)):
            self.functions["read_memo_remote_snapshot"]()


class BudgetSyncTest(unittest.TestCase):
    def setUp(self):
        self.st = fake_streamlit()
        self.sync = Mock()
        self.functions = page_functions("05_8_budget.py", st=self.st, github_backup_sync=self.sync,
                                        budget_db=budget_db, get_all_records=Mock(return_value=[expense()]),
                                        budget_remote_snapshot={"sha": "read-version"}, budget_displayed_snapshot=None)

    def test_remote_changes_refresh_unchanged_local_ledger(self):
        self.sync.get_local_sync_baseline.return_value = {"content": budget_db.build_markdown_backup([expense()])}
        snapshot = {"sha": "new", "records": [expense(amount=20)], "content": budget_db.build_markdown_backup([expense(amount=20)])}
        with patch.object(budget_db, "restore_synced_records") as restore:
            self.functions["align_budget_with_remote"](snapshot)
        restore.assert_called_once_with(snapshot["records"])
        self.sync.remember_local_sync_baseline.assert_called_once()

    def test_remote_changes_never_overwrite_unsynced_local_amount(self):
        self.functions["get_all_records"].return_value = [expense(amount=30)]
        self.sync.get_local_sync_baseline.return_value = {"content": budget_db.build_markdown_backup([expense()])}
        snapshot = {"sha": "new", "records": [expense(amount=20)], "content": ""}
        with patch.object(budget_db, "restore_synced_records") as restore, self.assertRaises(RuntimeError):
            self.functions["align_budget_with_remote"](snapshot)
        restore.assert_not_called()
        self.sync.remember_local_sync_baseline.assert_not_called()

    def test_failed_previous_upload_keeps_local_edit_when_remote_unchanged(self):
        self.functions["get_all_records"].return_value = [expense(amount=30)]
        self.sync.get_local_sync_baseline.return_value = {"content": budget_db.build_markdown_backup([expense()])}
        snapshot = {"sha": "same", "records": [expense()], "content": ""}
        with patch.object(budget_db, "restore_synced_records") as restore:
            self.functions["align_budget_with_remote"](snapshot)
        restore.assert_not_called()
        self.sync.remember_local_sync_baseline.assert_not_called()

    def test_newly_downloaded_backup_does_not_authorize_stale_existing_database(self):
        self.functions["get_all_records"].return_value = [expense(amount=30)]
        self.sync.get_local_sync_baseline.return_value = {"content": budget_db.build_markdown_backup([expense()])}
        snapshot = {"sha": "new", "records": [expense()], "content": ""}
        with patch.object(budget_db, "restore_synced_records") as restore, self.assertRaises(RuntimeError):
            self.functions["align_budget_with_remote"](snapshot, None)
        restore.assert_not_called()

    def test_sync_version_guard_and_stale_form(self):
        self.functions["read_budget_remote_snapshot"] = Mock(return_value={"sha": "read-version"})
        self.sync.sync_file_to_github.return_value = {"ok": True}
        self.functions["sync_budget_backup_to_github"]()
        self.assertEqual("read-version", self.sync.sync_file_to_github.call_args.kwargs["expected_sha"])
        self.functions["budget_displayed_snapshot"] = {"sha": "stale"}
        with self.assertRaises(PageStopped):
            self.functions["require_budget_remote_unchanged"]()

    def test_budget_restore_preserves_ids_and_rolls_back_invalid_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(budget_db, "DB_PATH", str(Path(tmpdir) / "budget.db")), patch.object(budget_db, "BACKUP_MD_PATH", str(Path(tmpdir) / "budget.md")), patch.object(budget_db, "BACKUP_XLSX_PATH", str(Path(tmpdir) / "budget.xlsx")):
            budget_db.init_db()
            budget_db.restore_synced_records([expense(7), expense(23, 30)])
            self.assertEqual({7, 23}, {record["id"] for record in budget_db.get_all_records()})
            with self.assertRaises(ValueError):
                budget_db.restore_synced_records([expense(0, 80)])
            self.assertEqual({7, 23}, {record["id"] for record in budget_db.get_all_records()})
            budget_db.add_record("2026-10-02", "学生实践费", "", "", "新增", 1)
            self.assertGreater(budget_db.get_all_records()[0]["id"], 23)

    def test_batch_edit_rolls_back_on_invalid_later_amount_or_missing_record(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(budget_db, "DB_PATH", str(Path(tmpdir) / "budget.db")), patch.object(budget_db, "BACKUP_MD_PATH", str(Path(tmpdir) / "budget.md")), patch.object(budget_db, "BACKUP_XLSX_PATH", str(Path(tmpdir) / "budget.xlsx")):
            budget_db.init_db()
            budget_db.restore_synced_records([expense(7), expense(23, 30)])
            for last_update in ({"id": 23, "amount": float("inf")}, {"id": 99, "amount": 1}):
                with self.subTest(last_update=last_update), self.assertRaises(ValueError):
                    budget_db.update_records([{"id": 7, "amount": 100}, last_update])
                self.assertEqual(12.5, next(record for record in budget_db.get_all_records() if record["id"] == 7)["amount"])
            budget_db.update_records([{"id": 7, "amount": 20}, {"id": 23, "reimbursement_status": "已报销"}])
            self.assertEqual(20, next(record for record in budget_db.get_all_records() if record["id"] == 7)["amount"])


if __name__ == "__main__":
    unittest.main()
