"""Business boundaries exercised with synthetic, real XLSX workbooks."""

import hashlib
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from integrations.file_distribution.models import Decision
from integrations.file_distribution.monthly import classify_monthly
from integrations.file_distribution.readers import read_workbook


def _month_label(months, year=None):
    return f"{year}年{months}月" if year else f"{months}月"


def _academy_sheet(sheet, summary="10", plan="11", year=2026, *, populated=True, group="副院长"):
    sheet["A1"] = f"健康学院{_month_label(summary, year)}工作总结及{plan}月工作计划"
    sheet["A2"] = group
    sheet["B2"] = "人员"
    sheet["C2"] = "工作领域"
    sheet["D2"] = f"{_month_label(summary, year)}工作总结"
    sheet["E2"] = f"{plan}月工作计划"
    sheet["A3"] = "教学管理" if group == "副院长" else "医学影像系"
    sheet["B3"] = "提交人甲"
    sheet["C3"] = "课程建设"
    if populated:
        sheet["D3"] = "完成两次课程研讨，形成修订清单。"
        sheet["E3"] = "开展三次课程检查并形成反馈。"


def _academy_workbook(**kwargs):
    workbook = Workbook()
    workbook.active.title = "当期月报"
    _academy_sheet(workbook.active, **kwargs)
    return workbook


def _school_workbook(summary="10", plan="11", year=2026, *, populated=True, plan_year=None):
    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "月度重点工作总结"
    summary_sheet["A1"] = f"健康学院{_month_label(summary, year)}重点工作总结"
    summary_sheet["A3"] = "工作项目"
    summary_sheet["B3"] = "实际完成情况"
    plan_sheet = workbook.create_sheet("月度重点工作计划")
    plan_sheet["A1"] = f"健康学院{_month_label(plan, plan_year or year)}重点工作计划"
    plan_sheet["A3"] = "工作项目"
    plan_sheet["B3"] = "计划完成目标（量化）"
    if populated:
        summary_sheet["A4"] = "课程建设"
        summary_sheet["B4"] = "完成两项示范课程评审。"
        plan_sheet["A4"] = "教学检查"
        plan_sheet["B4"] = "组织三次检查，完成整改反馈。"
    return workbook


class MonthlyClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="file_distribution_monthly_tests_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "Ding2026"
        self.root.mkdir()

    def save(self, name, workbook):
        path = self.root / name
        workbook.save(path)
        workbook.close()
        return path

    def classify(self, name, workbook):
        return classify_monthly(self.save(name, workbook), self.root)

    def assert_route(self, decision, kind, period):
        self.assertIsInstance(decision, Decision)
        self.assertEqual(decision.status, "ready", decision.reason)
        self.assertEqual(decision.kind, kind)
        self.assertEqual(decision.period, period)
        self.assertEqual(decision.relative_dir, f"月报/{period}/{kind}")

    def test_school_report_uses_summary_month_not_plan_month(self):
        result = self.classify("健康学院10月重点工作总结及11月重点工作计划.xlsx", _school_workbook())
        self.assert_route(result, "校办月报", "10月")

    def test_school_summer_and_winter_combined_summary_periods(self):
        for summary, plan, expected in (("7-8", "9", "07-08月"), ("1-2", "3", "01-02月")):
            with self.subTest(summary=summary):
                result = self.classify(
                    f"健康学院{summary}月重点工作总结及{plan}月重点工作计划.xlsx",
                    _school_workbook(summary, plan),
                )
                self.assert_route(result, "校办月报", expected)

    def test_school_december_summary_and_next_year_plan_keep_december(self):
        result = self.classify(
            "健康学院2026年12月重点工作总结及2027年1月重点工作计划.xlsx",
            _school_workbook("12", "1", plan_year=2027),
        )
        self.assert_route(result, "校办月报", "12月")

    def test_school_blank_template_is_not_a_submission(self):
        result = self.classify("健康学院10月重点工作总结及11月重点工作计划.xlsx", _school_workbook(populated=False))
        self.assertEqual(result.status, "skip")
        self.assertEqual(result.relative_dir, "")

    def test_school_headers_on_row_four_or_five_are_not_submission_content(self):
        for header_row in (4, 5):
            with self.subTest(header_row=header_row):
                workbook = _school_workbook(populated=False)
                for sheet in workbook.worksheets:
                    project_header, content_header = sheet["A3"].value, sheet["B3"].value
                    sheet["A3"] = None
                    sheet["B3"] = None
                    sheet.cell(header_row, 1, project_header)
                    sheet.cell(header_row, 2, content_header)
                result = self.classify("健康学院10月重点工作总结及11月重点工作计划.xlsx", workbook)
                self.assertEqual(result.status, "skip", result.reason)
                self.assertEqual(result.relative_dir, "")

    def test_school_content_below_late_headers_is_recognized(self):
        for header_row in (4, 5):
            with self.subTest(header_row=header_row):
                workbook = _school_workbook(populated=False)
                for sheet in workbook.worksheets:
                    project_header, content_header = sheet["A3"].value, sheet["B3"].value
                    sheet["A3"] = None
                    sheet["B3"] = None
                    sheet.cell(header_row, 1, project_header)
                    sheet.cell(header_row, 2, content_header)
                    sheet.cell(header_row + 1, 1, "课程建设")
                    sheet.cell(header_row + 1, 2, "开展两项课程建设工作。")
                result = self.classify("健康学院10月重点工作总结及11月重点工作计划.xlsx", workbook)
                self.assert_route(result, "校办月报", "10月")

    def test_academy_current_name_and_legacy_yuanbao_name(self):
        for name in ("【健康学院】学院月报-副院长-10-11.xlsx", "【健康学院】学院院报-副院长-10-11.xlsx"):
            with self.subTest(name=name):
                self.assert_route(self.classify(name, _academy_workbook()), "学院月报", "10月")

    def test_academy_work_summary_and_plan_name(self):
        result = self.classify("健康学院2026年10月工作总结及11月工作计划.xlsx", _academy_workbook())
        self.assert_route(result, "学院月报", "10月")

    def test_academy_78_9_compact_filename(self):
        result = self.classify("【健康学院】学院月报-副院长-78-9.xlsx", _academy_workbook(summary="7-8", plan="9"))
        self.assert_route(result, "学院月报", "07-08月")

    def test_academy_january_february_summary_is_one_period(self):
        result = self.classify("健康学院学院月报-1-2月总结及3月计划.xlsx", _academy_workbook(summary="1-2", plan="3"))
        self.assert_route(result, "学院月报", "01-02月")

    def test_current_blank_sheet_is_not_rescued_by_populated_history(self):
        workbook = _academy_workbook(populated=False)
        _academy_sheet(workbook.create_sheet("9月历史"), summary="9", plan="10", populated=True)
        result = self.classify("健康学院学院月报-副院长-10-11.xlsx", workbook)
        self.assertEqual(result.status, "skip", result.reason)
        self.assertIn("当期", result.reason)
        self.assertEqual(result.relative_dir, "")

    def test_prefilled_people_without_summary_or_plan_are_still_blank(self):
        workbook = _academy_workbook(populated=False)
        workbook.active["A4"] = "学生工作"
        workbook.active["B4"] = "提交人乙"
        workbook.active["C4"] = "日常管理"
        result = self.classify("健康学院学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.status, "skip")

    def test_placeholder_cells_are_not_submitted_content(self):
        for placeholder in ("请填写", "待填", "-", "某"):
            with self.subTest(placeholder=placeholder):
                workbook = _academy_workbook(populated=False)
                workbook.active["D3"] = placeholder
                workbook.active["E3"] = placeholder
                result = self.classify("健康学院学院月报-10-11.xlsx", workbook)
                self.assertEqual(result.status, "skip", result.reason)

    def test_explicit_no_matters_is_valid_report_content(self):
        for response in ("无", "暂无"):
            with self.subTest(response=response):
                workbook = _academy_workbook(populated=False)
                workbook.active["D3"] = response
                workbook.active["E3"] = response
                result = self.classify("健康学院学院月报-10-11.xlsx", workbook)
                self.assert_route(result, "学院月报", "10月")

    def test_populated_current_sheet_ignores_different_history_period(self):
        workbook = _academy_workbook()
        _academy_sheet(workbook.create_sheet("9月历史"), summary="9", plan="10")
        self.assert_route(self.classify("健康学院学院月报-10-11.xlsx", workbook), "学院月报", "10月")

    def test_a1_and_d2_month_conflict_requires_review(self):
        workbook = _academy_workbook()
        workbook.active["A1"] = "健康学院2026年9月工作总结及10月工作计划"
        result = self.classify("健康学院学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.status, "review")
        self.assertEqual(result.relative_dir, "")
        self.assertIn("冲突", result.reason)

    def test_filename_and_workbook_period_conflict_requires_review(self):
        result = self.classify("健康学院学院月报-副院长-10-11.xlsx", _academy_workbook(summary="9", plan="10"))
        self.assertEqual(result.status, "review")
        self.assertEqual(result.relative_dir, "")

    def test_material_year_different_from_ding2026_requires_review(self):
        result = self.classify("健康学院学院月报-10-11.xlsx", _academy_workbook(year=2025))
        self.assertEqual(result.status, "review")
        self.assertIn("Ding2026", result.reason)

    def test_explicit_filename_year_cannot_be_overridden_by_root_year(self):
        for sheet_year in (None, 2026):
            with self.subTest(sheet_year=sheet_year):
                result = self.classify("健康学院2025年10月工作总结及11月工作计划.xlsx", _academy_workbook(year=sheet_year))
                self.assertEqual(result.status, "review", "文件名的明确年份必须与 Ding2026 核对")
                self.assertEqual(result.relative_dir, "")

    def test_school_filename_summary_year_is_also_checked(self):
        result = self.classify(
            "健康学院2025年10月重点工作总结及11月重点工作计划.xlsx",
            _school_workbook(year=2026),
        )
        self.assertEqual(result.status, "review")
        self.assertEqual(result.relative_dir, "")

    def test_plan_year_earlier_than_summary_year_requires_review(self):
        for source in ("school_header", "academy_header", "filename"):
            with self.subTest(source=source):
                if source == "school_header":
                    workbook = _school_workbook(year=2026, plan_year=2025)
                    name = "健康学院10月重点工作总结及11月重点工作计划.xlsx"
                else:
                    workbook = _academy_workbook(year=2026)
                    name = "健康学院学院月报-10-11.xlsx"
                    if source == "academy_header":
                        workbook.active["E2"] = "2025年11月工作计划"
                    else:
                        name = "健康学院2026年10月工作总结及2025年11月工作计划.xlsx"
                result = self.classify(name, workbook)
                self.assertEqual(result.status, "review")
                self.assertIn("计划年份", result.reason)
                self.assertEqual(result.relative_dir, "")

    def test_academy_december_2026_summary_and_january_2027_plan_are_valid(self):
        workbook = _academy_workbook(summary="12", plan="1", year=2026)
        workbook.active["A1"] = "健康学院2026年12月工作总结及2027年1月工作计划"
        workbook.active["E2"] = "2027年1月工作计划"
        result = self.classify("健康学院2026年12月工作总结及2027年1月工作计划.xlsx", workbook)
        self.assert_route(result, "学院月报", "12月")

    def test_multiple_people_and_roles_keep_one_workbook_destination(self):
        workbook = _academy_workbook()
        workbook.active["B4"] = "提交人乙"
        workbook.active["D4"] = "完成三次学生座谈。"
        workbook.active["E4"] = "组织两次专题培训。"
        _academy_sheet(workbook.create_sheet("副院长补充"))
        result = self.classify("健康学院学院月报-10-11.xlsx", workbook)
        self.assert_route(result, "学院月报", "10月")
        self.assertNotIn("提交人", result.relative_dir)
        self.assertNotIn("副院长", result.relative_dir)
        self.assertEqual(result.target_name, "【健康学院】学院月报-副院长.xlsx")

    def test_department_single_report_uses_summary_month_and_preserves_extension(self):
        result = self.classify("学院月报-10-11.XLSX", _academy_workbook(group="系/部/中心"))
        self.assert_route(result, "学院月报", "10月")
        self.assertEqual(result.target_name, "【健康学院】学院月报-医学影像系-10月-提交人甲.XLSX")

    def test_center_report_ignores_unfilled_roster_and_strips_job_title(self):
        workbook = _academy_workbook(group="系/部/中心")
        workbook.active["A3"] = "科研管理中心副主任"
        workbook.active["A4"] = "学生竞赛管理中心主任"
        workbook.active["B4"] = "提交人乙"
        workbook.active["D4"] = "待填"
        result = self.classify("学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.target_name, "【健康学院】学院月报-科研管理中心-10月-提交人甲.xlsx")

    def test_merged_department_applies_to_actual_filled_person_only(self):
        workbook = _academy_workbook(group="系/部/中心", populated=False)
        sheet = workbook.active
        sheet.merge_cells("A3:A4")
        sheet["B4"] = "提交人乙"
        sheet["D4"] = "完成当期工作。"
        result = self.classify("学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.target_name, "【健康学院】学院月报-医学影像系-10月-提交人乙.xlsx")

    def test_unmerged_missing_department_is_not_filled_from_previous_person(self):
        workbook = _academy_workbook(group="系/部/中心", populated=False)
        workbook.active["B4"] = "提交人乙"
        workbook.active["D4"] = "完成当期工作。"
        result = self.classify("学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.status, "review")
        self.assertIn("系部/管理中心", result.reason)

    def test_real_deputy_layout_reads_name_from_deputy_column(self):
        workbook = _academy_workbook()
        sheet = workbook.active
        sheet["B2"] = "分管范围"
        sheet["C2"] = sheet["D2"].value
        sheet["D2"] = sheet["E2"].value
        sheet["E2"] = None
        sheet["A3"] = "提交人甲"
        sheet["B3"] = "教学管理"
        sheet["C3"] = "完成两次检查。"
        sheet["D3"] = "安排下期检查。"
        result = self.classify("学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.target_name, "【健康学院】学院月报-副院长-10月-提交人甲.xlsx")

    def test_repeated_rows_for_same_person_are_not_a_summary(self):
        workbook = _academy_workbook(group="系/部/中心")
        sheet = workbook.active
        sheet.merge_cells("A3:A4")
        sheet.merge_cells("B3:B4")
        sheet["D4"] = "补充一项当期工作。"
        result = self.classify("学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.target_name, "【健康学院】学院月报-医学影像系-10月-提交人甲.xlsx")

    def test_department_summary_uses_category_without_month_or_people(self):
        workbook = _academy_workbook(group="系/部/中心")
        workbook.active["A4"] = "健康体育部"
        workbook.active["B4"] = "提交人乙"
        workbook.active["D4"] = "完成当期工作。"
        result = self.classify("学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.target_name, "【健康学院】学院月报-系主任管理中心.xlsx")

    def test_explicit_summary_with_one_filled_person_still_uses_summary_name(self):
        result = self.classify("学院月报汇总-10-11.xlsx", _academy_workbook(group="系/部/中心"))
        self.assertEqual(result.target_name, "【健康学院】学院月报-系主任管理中心.xlsx")

    def test_mixed_summary_categories_require_review(self):
        workbook = _academy_workbook()
        _academy_sheet(workbook.create_sheet("系部月报"), group="系/部/中心")
        result = self.classify("学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.status, "review")
        self.assertIn("汇总类别", result.reason)

    def test_missing_person_or_unsafe_unit_requires_review(self):
        for address, value in (("B3", None), ("B3", "某某"), ("A3", "科研/管理中心")):
            with self.subTest(address=address, value=value):
                workbook = _academy_workbook(group="系/部/中心")
                workbook.active[address] = value
                result = self.classify("学院月报-10-11.xlsx", workbook)
                self.assertEqual(result.status, "review")
                self.assertFalse(result.target_name)

    def test_filename_person_conflict_is_not_silently_renamed(self):
        workbook = _academy_workbook(group="系/部/中心")
        workbook.active["B4"] = "提交人乙"
        result = self.classify("学院月报-提交人乙-10-11.xlsx", workbook)
        self.assertEqual(result.status, "review")
        self.assertIn("人员不一致", result.reason)

    def test_personal_filename_with_other_filled_people_is_not_renamed_as_summary(self):
        workbook = _academy_workbook(group="系/部/中心")
        workbook.active["A4"] = "健康体育部"
        workbook.active["B4"] = "提交人乙"
        workbook.active["D4"] = "另一名人员实际填写。"
        result = self.classify("学院月报-提交人乙-10-11.xlsx", workbook)
        self.assertEqual(result.status, "review")
        self.assertIn("人员不一致", result.reason)

    def test_one_person_with_conflicting_units_is_not_renamed_as_summary(self):
        workbook = _academy_workbook(group="系/部/中心")
        workbook.active["A4"] = "健康体育部"
        workbook.active["B4"] = "提交人甲"
        workbook.active["D4"] = "同一人另一项工作。"
        result = self.classify("学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.status, "review")
        self.assertIn("单位不唯一", result.reason)

    def test_normalized_combined_summary_name_does_not_select_historical_month(self):
        workbook = _academy_workbook(group="系/部/中心", summary="7-8", plan="9")
        _academy_sheet(workbook.create_sheet("7月历史"), summary="7", plan="8", group="系/部/中心")
        name = "【健康学院】学院月报-医学影像系-07-08月-提交人甲.xlsx"
        result = self.classify(name, workbook)
        self.assert_route(result, "学院月报", "07-08月")
        self.assertEqual(result.target_name, name)

    def test_department_management_and_student_affairs_header_is_recognized(self):
        result = self.classify(
            "健康学院学院月报-系主任管理中心-10-11.xlsx",
            _academy_workbook(group="系（部）/管理中心/学工"),
        )
        self.assert_route(result, "学院月报", "10月")

    def test_unrelated_monthly_type_is_skipped(self):
        workbook = Workbook()
        workbook.active["A1"] = "设备巡检2026年10月总结及11月计划"
        workbook.active["A2"] = "设备"
        workbook.active["B2"] = "巡检情况"
        workbook.active["B3"] = "测试设备运转正常。"
        result = self.classify("设备巡检月报-10-11.xlsx", workbook)
        self.assertEqual(result.status, "skip", result.reason)
        self.assertEqual(result.relative_dir, "")

    def test_quality_reports_and_submission_progress_are_skipped(self):
        for name in ("健康学院教学质量月报-10-11.xlsx", "学院月报报送进度表-10月.xlsx", "学院月报提交统计-10月.xlsx"):
            with self.subTest(name=name):
                result = self.classify(name, _academy_workbook())
                self.assertEqual(result.status, "skip")

    def test_root_year_is_sufficient_when_workbook_omits_year(self):
        self.assert_route(self.classify("健康学院学院月报-10-11.xlsx", _academy_workbook(year=None)), "学院月报", "10月")

    def test_missing_material_year_and_unknown_root_year_require_review(self):
        path = self.save("健康学院学院月报-10-11.xlsx", _academy_workbook(year=None))
        result = classify_monthly(path, Path(self.temporary.name) / "材料收件箱")
        self.assertEqual(result.status, "review")
        self.assertIn("年份", result.reason)

    def test_missing_summary_and_plan_months_require_review(self):
        workbook = _academy_workbook()
        workbook.active["A1"] = "健康学院工作总结及工作计划"
        workbook.active["D2"] = "当月工作总结"
        workbook.active["E2"] = "下月工作计划"
        result = self.classify("健康学院学院月报-副院长.xlsx", workbook)
        self.assertEqual(result.status, "review")
        self.assertEqual(result.relative_dir, "")

    def test_old_xls_requires_conversion_and_review(self):
        path = self.root / "健康学院学院月报-10-11.xls"
        path.write_bytes(b"synthetic unreadable legacy workbook")
        result = classify_monthly(path, self.root)
        self.assertEqual(result.status, "review")
        self.assertIn("xlsx", result.reason)

    def test_corrupt_xlsx_requires_review_without_raising(self):
        path = self.root / "健康学院学院月报-10-11.xlsx"
        path.write_bytes(b"synthetic damaged workbook")
        result = classify_monthly(path, self.root)
        self.assertEqual(result.status, "review")
        self.assertIn("无法读取", result.reason)

    def test_hidden_history_content_does_not_count_as_current_submission(self):
        workbook = _academy_workbook(populated=False)
        historical = workbook.create_sheet("历史副本")
        _academy_sheet(historical)
        historical.sheet_state = "hidden"
        result = self.classify("健康学院学院月报-10-11.xlsx", workbook)
        self.assertEqual(result.status, "skip")

    def test_reader_preserves_sheet_order_hidden_flag_and_cell_addresses(self):
        workbook = _academy_workbook()
        historical = workbook.create_sheet("历史月报")
        _academy_sheet(historical, summary="9", plan="10")
        historical.sheet_state = "hidden"
        path = self.save("健康学院学院月报-10-11.xlsx", workbook)
        sheets = read_workbook(path)
        self.assertEqual([sheet.name for sheet in sheets], ["当期月报", "历史月报"])
        self.assertEqual([sheet.hidden for sheet in sheets], [False, True])
        self.assertEqual(sheets[0].cells["B3"], "提交人甲")
        self.assertEqual(sheets[0].cells["D2"], "2026年10月工作总结")

    def test_classification_preserves_workbook_bytes_and_creates_no_archive(self):
        workbook = _academy_workbook()
        _academy_sheet(workbook.create_sheet("9月历史"), summary="9", plan="10")
        path = self.save("健康学院学院月报-10-11.xlsx", workbook)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        modified = path.stat().st_mtime_ns
        entries = set(self.root.rglob("*"))
        self.assert_route(classify_monthly(path, self.root), "学院月报", "10月")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        self.assertEqual(path.stat().st_mtime_ns, modified)
        self.assertEqual(set(self.root.rglob("*")), entries)


if __name__ == "__main__":
    unittest.main()
