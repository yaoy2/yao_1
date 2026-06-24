import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import llm_budget_accounts


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "00_13_llm_budget.py"


class LLMBudgetAccountsTest(unittest.TestCase):
    def test_save_login_account_persists_trimmed_account(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            accounts_path = Path(tmpdir) / "llm_budget_accounts.json"

            with patch.object(llm_budget_accounts, "ACCOUNTS_PATH", accounts_path):
                llm_budget_accounts.save_login_account("deepseek", "  sir@example.com  ")

                self.assertEqual(
                    "sir@example.com",
                    llm_budget_accounts.get_login_account("deepseek"),
                )

    def test_blank_login_account_removes_saved_account(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            accounts_path = Path(tmpdir) / "llm_budget_accounts.json"

            with patch.object(llm_budget_accounts, "ACCOUNTS_PATH", accounts_path):
                llm_budget_accounts.save_login_account("kimi", "sir@example.com")
                llm_budget_accounts.save_login_account("kimi", "   ")

                self.assertEqual("", llm_budget_accounts.get_login_account("kimi"))

    def test_page_renders_editable_login_account_for_each_provider(self):
        page_source = PAGE_PATH.read_text(encoding="utf-8")

        self.assertIn("登录账号", page_source)
        self.assertIn("llm_budget_accounts.get_login_account(key)", page_source)
        self.assertIn("llm_budget_accounts.save_login_account(key", page_source)
        self.assertIn('key=f"account_{key}"', page_source)
        self.assertIn('key=f"save_account_{key}"', page_source)
        self.assertIn("sync_llm_budget_accounts_to_github()", page_source)


if __name__ == "__main__":
    unittest.main()
