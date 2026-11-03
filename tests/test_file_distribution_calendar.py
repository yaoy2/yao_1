"""Calendar-bound dates and weeks use the user-confirmed school calendar."""

from datetime import date

import pytest

from integrations.file_distribution.school_calendar import WEEK_RANGES, week_for_date
from integrations.file_distribution.weekly import classify_weekly
from integrations.file_distribution import engine
from tests.test_file_distribution_engine import write_minutes, read_events


@pytest.mark.parametrize('label,start,end', [
    ('第1周', '2026-09-14', '2026-09-20'), ('第2周', '2026-09-21', '2026-09-27'),
    ('第3周', '2026-09-28', '2026-10-04'), ('第4周', '2026-10-05', '2026-10-11'),
    ('第5周', '2026-10-12', '2026-10-18'), ('第6周', '2026-10-19', '2026-10-25'),
    ('第7周', '2026-10-26', '2026-11-01'), ('第8周', '2026-11-02', '2026-11-08'),
    ('第9周', '2026-11-09', '2026-11-15'), ('第10周', '2026-11-16', '2026-11-22'),
    ('第11周', '2026-11-23', '2026-11-29'), ('第12周', '2026-11-30', '2026-12-06'),
    ('第13周', '2026-12-07', '2026-12-13'), ('第14周', '2026-12-14', '2026-12-20'),
    ('第15周', '2026-12-21', '2026-12-27'), ('第16周', '2026-12-28', '2027-01-03'),
    ('考试周', '2027-01-04', '2027-01-10'), ('总结周', '2027-01-11', '2027-01-15'),
])
def test_calendar_table_boundaries(label, start, end):
    assert WEEK_RANGES[label] == (date.fromisoformat(start), date.fromisoformat(end))
    assert week_for_date(date.fromisoformat(start)) == week_for_date(date.fromisoformat(end)) == label


@pytest.mark.parametrize('stamp,week', [
    ('2026年9月14日', '第1周'), ('2026-10-01', '第3周'), ('2026_10_05', '第4周'),
    ('20261028', '第7周'), ('2026/11/1', '第7周'), ('2026.12.1', '第12周'),
    ('2027年1月3日', '第16周'), ('2027年1月8日', '考试周'), ('20270115', '总结周'),
])
def test_material_dates_determine_semester_without_batch_context(stamp, week):
    result = classify_weekly(f'健康体育部会议纪要{stamp.replace("/", "-")}.pdf', calendar_period='')
    assert (result.status, result.period) == ('ready', '2026-2027-1')
    assert week in result.reason


@pytest.mark.parametrize('hint', ['第七周', '10月28日', '10-28', '10_28', '10.28'])
def test_partial_dates_and_weeks_need_explicit_batch_context(hint):
    name = f'健康体育部{hint}会议纪要.doc'
    assert classify_weekly(name).status == 'ready'
    assert classify_weekly(name, calendar_period='').status == 'review'


@pytest.mark.parametrize('name,text', [
    ('健康体育部第7周会议纪要20261020.pdf', ''),
    ('健康体育部第5周考勤.docx', '周次：第六周'),
    ('健康体育部2026-2027-1考勤20270116.pdf', ''),
    ('健康体育部2025-2026-1会议纪要20261020.doc', ''),
    ('健康体育部第17周考勤.pdf', ''),
    ('健康体育部准备周考勤.pdf', ''),
    ('健康体育部第1周考勤20270914.pdf', ''),
    ('健康体育部考勤20260913.pdf', ''),
    ('健康体育部考勤20260230.pdf', ''),
    ('健康体育部2027年第1周考勤.pdf', ''),
    ('健康体育部2025年10月28日会议纪要.docx', ''),
    ('健康体育部2025年会议纪要-10月28日.doc', ''),
    ('健康体育部2026-2027学年第二学期第7周考勤.pdf', '日期：2026年10月28日'),
])
def test_conflicting_and_out_of_calendar_material_stays_for_review(name, text):
    result = classify_weekly(name, text)
    assert result.status == 'review'
    assert not result.relative_dir


def test_metadata_dates_and_time_ranges_do_not_conflict():
    result = classify_weekly('健康体育部会议纪要.docx', '健康体育部周工作例会\n时间：2026年10月28日14:30-15:30')
    assert (result.status, result.period) == ('ready', '2026-2027-1')
    assert '第7周' in result.reason
    result = classify_weekly('健康体育部会议纪要.docx', '时间：2026-10-28 14:30-15:30')
    assert result.status == 'ready'
    assert '2026-10-28' in result.reason
    assert classify_weekly('健康体育部第4周会议纪要.docx', '会议日期：10/11').status == 'ready'
    result = classify_weekly('健康体育部第7周考勤.docx', '考勤日期：2026年10月26日—10月30日')
    assert result.status == 'ready'
    assert '2026-10-30' in result.reason
    result = classify_weekly('健康体育部会议纪要.docx', '健康体育部会议纪要\n会议日期\n2026年10月28日 星期三 14:30-15:30')
    assert (result.status, result.period) == ('ready', '2026-2027-1')


def test_cross_week_attendance_and_exam_labels():
    assert classify_weekly('健康体育部第6-7周考勤.docx', '考勤日期：2026年10月19日至10月30日').status == 'ready'
    assert classify_weekly('健康体育部考试周考勤20270108.pdf').status == 'ready'
    assert classify_weekly('健康体育部总结周考勤20270115.pdf').status == 'ready'
    assert classify_weekly('健康体育部第1周会议纪要.docx', '一、工作安排\n未来拟于2027年1月18日参加会议').status == 'ready'


def test_execution_reuses_preview_calendar_context_and_records_it(tmp_path):
    source = write_minutes(tmp_path, name='健康体育部第4周会议纪要.docx', text=['健康体育部第4周会议纪要', '一、工作安排'])
    assert engine.scan(tmp_path, 'weekly', calendar_period='').items[0].status == 'review'
    plan = engine.scan(tmp_path, 'weekly')
    assert plan.items[0].status == 'ready'
    result = engine.execute(plan, [source.name])
    assert result.moved == 1
    assert read_events(result)[0]['calendar_period'] == '2026-2027-1'
