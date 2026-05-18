import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import budget_db


class BudgetDbReplaceAllRecordsTest(unittest.TestCase):
    def test_replace_all_records_overwrites_existing_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "budget.db")
            with patch.object(budget_db, "DB_PATH", db_path):
                budget_db.init_db()
                budget_db.add_record("2026-05-01", "学生实践费", "护理系", "旧记录", 100)

                budget_db.replace_all_records([
                    {
                        "record_date": "2026-05-18",
                        "category": "学生竞赛费",
                        "unit": "康复系",
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
        self.assertEqual("新记录", records[0]["description"])
        self.assertEqual(2800, records[0]["amount"])
        self.assertEqual("已报销", records[0]["reimbursement_status"])

    def test_replace_all_records_rolls_back_if_any_record_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "budget.db")
            with patch.object(budget_db, "DB_PATH", db_path):
                budget_db.init_db()
                budget_db.add_record("2026-05-01", "学生实践费", "护理系", "保留记录", 100)

                with self.assertRaises((KeyError, TypeError, ValueError)):
                    budget_db.replace_all_records([
                        {
                            "record_date": "2026-05-18",
                            "category": "学生竞赛费",
                            "unit": "康复系",
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
        self.assertEqual("保留记录", records[0]["description"])
        self.assertEqual(100, records[0]["amount"])


if __name__ == "__main__":
    unittest.main()
