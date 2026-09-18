import unittest

from utils.schedule_docx import is_physical_education
from utils.schedule_excel import (
    mark_source_overlaps,
    parse_summary_entry,
    parse_summary_weeks,
    select_authoritative_records,
)


def entry(text, *, sheet="医信工系", cell="E3", day="星期二", previous=None):
    return parse_summary_entry(text, sheet, cell, day, "2026-2027-1", previous or [])


class ScheduleExcelTest(unittest.TestCase):
    def test_disjoint_semicolon_and_even_week_notation(self):
        self.assertEqual([1, 2, 4, 5, 6, 7, 8], parse_summary_weeks("1-2 ，4-8周"))
        self.assertEqual([1, 2, 3, 4, 10, 11], parse_summary_weeks("1-4、10-11周"))
        self.assertEqual([1, *range(8, 17)], parse_summary_weeks("1周；8-16周"))
        self.assertEqual([6, 8, 10, 12], parse_summary_weeks("6-12周(双)"))

    def test_preserves_course_parentheses_and_lab_name(self):
        record = entry("【1】张三 程序设计基础（Python）（5-8周）2-5节 F3118 生理学实验室 医学信息26201 人数:0")
        self.assertEqual("程序设计基础（Python）", record["course"])
        self.assertEqual("F3118生理学实验室", record["classroom"])
        self.assertEqual("医学信息26201", record["class_group"])
        self.assertEqual((2, 5), (record["start_period"], record["end_period"]))
        self.assertEqual(0, record["student_count"])

    def test_week_prefix_is_not_left_in_course_name(self):
        record = entry("【1】陈慧 临床医学概论（第1周；8-16周）8-9节 F3121人体解剖学实验室 医学影像25201 人数:48")
        self.assertEqual("临床医学概论", record["course"])
        self.assertEqual([1, *range(8, 17)], record["weeks"])

    def test_count_before_classes_and_attached_lab_suffix(self):
        first = entry("【1】李全珍 思维创新与开发 （1-10周） 3-4节 A5303 选课人数：75 数媒技术24214，虚拟现实24201")
        self.assertEqual("数媒技术24214，虚拟现实24201", first["class_group"])
        self.assertEqual(75, first["student_count"])
        second = entry("【1】高静 健康照护（7-16周）1-2节 F3119临床技能实验室健康管理24201 人数:28")
        self.assertEqual("F3119临床技能实验室", second["classroom"])
        self.assertEqual("健康管理24201", second["class_group"])

    def test_missing_fields_are_not_guessed(self):
        record = entry("【1】许文博 放射物理与防护（1-16周）4-5节 医学影像25201 人数：50")
        self.assertEqual("", record["classroom"])
        self.assertEqual("医学影像25201", record["class_group"])
        record = entry("【1】史鸿儒 综合实训（1-10周）2-5节 F3117")
        self.assertEqual("", record["class_group"])
        self.assertIsNone(record["student_count"])

    def test_missing_periods_use_only_an_unambiguous_previous_match(self):
        old = entry("【1】熊亮宇 国家安全教育（二）（4-7周）1-2节 E5225 大数据25204 人数:106", day="星期三")
        raw = "【5】熊亮宇 国家安全教育（二）4-7周 E5225 大数据25204 选课人数:106"
        current = entry(raw, sheet="素质老师", cell="H3", day="星期三", previous=[old])
        self.assertEqual((1, 2), (current["start_period"], current["end_period"]))
        self.assertTrue(current["periods_from_previous"])
        self.assertIn("未列节次", current["import_notes"][0])
        for previous in [[], [old, dict(old, start_period=3, end_period=4)], [dict(old, term="2025-2026-2")]]:
            with self.assertRaisesRegex(ValueError, "不能唯一补齐"):
                entry(raw, sheet="素质老师", cell="H3", day="星期三", previous=previous)

    def test_primary_sheets_override_council_without_merging_wrong_weeks_or_rooms(self):
        primary = entry("【1】庞晨昕 程序设计基础（Python）（5-8周）2-5节 F3218 智能医学26301 人数:0")
        duplicate = entry(primary["raw"], sheet="院务会")
        stale = entry("【2】庞晨昕 程序设计基础（Python）（1-8周）2-5节 F3201 智能医学26301 人数:0", sheet="院务会")
        supplement = entry("【3】郭洋 专业导引（1-8周）6-7节 F3104 医学影像26201 人数:30", sheet="院务会", cell="E4")
        selected, overridden, duplicates = select_authoritative_records([stale, duplicate, supplement, primary])
        self.assertEqual(2, len(selected))
        self.assertEqual([stale], overridden)
        self.assertEqual(1, duplicates)
        kept = next(r for r in selected if r["teacher_label"] == "庞晨昕")
        self.assertEqual(("5-8周", "F3218"), (kept["week_text"], kept["classroom"]))
        self.assertEqual(2, len(kept["source_refs"]))

    def test_primary_assignment_wins_when_council_names_a_different_teacher(self):
        primary = entry("【1】栾永康 思维创新与开发（1-16周）2-3节 F3215 人力资源26201 人数:0", sheet="素质老师")
        stale = entry("【1】张勇 思维创新与开发（1-16周）2-3节 F3215 人力资源26201 人数:133", sheet="院务会")
        selected, overridden, _duplicates = select_authoritative_records([primary, stale])
        self.assertEqual(["栾永康"], [r["teacher_label"] for r in selected])
        self.assertEqual([stale], overridden)

    def test_preserves_and_marks_overlaps_within_authoritative_source(self):
        first = entry("【1】雷楠楠 国家安全教育（二）（4-7周）6-7节 A7118 虚拟现实25201 人数:110", sheet="素质老师")
        second = entry("【2】雷楠楠 大学生心理健康教育（1-8周）6-7节 A5201 财务管理26216 人数:0", sheet="素质老师")
        other_weeks = entry("【3】雷楠楠 医学心理学（9-16周）6-7节 A5201 财务管理26216 人数:0", sheet="素质老师")
        records = [first, second, other_weeks]
        overlaps = mark_source_overlaps(records)
        self.assertEqual(1, len(overlaps))
        self.assertEqual([4, 5, 6, 7], overlaps[0]["weeks"])
        self.assertTrue(first["import_notes"])
        self.assertTrue(second["import_notes"])
        self.assertFalse(other_weeks["import_notes"])
        self.assertEqual(3, len(records))

    def test_excludes_sports_electives_but_retains_other_courses_in_sports_department(self):
        for course in ["花球啦啦操", "羽毛球技战术实战运动与提高（1）", "篮球规则与篮球裁判法", "艾扬格正位瑜伽", "排球基础", "街舞入门", "跆拳道品势与竞技高级", "舞蹈文化与艺术体验"]:
            self.assertTrue(is_physical_education(course))
        self.assertFalse(is_physical_education("思维创新与开发"))


if __name__ == "__main__":
    unittest.main()
