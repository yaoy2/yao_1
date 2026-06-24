import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import llm_budget_accounts


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "00_13_llm_budget.py"


class LLMBudgetAccountsTest(unittest.TestCase):
    def test_save_provider_profile_persists_trimmed_account_and_expiration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            accounts_path = Path(tmpdir) / "llm_budget_accounts.json"

            with patch.object(llm_budget_accounts, "ACCOUNTS_PATH", accounts_path):
                llm_budget_accounts.save_provider_profile(
                    "deepseek",
                    account="  sir@example.com  ",
                    expiration_date="  26_09_30  ",
                )

                self.assertEqual(
                    "sir@example.com",
                    llm_budget_accounts.get_login_account("deepseek"),
                )
                self.assertEqual(
                    "26_09_30",
                    llm_budget_accounts.get_expiration_date("deepseek"),
                )

    def test_save_provider_profile_keeps_multiple_accounts_for_one_provider(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            accounts_path = Path(tmpdir) / "llm_budget_accounts.json"

            with patch.object(llm_budget_accounts, "ACCOUNTS_PATH", accounts_path):
                llm_budget_accounts.save_provider_profile("gemini", "a@gmail.com", "26_09_30")
                llm_budget_accounts.save_provider_profile("gemini", "b@gmail.com", "26_12_31")

                self.assertEqual(["a@gmail.com", "b@gmail.com"], llm_budget_accounts.list_login_accounts("gemini"))
                self.assertEqual("b@gmail.com", llm_budget_accounts.get_login_account("gemini"))
                self.assertEqual("26_12_31", llm_budget_accounts.get_expiration_date("gemini"))
                self.assertEqual("26_09_30", llm_budget_accounts.get_expiration_date("gemini", "a@gmail.com"))

    def test_set_active_login_account_switches_expiration_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            accounts_path = Path(tmpdir) / "llm_budget_accounts.json"

            with patch.object(llm_budget_accounts, "ACCOUNTS_PATH", accounts_path):
                llm_budget_accounts.save_provider_profile("gemini", "a@gmail.com", "26_09_30")
                llm_budget_accounts.save_provider_profile("gemini", "b@gmail.com", "26_12_31")
                llm_budget_accounts.set_active_login_account("gemini", "a@gmail.com")

                self.assertEqual("a@gmail.com", llm_budget_accounts.get_login_account("gemini"))
                self.assertEqual("26_09_30", llm_budget_accounts.get_expiration_date("gemini"))

    def test_blank_profile_removes_saved_provider(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            accounts_path = Path(tmpdir) / "llm_budget_accounts.json"

            with patch.object(llm_budget_accounts, "ACCOUNTS_PATH", accounts_path):
                llm_budget_accounts.save_provider_profile("kimi", "sir@example.com", "26_09_30")
                llm_budget_accounts.save_provider_profile("kimi", "   ", "   ")

                self.assertEqual("", llm_budget_accounts.get_login_account("kimi"))
                self.assertEqual("", llm_budget_accounts.get_expiration_date("kimi"))

    def test_legacy_string_account_file_still_reads_account(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            accounts_path = Path(tmpdir) / "llm_budget_accounts.json"
            accounts_path.write_text('{"deepseek": "7770"}', encoding="utf-8")

            with patch.object(llm_budget_accounts, "ACCOUNTS_PATH", accounts_path):
                self.assertEqual("7770", llm_budget_accounts.get_login_account("deepseek"))
                self.assertEqual("", llm_budget_accounts.get_expiration_date("deepseek"))

    def test_page_renders_editable_login_account_for_each_provider(self):
        page_source = PAGE_PATH.read_text(encoding="utf-8")

        self.assertIn("登录账号", page_source)
        self.assertIn("llm_budget_accounts.get_login_account(key)", page_source)
        self.assertIn("llm_budget_accounts.list_login_accounts(key)", page_source)
        self.assertIn("expiration date: yy_mm_dd", page_source)
        self.assertIn("llm_budget_accounts.get_expiration_date(key, account_value)", page_source)
        self.assertIn("st.selectbox(", page_source)
        self.assertIn("accept_new_options=True", page_source)
        self.assertIn("llm_budget_accounts.save_provider_profile(", page_source)
        self.assertIn("account_col, save_col = st.columns([3, 1]", page_source)
        self.assertIn('key=f"account_{key}"', page_source)
        self.assertIn('key=f"expiration_{key}_{account_value}"', page_source)
        self.assertIn('st.button("保存"', page_source)
        self.assertNotIn('st.button("保存账号"', page_source)
        self.assertIn('key=f"save_account_{key}"', page_source)
        self.assertIn("sync_llm_budget_accounts_to_github()", page_source)

    def test_gemini_provider_is_available(self):
        from utils.llm_budget_providers import MANUAL_PROVIDERS

        self.assertIn("gemini", MANUAL_PROVIDERS)
        self.assertEqual("Gemini", MANUAL_PROVIDERS["gemini"]["name"])


if __name__ == "__main__":
    unittest.main()
