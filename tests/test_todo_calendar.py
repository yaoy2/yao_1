import copy
import tempfile
import unittest
from datetime import date

from bs4 import BeautifulSoup

from tests.test_todo_db import patched_todo_storage
from utils import todo_db
from utils.todo_calendar import calendar_title, render_calendar_html, shift_month


def record(content, due_date="2026-09-30", **fields):
    return {"content": content, "due_date": due_date, "status": "pending", "is_archived": False, **fields}


def calendar_document(records, month=date(2026, 9, 1)):
    return BeautifulSoup(render_calendar_html(records, month, today=date(2026, 9, 29)), "html.parser")


class TodoCalendarTest(unittest.TestCase):
    def test_calendar_keeps_completed_tasks_and_hides_deleted_or_split_parents(self):
        records = [
            record("未完成材料"),
            record("已完成材料", status="done", is_archived=True),
            record("已删除材料", status="deleted", is_archived=True),
            record("拆分前的原始记录", is_archived=True),
        ]
        original = copy.deepcopy(records)
        document = calendar_document(records)
        tasks = document.select(".todo-calendar-day .todo-calendar-task")

        self.assertEqual(2, len(tasks))
        self.assertEqual("未完成材料", tasks[0].summary.get_text())
        self.assertIsNone(tasks[0].summary.find("s"))
        self.assertEqual("已完成材料", tasks[1].summary.find("s").get_text())
        self.assertIn("已完成", tasks[1].select_one(".todo-calendar-meta").get_text())
        self.assertEqual(original, records)

    def test_multiple_tasks_use_full_deadline_and_sort_by_completion_then_time(self):
        records = [
            record("已完成", due_time="08:00", status="done", is_archived=True),
            record("下午交材料", due_time="17:00", record_date="2026-09-29"),
            record("上午交材料", due_time="09:30"),
            record("下月材料", due_date="2026-10-01"),
            record("去年的同一天", due_date="2025-09-30"),
        ]
        document = calendar_document(records)
        day = document.select_one('[data-date="2026-09-30"]')

        self.assertEqual(["上午交材料", "下午交材料", "已完成"], [item.get_text() for item in day.select("summary")])
        self.assertEqual([], document.select('[data-date="2026-09-29"] .todo-calendar-task'))
        self.assertNotIn("下月材料", document.get_text())
        self.assertNotIn("去年的同一天", document.get_text())
        self.assertEqual("2026-09-29", document.select_one(".todo-calendar-day.today")["data-date"])

    def test_month_grid_handles_leap_day_and_navigation_across_years(self):
        document = calendar_document([record("闰日材料", due_date="2024-02-29")], month=date(2024, 2, 1))

        self.assertEqual(29, len(document.select(".todo-calendar-day[data-date]")))
        self.assertEqual("闰日材料", document.select_one('[data-date="2024-02-29"] summary').get_text())
        self.assertEqual(35, len(document.select(".todo-calendar-day")))
        self.assertEqual(6, len(document.select(".todo-calendar-day.empty")))
        self.assertEqual("2024-02-01", document.select(".todo-calendar-day")[3]["data-date"])
        self.assertEqual(date(2027, 1, 1), shift_month(date(2026, 12, 1), 1))
        self.assertEqual(date(2025, 12, 1), shift_month(date(2026, 1, 1), -1))

    def test_missing_or_invalid_dates_stay_accessible_without_being_assigned_a_day(self):
        records = [record("日期未定", ""), record("需确认旧日期", "2026-02-30"), record("没有日期", None)]
        document = calendar_document(records)

        self.assertEqual([], document.select(".todo-calendar-day .todo-calendar-task"))
        undated = document.select_one(".todo-calendar-undated")
        self.assertNotIn("open", undated.attrs)
        self.assertIn("（3）", undated.summary.get_text())
        self.assertEqual(3, len(undated.select(".todo-calendar-task")))
        self.assertIn("2026-02-30", undated.get_text())

    def test_clickable_details_preserve_full_text_and_escape_all_fields(self):
        content = '9月30日前提交很长的材料名称和附件清单\n<script>alert("任务")</script> & "附件"'
        document = calendar_document([record(content, due_time='09:30 <img src=x onerror="alert(1)">',
                                               status="done", is_archived=True, completed_at="2026-09-28 10:00")])
        task = document.select_one(".todo-calendar-task")

        self.assertNotIn("open", task.attrs)
        self.assertEqual(content, task.summary["title"])
        self.assertEqual(content, task.select_one(".todo-calendar-content").get_text())
        self.assertIn("2026-09-28 10:00", task.select_one(".todo-calendar-meta").get_text())
        self.assertEqual([], document.select("script, img, input, button, a"))
        self.assertLess(len(task.summary.get_text()), len(content))
        self.assertTrue(task.summary.get_text().endswith("…"))
        self.assertEqual("提交10月工作安排", calendar_title("10月7日前提交10月工作安排"))

    def test_existing_completion_reopen_and_deadline_edits_flow_into_calendar(self):
        with tempfile.TemporaryDirectory() as directory, patched_todo_storage(directory) as storage:
            todo_db.init_db()
            record_id = todo_db.add_todo("测试材料", due_date="2026-09-30")
            todo_db.complete_todo(record_id)
            backup_before_render = (storage / "todo_items_backup.md").read_bytes()

            document = calendar_document(todo_db.get_todos(view="all"))
            self.assertEqual("测试材料", document.select_one('[data-date="2026-09-30"] s').get_text())
            self.assertEqual(backup_before_render, (storage / "todo_items_backup.md").read_bytes())

            todo_db.reopen_todo(record_id)
            todo_db.update_todo(record_id, due_date="2026-10-07", due_time="17:00")
            september = calendar_document(todo_db.get_todos(view="all"))
            october = calendar_document(todo_db.get_todos(view="all"), month=date(2026, 10, 1))
            task = october.select_one('[data-date="2026-10-07"] .todo-calendar-task')
            self.assertEqual([], september.select(".todo-calendar-task"))
            self.assertIsNone(task.find("s"))
            self.assertIn("17:00", task.get_text())


if __name__ == "__main__":
    unittest.main()
