import unittest

from integrations.file_distribution.weekly import classify_weekly


class WeeklyClassificationTests(unittest.TestCase):
    def test_supported_department_names_and_alias(self):
        for name, expected in (
            ("医学信息工程系", "医学信息工程系"),
            ("医学影像系", "医学影像系"),
            ("健康服务与管理系", "健康服务与管理系"),
            ("健服系", "健康服务与管理系"),
            ("健康体育部", "健康体育部"),
        ):
            with self.subTest(name=name):
                result = classify_weekly(f"{name}2026-2027-1第2周会议纪要.pdf")
                self.assertEqual(result.status, "ready")
                self.assertEqual(result.department, expected)
                self.assertEqual(result.period, "2026-2027-1")
                self.assertEqual(
                    result.relative_dir,
                    f"02_学期工作/2026-2027-1/03_会议_考勤/党政联席会_系部例会/{expected}",
                )

    def test_chinese_term_short_years_and_unicode(self):
        for period in ("2026-2027学年第一学期", "26-27-1", "２０２６—２０２７—１", "2026_2027_1"):
            with self.subTest(period=period):
                result = classify_weekly(f"医学影像系{period}第十周会议纪要.docx")
                self.assertEqual((result.status, result.period), ("ready", "2026-2027-1"))
                self.assertIn("第十周", result.reason)

    def test_previous_academic_year_and_third_term_are_preserved(self):
        for period in ("2025-2026-3", "2025-2026学年第3学期", "2025-2026学年小学期"):
            with self.subTest(period=period):
                result = classify_weekly(f"医学影像系{period}第4周会议纪要20260908.pdf")
                self.assertEqual((result.status, result.period), ("ready", "2025-2026-3"))
                self.assertNotIn("2026-2027-1", result.relative_dir)

    def test_minutes_title_variants(self):
        for title in ("会议纪要", "系部例会", "周工作例会", "第1周例会", "例会纪要"):
            with self.subTest(title=title):
                result = classify_weekly(f"健康体育部2026-2027-1{title}.doc")
                self.assertEqual((result.status, result.kind), ("ready", "会议纪要"))

    def test_attendance_and_cross_week_labels(self):
        for week in ("准备周", "第一至二周", "第1周至第2周", "第1-2周", "第一、二周"):
            with self.subTest(week=week):
                result = classify_weekly(f"健服系26-27-1{week}考勤表.xlsx")
                self.assertEqual((result.status, result.kind), ("ready", "考勤记录"))
                self.assertTrue(result.relative_dir.endswith("考勤记录/健康服务与管理系"))
                self.assertNotIn("未识别周次", result.reason)

    def test_no_week_does_not_block_known_term_and_department(self):
        result = classify_weekly("医学信息工程系2026-2027-1会议纪要.pdf")
        self.assertEqual(result.status, "ready")
        self.assertIn("未识别周次", result.reason)

    def test_explicit_scanned_pdf_name_needs_no_body(self):
        result = classify_weekly("医学影像系26-27-1第2周考勤情况.pdf", "")
        self.assertEqual(result.status, "ready")

    def test_metadata_can_fill_missing_filename_details(self):
        text = "健康医疗科技学院\n医学信息工程系\n2026-2027学年第一学期\n第一周会议纪要\n会议时间：2026年9月16日\n一、工作内容\n其他正文"
        result = classify_weekly("会议纪要20260916.pdf", text)
        self.assertEqual((result.status, result.department, result.period), ("ready", "医学信息工程系", "2026-2027-1"))

    def test_split_academic_year_and_term_fields(self):
        result = classify_weekly("医学影像系考勤.xlsx", "学年：2026-2027\n学期：1\n第2周考勤表")
        self.assertEqual((result.status, result.period), ("ready", "2026-2027-1"))

    def test_body_mentions_of_other_department_and_future_term_are_ignored(self):
        text = "医学信息工程系会议纪要\n2026-2027学年第一学期\n会议时间：2026年9月16日\n一、工作安排\n与医学影像系协作，讨论2026-2027学年第三学期工作计划。\n附件：考勤表"
        result = classify_weekly("医学信息工程系26-27-1第1周会议纪要.docx", text)
        self.assertEqual((result.status, result.period), ("ready", "2026-2027-1"))

    def test_unlabelled_narrative_does_not_become_metadata(self):
        text = "医学信息工程系会议纪要\n2026-2027学年第一学期\n计划与医学影像系开展交流，筹备2026-2027学年第三学期工作。"
        self.assertEqual(classify_weekly("医学信息工程系会议纪要.docx", text).status, "ready")

    def test_meeting_location_and_participants_do_not_change_department(self):
        for separator in ("：", " ", ""):
            with self.subTest(separator=separator):
                text = f"医学信息工程系2026-2027学年第一学期会议纪要\n会议地点{separator}医学影像系会议室\n参会人员{separator}医学影像系教师"
                self.assertEqual(classify_weekly("医学信息工程系会议纪要.docx", text).status, "ready")

    def test_plain_body_sentence_does_not_supply_missing_semester(self):
        text = "医学信息工程系会议纪要\n医学影像系将在2026-2027学年第三学期举办交流活动。"
        result = classify_weekly("医学信息工程系会议纪要.docx", text)
        self.assertEqual(result.status, "review")
        self.assertEqual(result.department, "医学信息工程系")
        self.assertIn("缺少", result.reason)

    def test_discussion_subject_is_not_a_period_or_department_header(self):
        text = "医学信息工程系会议纪要\n2026-2027学年第一学期\n会议主题：医学影像系2026-2027学年第三学期教学活动"
        result = classify_weekly("医学信息工程系会议纪要.docx", text)
        self.assertEqual((result.status, result.period), ("ready", "2026-2027-1"))

    def test_conflicting_terms_in_filename_and_heading_need_review(self):
        result = classify_weekly("医学影像系26-27-1第1周会议纪要.pdf", "医学影像系2026-2027学年第三学期会议纪要")
        self.assertEqual(result.status, "review")
        self.assertIn("冲突", result.reason)
        self.assertEqual(result.relative_dir, "")

    def test_conflicting_terms_inside_title_need_review(self):
        result = classify_weekly("医学影像系2026-2027-1第三学期会议纪要.pdf")
        self.assertEqual(result.status, "review")

    def test_conflicting_academic_years_need_review(self):
        result = classify_weekly("医学影像系2026-2027-1会议纪要.pdf", "医学影像系2025-2026学年第一学期会议纪要")
        self.assertEqual(result.status, "review")

    def test_conflicting_department_titles_need_review(self):
        result = classify_weekly("医学影像系26-27-1会议纪要.pdf", "医学信息工程系2026-2027学年第一学期会议纪要")
        self.assertEqual(result.status, "review")
        self.assertIn("多个部门", result.reason)

    def test_calendar_date_never_infers_semester(self):
        for filename in ("医学影像系会议纪要20260916.pdf", "医学影像系2026-11-1会议纪要.pdf", "医学影像系第一周会议纪要.pdf"):
            with self.subTest(filename=filename):
                result = classify_weekly(filename, "会议时间：2026年9月16日")
                self.assertEqual(result.status, "review")
                self.assertEqual(result.relative_dir, "")

    def test_month_day_suffix_cannot_supply_a_short_academic_year(self):
        for suffix in ("10-11", "10_11"):
            with self.subTest(suffix=suffix):
                result = classify_weekly(f"医学影像系第一学期第7周会议纪要-{suffix}.pdf")
                self.assertEqual(result.status, "review")
                self.assertEqual(result.period, "")
                self.assertEqual(result.relative_dir, "")

    def test_dated_filename_does_not_conflict_with_explicit_academic_year(self):
        for date in ("2026-10-28", "2026_10_28", "2026-11-1"):
            with self.subTest(date=date):
                result = classify_weekly(f"医学影像系2026-2027学年第一学期第7周会议纪要-{date}.pdf")
                self.assertEqual((result.status, result.period), ("ready", "2026-2027-1"))

    def test_slash_dates_in_metadata_never_supply_or_conflict_with_years(self):
        result = classify_weekly("医学影像系第一学期第7周会议纪要.pdf", "会议日期：10/11")
        self.assertEqual(result.status, "review")
        result = classify_weekly("医学影像系2026-2027学年第一学期第7周会议纪要.pdf", "会议日期：2026/10/28")
        self.assertEqual((result.status, result.period), ("ready", "2026-2027-1"))

    def test_short_year_pair_requires_academic_label_or_complete_numeric_period(self):
        for title in ("26-27学年第一学期", "26-27-1"):
            with self.subTest(title=title):
                result = classify_weekly(f"医学影像系{title}会议纪要.pdf")
                self.assertEqual((result.status, result.period), ("ready", "2026-2027-1"))
        self.assertEqual(classify_weekly("医学影像系26-27第一学期会议纪要.pdf").status, "review")

    def test_short_year_metadata_field_is_explicit(self):
        result = classify_weekly("医学影像系会议纪要.docx", "学年：26-27\n学期：1\n第一周会议纪要")
        self.assertEqual((result.status, result.period), ("ready", "2026-2027-1"))

    def test_missing_department_needs_review(self):
        self.assertEqual(classify_weekly("2026-2027-1第1周会议纪要.pdf").status, "review")

    def test_nonconsecutive_years_need_review(self):
        result = classify_weekly("医学影像系2026-2028-1第1周会议纪要.pdf")
        self.assertEqual(result.status, "review")
        self.assertIn("不连续", result.reason)

    def test_combined_minutes_and_attendance_need_review(self):
        self.assertEqual(classify_weekly("医学影像系26-27-1会议纪要及考勤.pdf").status, "review")

    def test_other_business_and_departments_are_out_of_scope(self):
        for name in (
            "医学影像系26-27-1系部例会通知.docx",
            "医学影像系26-27-1会议纪要新闻稿.docx",
            "健康学院党政联席会26-27-1会议纪要.pdf",
            "管理中心26-27-1会议纪要.pdf",
            "学工26-27-1考勤表.xlsx",
            "产业园26-27-1考勤记录.pdf",
            "学院月报-医学影像系-10-11.xlsx",
            "医学影像系26-27-1考勤管理办法.docx",
            "医学影像系26-27-1考勤安排.docx",
            "校党委2026年第7次会议纪要.pdf",
            "健康学院党总支26-27-1会议纪要.pdf",
            "医学影像系教学指导委员会26-27-1会议纪要.pdf",
            "学校党委2026年10月28日会议纪要.pdf",
        ):
            with self.subTest(name=name):
                self.assertEqual(classify_weekly(name).status, "ignored")

    def test_non_department_meeting_identified_in_document_heading(self):
        result = classify_weekly("2026-2027-1会议纪要.pdf", "健康学院党总支委员会会议纪要")
        self.assertEqual(result.status, "ignored")

    def test_temporary_templates_and_unsupported_files(self):
        self.assertEqual(classify_weekly("~$医学影像系26-27-1会议纪要.docx").status, "skip")
        self.assertEqual(classify_weekly("医学影像系26-27-1会议纪要模板.docx").status, "skip")
        self.assertEqual(classify_weekly("医学影像系26-27-1会议纪要.exe").status, "ignored")


if __name__ == "__main__":
    unittest.main()
