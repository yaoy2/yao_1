import tempfile
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch

from utils import todo_db


@contextmanager
def patched_todo_storage(tmpdir):
    tmp_path = Path(tmpdir)
    with (
        patch.object(todo_db, "DB_PATH", str(tmp_path / "todos.db")),
        patch.object(todo_db, "BACKUP_MD_PATH", str(tmp_path / "todo_items_backup.md")),
    ):
        yield tmp_path


class TodoDbTest(unittest.TestCase):
    def test_add_todo_uses_today_and_writes_markdown_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_todo_storage(tmpdir) as tmp_path:
                todo_db.init_db()
                todo_db.add_todo("下周一下午3点交学院材料")

                records = todo_db.get_todos()
                backup_text = (tmp_path / "todo_items_backup.md").read_text(encoding="utf-8")

        self.assertEqual(1, len(records))
        self.assertEqual(date.today().isoformat(), records[0]["record_date"])
        self.assertIn("下周一下午3点交学院材料", backup_text)
        self.assertIn("# 待办清单备份", backup_text)

    def test_extract_due_fields_from_common_chinese_text(self):
        base_date = date(2026, 6, 29)

        self.assertEqual(("2026-07-01", "14:30"), todo_db.extract_due_fields("2026-07-01 14:30 交表", base_date))
        self.assertEqual(("2026-07-01", "15:00"), todo_db.extract_due_fields("7月1日下午3点交材料", base_date))
        self.assertEqual(("2026-06-30", "10:30"), todo_db.extract_due_fields("明天上午10点半提醒", base_date))
        self.assertEqual(("2026-07-01", ""), todo_db.extract_due_fields("后天联系学生", base_date))
        self.assertEqual(("2026-07-06", ""), todo_db.extract_due_fields("下周一开协调会", base_date))

    def test_search_matches_content_record_date_due_date_and_due_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_todo_storage(tmpdir):
                todo_db.init_db()
                todo_db.add_todo("提交竞赛报名表", record_date="2026-06-29", due_date="2026-07-01", due_time="15:00")

                self.assertEqual(1, len(todo_db.get_todos(keyword="竞赛")))
                self.assertEqual(1, len(todo_db.get_todos(keyword="2026-06-29")))
                self.assertEqual(1, len(todo_db.get_todos(keyword="2026-07-01")))
                self.assertEqual(1, len(todo_db.get_todos(keyword="15:00")))
                self.assertEqual([], todo_db.get_todos(keyword="不存在"))

    def test_complete_todo_archives_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_todo_storage(tmpdir):
                todo_db.init_db()
                todo_db.add_todo("完成后归档")
                record_id = todo_db.get_todos()[0]["id"]

                changed = todo_db.complete_todo(record_id)
                active_records = todo_db.get_todos()
                archived_records = todo_db.get_todos(view="archived")
                all_records = todo_db.get_todos(view="all")

        self.assertEqual(1, changed)
        self.assertEqual([], active_records)
        self.assertEqual(1, len(archived_records))
        self.assertEqual(1, len(all_records))
        self.assertEqual("done", archived_records[0]["status"])
        self.assertTrue(archived_records[0]["is_archived"])
        self.assertTrue(archived_records[0]["completed_at"])

    def test_init_db_restores_records_from_markdown_backup_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_todo_storage(tmpdir) as tmp_path:
                (tmp_path / "todo_items_backup.md").write_text(
                    "\n".join(
                        [
                            "# 待办清单备份",
                            "",
                            "## TODO-7",
                            "",
                            "- 发布日期：2026-06-29",
                            "- 截止日期：2026-07-01",
                            "- 截止时间：15:00",
                            "- 状态：pending",
                            "- 归档：否",
                            "- 完成时间：",
                            "- 创建时间：2026-06-29 09:00:00",
                            "- 更新时间：2026-06-29 09:00:00",
                            "",
                            "### 内容",
                            "",
                            "从备份恢复的待办",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                todo_db.init_db()
                records = todo_db.get_todos()

        self.assertEqual(1, len(records))
        self.assertEqual("从备份恢复的待办", records[0]["content"])
        self.assertEqual("2026-07-01", records[0]["due_date"])
        self.assertEqual("15:00", records[0]["due_time"])

    def test_import_todo_records_merges_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_todo_storage(tmpdir):
                todo_db.init_db()
                todo_db.add_todo("本地待办", record_date="2026-06-29")

                inserted = todo_db.import_todo_records(
                    [
                        {"record_date": "2026-06-29", "content": "本地待办", "status": "pending"},
                        {"record_date": "2026-06-30", "content": "远端待办", "status": "pending"},
                    ]
                )
                records = todo_db.get_todos(view="all")

        self.assertEqual(1, inserted)
        self.assertEqual(2, len(records))
        self.assertIn("远端待办", [record["content"] for record in records])

    def test_page_uses_auth_search_dates_completion_archive_and_github_sync(self):
        page_path = Path(__file__).resolve().parents[1] / "pages" / "14_todos.py"
        page_source = page_path.read_text(encoding="utf-8")

        self.assertIn("budget_auth", page_source)
        self.assertIn("todo_text", page_source)
        self.assertIn("date_input", page_source)
        self.assertIn("time_input", page_source)
        self.assertIn("keyword", page_source)
        self.assertIn("complete_todo", page_source)
        self.assertIn("归档", page_source)
        self.assertIn("restore_todo_backup_from_github()", page_source)
        self.assertIn("merge_remote_todos_from_github()", page_source)
        self.assertIn("sync_todo_backup_to_github()", page_source)


if __name__ == "__main__":
    unittest.main()
