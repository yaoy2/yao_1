import unittest

from utils import budget_auth


class BudgetAuthTest(unittest.TestCase):
    def test_get_budget_password_prefers_streamlit_secrets(self):
        password = budget_auth.get_budget_password(
            secrets={"budget_password": "from-secrets"},
            environ={"BUDGET_PASSWORD": "from-env"},
        )

        self.assertEqual("from-secrets", password)

    def test_get_budget_password_reads_budget_section(self):
        password = budget_auth.get_budget_password(
            secrets={"budget": {"password": "section-password"}},
            environ={},
        )

        self.assertEqual("section-password", password)

    def test_get_budget_password_falls_back_to_environment(self):
        password = budget_auth.get_budget_password(
            secrets={},
            environ={"BUDGET_PASSWORD": "from-env"},
        )

        self.assertEqual("from-env", password)

    def test_get_budget_password_ignores_blank_values(self):
        password = budget_auth.get_budget_password(
            secrets={"budget_password": "   "},
            environ={"BUDGET_PASSWORD": ""},
        )

        self.assertIsNone(password)

    def test_is_budget_password_valid_compares_exact_password(self):
        self.assertTrue(budget_auth.is_budget_password_valid("secret", "secret"))
        self.assertFalse(budget_auth.is_budget_password_valid("Secret", "secret"))
        self.assertFalse(budget_auth.is_budget_password_valid("", "secret"))


if __name__ == "__main__":
    unittest.main()
