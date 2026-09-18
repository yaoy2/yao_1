import ast
import importlib
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from utils import todo_db
from tests.test_todo_db import patched_todo_storage


class TodoPageCompatTest(unittest.TestCase):
    def run_page_bootstrap(self):
        page = Path(__file__).resolve().parents[1] / "pages/14_todos.py"
        tree = ast.parse(page.read_text(encoding="utf-8"))
        # Execute the page's startup logic, stopping before any Streamlit UI or DB writes.
        statements = []
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value.func
                if isinstance(call, ast.Attribute) and call.attr == "set_page_config":
                    break
            if isinstance(node, (ast.If, ast.Assign)):
                statements.append(node)
        namespace = {"importlib": importlib, "todo_db": todo_db}
        exec(compile(ast.Module(body=statements, type_ignores=[]), str(page), "exec"), namespace)
        return namespace["todo_db"]

    def test_cached_pre_chat_module_recovers_before_page_uses_today(self):
        # Simulate a module cached before today()/record_uid() were introduced.
        with patch.dict(todo_db.__dict__):
            del todo_db.today
            del todo_db.record_uid
            with self.assertRaises(AttributeError):
                todo_db.today()
            module = self.run_page_bootstrap()
            self.assertIsInstance(module.today(), date)
            self.assertTrue(callable(module.record_uid))
            with tempfile.TemporaryDirectory() as directory, patched_todo_storage(directory):
                module.init_db()
                module.add_todo("明天下午3点提交材料", record_date=module.today().isoformat())
                item = module.get_todos()[0]
                self.assertTrue(item["uid"])
                self.assertEqual("15:00", item["due_time"])

    def test_current_module_is_not_reloaded_on_every_rerun(self):
        with patch.object(importlib, "reload", side_effect=AssertionError("unexpected reload")):
            self.assertIs(todo_db, self.run_page_bootstrap())


if __name__ == "__main__":
    unittest.main()
