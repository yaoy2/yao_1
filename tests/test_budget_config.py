import unittest

from config.budget_config import BUDGET_CATEGORIES, TOTAL_BUDGET, UNCAPPED_BUDGET_CATEGORIES


class BudgetConfigTest(unittest.TestCase):
    def test_year_end_bonus_retention_category_exists_without_changing_total_budget(self):
        self.assertIn("年终奖留存", BUDGET_CATEGORIES)
        self.assertEqual(0, BUDGET_CATEGORIES["年终奖留存"])
        self.assertIn("年终奖留存", UNCAPPED_BUDGET_CATEGORIES)
        self.assertEqual(TOTAL_BUDGET, sum(BUDGET_CATEGORIES.values()))


if __name__ == "__main__":
    unittest.main()
