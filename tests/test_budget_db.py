import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from utils import budget_db


@contextmanager
def patched_budget_storage(tmpdir):
    tmp_path = Path(tmpdir)
    with (
        patch.object(budget_db, "DB_PATH", str(tmp_path / "budget.db")),
        patch.object(budget_db, "BACKUP_MD_PATH", str(tmp_path / "budget_ledger_backup.md")),
        patch.object(budget_db, "BACKUP_XLSX_PATH", str(tmp_path / "budget_ledger_backup.xlsx")),
    ):
        yield tmp_path


class BudgetDbReplaceAllRecordsTest(unittest.TestCase):
    def test_add_record_writes_markdown_and_excel_backups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_budget_storage(tmpdir) as tmp_path:
                md_path = tmp_path / "budget_ledger_backup.md"
                xlsx_path = tmp_path / "budget_ledger_backup.xlsx"
                budget_db.init_db()
                budget_db.add_record("2026-05-01", "学生实践费", "护理系", "张三", "耗材", 100)

                self.assertTrue(md_path.exists())
                self.assertTrue(xlsx_path.exists())
                backup_text = md_path.read_text(encoding="utf-8")
                workbook = load_workbook(xlsx_path)
                sheet = workbook["预算流水"]
                excel_headers = [cell.value for cell in sheet[1]]
                excel_values = [cell.value for cell in sheet[2]]

        self.assertIn("预算速记台账备份", backup_text)
        self.assertIn("2026-05-01", backup_text)
        self.assertIn("学生实践费", backup_text)
        self.assertIn("护理系", backup_text)
        self.assertIn("张三", backup_text)
        self.assertIn("耗材", backup_text)
        self.assertIn("100.00", backup_text)
        self.assertIn("未报销", backup_text)
        self.assertIn("支出人", excel_headers)
        self.assertIn("张三", excel_values)
        self.assertIn("耗材", excel_values)

    def test_add_record_saves_spender(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_budget_storage(tmpdir):
                budget_db.init_db()
                budget_db.add_record("2026-05-01", "学生实践费", "护理系", "张三", "耗材", 100)

                records = budget_db.get_all_records()

        self.assertEqual("张三", records[0]["spender"])
        self.assertEqual("耗材", records[0]["description"])

    def test_init_db_adds_spender_column_to_existing_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_budget_storage(tmpdir):
                conn = budget_db.get_connection()
                conn.execute("""
                    CREATE TABLE expense_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        record_date TEXT NOT NULL,
                        category TEXT NOT NULL,
                        unit TEXT NOT NULL DEFAULT '',
                        description TEXT NOT NULL DEFAULT '',
                        amount REAL NOT NULL,
                        reimbursement_status TEXT NOT NULL DEFAULT '未报销',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.commit()
                conn.close()

                budget_db.init_db()
                budget_db.add_record("2026-05-01", "学生实践费", "护理系", "张三", "耗材", 100)

                records = budget_db.get_all_records()

        self.assertEqual("张三", records[0]["spender"])

    def test_replace_all_records_overwrites_existing_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_budget_storage(tmpdir):
                budget_db.init_db()
                budget_db.add_record("2026-05-01", "学生实践费", "护理系", "李四", "旧记录", 100)

                budget_db.replace_all_records([
                    {
                        "record_date": "2026-05-18",
                        "category": "学生竞赛费",
                        "unit": "康复系",
                        "spender": "王五",
                        "description": "新记录",
                        "amount": 2800,
                        "reimbursement_status": "已报销",
                        "created_at": "2026-05-18 08:00:00",
                        "updated_at": "2026-05-18 08:00:00",
                    }
                ])

                records = budget_db.get_all_records()

        self.assertEqual(1, len(records))
        self.assertEqual("学生竞赛费", records[0]["category"])
        self.assertEqual("康复系", records[0]["unit"])
        self.assertEqual("王五", records[0]["spender"])
        self.assertEqual("新记录", records[0]["description"])
        self.assertEqual(2800, records[0]["amount"])
        self.assertEqual("已报销", records[0]["reimbursement_status"])

    def test_replace_all_records_rolls_back_if_any_record_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_budget_storage(tmpdir):
                budget_db.init_db()
                budget_db.add_record("2026-05-01", "学生实践费", "护理系", "赵六", "保留记录", 100)

                with self.assertRaises((KeyError, TypeError, ValueError)):
                    budget_db.replace_all_records([
                        {
                            "record_date": "2026-05-18",
                            "category": "学生竞赛费",
                            "unit": "康复系",
                            "spender": "王五",
                            "description": "有效记录",
                            "amount": 2800,
                            "reimbursement_status": "已报销",
                        },
                        {
                            "record_date": "2026-05-19",
                            "category": "学生实践费",
                            "unit": "护理系",
                            "description": "缺少金额",
                            "reimbursement_status": "未报销",
                        },
                    ])

                records = budget_db.get_all_records()

        self.assertEqual(1, len(records))
        self.assertEqual("赵六", records[0]["spender"])
        self.assertEqual("保留记录", records[0]["description"])
        self.assertEqual(100, records[0]["amount"])


if __name__ == "__main__":
    unittest.main()
