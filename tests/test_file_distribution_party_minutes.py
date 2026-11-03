"""Only the approved college joint-meeting PDF pattern joins the minutes rule."""

from pathlib import Path

import pytest

from integrations.file_distribution import engine
from integrations.file_distribution.weekly import classify_weekly
from tests.test_file_distribution_invoices import write_invoice


STANDARD = '健康学院党政联席会会议纪要-健康学院2026-2027学年第一学期教学第七周'
HEADING = '健康医疗科技学院会议纪要\n会议时间：2026年10月26日（2026-2027学年第一学期教学第七周）\n一、工作事项\n研究与医学影像系的协作。'


@pytest.mark.parametrize('name', [STANDARD + '.pdf', STANDARD + ' (1).pdf', STANDARD + '（2）.PDF'])
def test_standard_college_pdf_routes_to_existing_joint_meeting_folder(name):
    result = classify_weekly(name, HEADING)
    assert (result.status, result.kind, result.period) == ('ready', '学院党政联席会纪要', '2026-2027-1')
    assert result.relative_dir == '02_学期工作/2026-2027-1/03_会议_考勤/党政联席会_系部例会/党政联席会'
    assert result.target_name == ''


@pytest.mark.parametrize('name', [
    STANDARD + '.docx', STANDARD + '.doc', '党政联席会考勤表20261026.xlsx',
    '健康学院党总支委员会2026-2027-1第7周会议纪要.pdf', '校党委2026-2027-1第7周会议纪要.pdf',
    '其他学院党政联席会会议纪要-健康学院2026-2027学年第一学期教学第七周.pdf',
    '【发言稿】党政联席会20261026.docx', '封皮-党政联席会-20261026.pdf',
])
def test_other_formats_and_meetings_remain_out_of_scope(name):
    assert classify_weekly(name).status == 'ignored'


def test_party_header_week_conflict_reports_actual_calendar_week():
    name = STANDARD.replace('第七周', '第二周') + '.pdf'
    text = HEADING.replace('第七周', '第一周').replace('10月26日', '9月21日')
    result = classify_weekly(name, text)
    assert result.status == 'review'
    assert '冲突' in result.reason and '按校历日期对应第2周' in result.reason
    assert not result.relative_dir


@pytest.mark.parametrize('header', ['校党委会议纪要', '健康学院党总支委员会会议纪要', '医学影像系2026-2027-1第7周会议纪要'])
def test_standard_name_does_not_override_wrong_document_type(header):
    assert classify_weekly(STANDARD + '.pdf', header).status == 'review'


def test_actual_pdf_move_obeys_minutes_selection_and_preserves_other_files(tmp_path):
    source = write_invoice(tmp_path, STANDARD + '.pdf', HEADING)
    original = source.read_bytes()
    word_draft = tmp_path / (STANDARD + '.docx')
    word_draft.write_bytes(b'word draft not selected by this rule')
    assert not engine.scan(tmp_path, ('attendance',)).items
    plan = engine.scan(tmp_path, ('minutes',))
    assert len(plan.items) == 1 and plan.items[0].status == 'ready'
    result = engine.execute(plan, [source.name])
    assert result.moved == 1
    assert Path(result.items[0].destination).name == source.name
    assert Path(result.items[0].destination).read_bytes() == original
    summary = Path(result.items[0].summary_destination)
    assert summary.name == source.name and '10月会议纪要-健康学院' in str(summary)
    assert summary.read_bytes() == original
    assert word_draft.read_bytes() == b'word draft not selected by this rule'
    assert not source.exists()
