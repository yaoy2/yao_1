"""M20 standardizes only the selected department records, with original bytes."""

from pathlib import Path

import pytest

from integrations.file_distribution import engine
from integrations.file_distribution.weekly import classify_weekly
from tests.test_file_distribution_engine import write_minutes, inventory, read_events
from tests.test_file_distribution_invoices import write_invoice
from tests.test_file_distribution_party_minutes import STANDARD, HEADING


@pytest.mark.parametrize('unit,expected', [
    ('医学信息工程系', '医学信息工程系'), ('医学影像系', '医学影像系'),
    ('健康服务与管理系', '健康服务与管理系'), ('健服系', '健康服务与管理系'),
    ('健康体育部', '健康体育部'),
])
@pytest.mark.parametrize('kind,extension', [('会议纪要', '.DOCX'), ('考勤表', '.xlsx')])
def test_formal_department_names_and_original_extension_are_preserved(unit, expected, kind, extension):
    result = classify_weekly(f'{unit}2026-2027学年第一学期第七周{kind}{extension}')
    assert result.status == 'ready'
    stem = f'{expected}-会议纪要-第7周' if kind == '会议纪要' else f'考勤表-{expected}-第7周'
    assert result.target_name == stem + extension
    assert result.week_label == '第7周'


@pytest.mark.parametrize('hint,text,label', [
    ('20261028', '', '第7周'), ('', '会议日期：2026年9月21日', '第2周'),
    ('第六至七周', '考勤日期：2026年10月20日', '第6—7周'),
    ('第六、八周', '', '第6、8周'), ('考试周', '', '考试周'), ('总结周', '', '总结周'),
])
def test_calendar_dates_and_full_multi_week_ranges_supply_naming_label(hint, text, label):
    result = classify_weekly(f'健康体育部2026-2027-1-{hint}考勤表.PDF', text)
    assert result.status == 'ready', result.reason
    assert result.target_name == f'考勤表-健康体育部-{label}.PDF'


@pytest.mark.parametrize('name', [
    '医学信息工程系-会议纪要-第7周.docx', '考勤表-健康体育部-第7周.XLSX',
])
def test_already_standard_names_are_idempotent(name):
    result = classify_weekly(name)
    assert result.status == 'ready' and result.target_name == name


def test_old_term_never_uses_current_calendar_to_invent_naming_week():
    dated = classify_weekly('医学影像系2025-2026-1会议纪要20251028.pdf')
    assert dated.status == 'review' and not dated.target_name
    explicit = classify_weekly('医学影像系2025-2026-1第17周会议纪要.pdf')
    assert explicit.status == 'ready'
    assert explicit.target_name == '医学影像系-会议纪要-第17周.pdf'
    conflict = classify_weekly('医学影像系2025-2026-1第7周会议纪要.pdf', '医学影像系第8周会议纪要')
    assert conflict.status == 'review' and not conflict.target_name


def test_batch_move_uses_preview_names_and_preserves_party_name_contents_and_other_files(tmp_path):
    minutes = write_minutes(tmp_path)
    attendance = write_minutes(tmp_path, name='健服系2026-2027-1第七周考勤记录.DOCX',
                               text=['健康服务与管理系第七周考勤表', '2026-2027学年第一学期', '考勤明细'])
    party = write_invoice(tmp_path, STANDARD + ' (1).PDF', HEADING)
    other = tmp_path / '不处理的材料.txt'
    other.write_bytes(b'unchanged')
    historical = tmp_path / '历史归档'
    historical.mkdir()
    write_minutes(historical)
    historical_before = inventory(historical)
    sources = [minutes, attendance, party]
    original = {path.name: path.read_bytes() for path in sources}
    expected = {minutes.name: '医学信息工程系-会议纪要-第7周.docx',
                attendance.name: '考勤表-健康服务与管理系-第7周.DOCX', party.name: party.name}
    plan = engine.scan(tmp_path, 'weekly')
    assert all(item.status == 'ready' for item in plan.items)
    assert {item.name: Path(item.destination).name for item in plan.items} == expected
    assert all(path.exists() for path in sources)  # Preview never renames.
    result = engine.execute(plan, expected)
    assert result.moved == 3
    for item in result.items:
        target = Path(item.destination)
        assert target.name == expected[item.name]
        assert target.read_bytes() == original[item.name]
        assert not Path(item.source).exists()
    planned = [event['file'] for event in read_events(result) if event['event'] == 'planned']
    assert {item['name']: Path(item['destination']).name for item in planned} == expected
    assert {item['name']: item['week_label'] for item in planned}[minutes.name] == '第7周'
    assert inventory(historical) == historical_before and other.read_bytes() == b'unchanged'


def test_batch_different_contents_same_final_name_are_all_blocked_case_insensitively(tmp_path):
    first = write_minutes(tmp_path, '甲')
    second = write_minutes(tmp_path, '乙', name='医学信息工程系第七周会议纪要-乙.DOCX')
    before = inventory(tmp_path)
    plan = engine.scan(tmp_path, 'weekly')
    assert {item.status for item in plan.items} == {'collision'}
    assert len({item.destination.casefold() for item in plan.items}) == 1
    with pytest.raises(ValueError):
        engine.execute(plan, [first.name, second.name])
    assert inventory(tmp_path) == before


@pytest.mark.parametrize('same_content', [False, True])
def test_existing_standard_name_is_never_overwritten(tmp_path, same_content):
    source = write_minutes(tmp_path)
    plan = engine.scan(tmp_path, 'weekly')
    target = Path(plan.items[0].destination)
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes() if same_content else b'existing different record')
    before = inventory(tmp_path)
    rescanned = engine.scan(tmp_path, 'weekly')
    assert rescanned.items[0].status == ('ready' if same_content else 'collision')
    # Even the earlier preview is rechecked at execution time.
    result = engine.execute(plan, [source.name])
    assert result.moved == 0 and source.exists()
    assert target.read_bytes() == (source.read_bytes() if same_content else b'existing different record')
    assert {key: value for key, value in inventory(tmp_path).items() if key in before and not value[0]} == {
        key: value for key, value in before.items() if not value[0]}
