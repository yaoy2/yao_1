"""Check uploaded workbooks through the page's parser without opening real data."""

import ast
import io
import math
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from config.budget_config import BUDGET_CATEGORIES, REIMBURSEMENT_STATUSES


@pytest.fixture
def parse_workbook():
    page = Path(__file__).resolve().parents[1] / "pages" / "05_8_budget.py"
    names = {"_clean_excel_date", "_clean_excel_text", "_records_from_excel"}
    nodes = []
    for node in ast.parse(page.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "COL_RENAME" for target in node.targets):
            nodes.append(node)
    namespace = {"pd": pd, "math": math, "date": date, "datetime": datetime,
                 "BUDGET_CATEGORIES": BUDGET_CATEGORIES, "REIMBURSEMENT_STATUSES": REIMBURSEMENT_STATUSES}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(page), "exec"), namespace)
    return namespace["_records_from_excel"]


def workbook(*dates, amount=12.5):
    rows = [{"日期": value, "类别": next(iter(BUDGET_CATEGORIES)), "金额": amount,
             "报销状态": "未报销", "支出明细": "测试材料"} for value in dates]
    output = io.BytesIO()
    pd.DataFrame(rows).to_excel(output, index=False, engine="openpyxl")
    output.seek(0)
    return output


@pytest.mark.parametrize("invalid_date", ["2026-02-30", "不是日期", 46297, True, ""])
def test_invalid_later_date_rejects_the_workbook_with_row_number(parse_workbook, invalid_date):
    with pytest.raises(ValueError, match="第 3 行日期缺失或无效"):
        parse_workbook(workbook("2026-10-02", invalid_date))


@pytest.mark.parametrize("value", ["2024-02-29", "2024/02/29", date(2024, 2, 29), datetime(2024, 2, 29, 14, 30)])
def test_valid_excel_dates_and_exported_strings_are_preserved(parse_workbook, value):
    records = parse_workbook(workbook(value))
    assert records[0]["record_date"] == "2024-02-29"
    assert records[0]["amount"] == 12.5


@pytest.mark.parametrize("amount", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_amount_rejected_before_restore(parse_workbook, amount):
    with pytest.raises(ValueError, match="第 2 行金额无效"):
        parse_workbook(workbook("2026-10-02", amount=amount))
