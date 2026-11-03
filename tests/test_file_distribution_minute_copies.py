"""Two verified minute archives, safe retries, and material-based monthly routing."""

from pathlib import Path
import shutil

import pytest

from integrations.file_distribution import engine
from integrations.file_distribution.school_calendar import filing_month
from tests.test_file_distribution_engine import write_minutes, digest, inventory, read_events


@pytest.mark.parametrize('evidence,period,month', [
    (['会议时间：2026年10月27日', '第7周'], '2026-2027-1', '10月'),
    (['会议时间：2026年11月1日', '第7周'], '2026-2027-1', '11月'),
    (['会议日期：10月27日'], '2026-2027-1', '10月'),
    (['第4周'], '2026-2027-1', '10月'),
    (['考试周'], '2026-2027-1', '1月'),
    (['会议日期：2025年10月20日'], '2025-2026-1', '10月'),
])
def test_filing_month_uses_dates_before_week_ranges(evidence, period, month):
    assert filing_month(evidence, period) == (month, '')


@pytest.mark.parametrize('evidence,period', [
    (['第7周'], '2026-2027-1'), (['第16周'], '2026-2027-1'),
    (['2026年10月31日—11月1日'], '2026-2027-1'),
    (['第4周'], '2025-2026-1'), (['10月20日'], '2025-2026-1'),
])
def test_ambiguous_months_need_review(evidence, period):
    month, error = filing_month(evidence, period)
    assert not month and error


def test_selected_minutes_get_two_identical_copies_with_original_and_summary_paths_logged(tmp_path):
    source = write_minutes(tmp_path)
    other = write_minutes(tmp_path, week=8)
    data = source.read_bytes()
    plan = engine.scan(tmp_path, ('minutes',))
    item = next(item for item in plan.items if item.name == source.name)
    assert '10月会议纪要-健康学院' in item.summary_destination
    assert Path(item.summary_destination).name == Path(item.destination).name
    result = engine.execute(plan, [source.name])
    assert result.moved == 1 and result.copied == 0
    assert not source.exists() and other.exists()
    assert Path(item.destination).read_bytes() == Path(item.summary_destination).read_bytes() == data
    logged = next(event['file'] for event in read_events(result) if event['event'] == 'planned')
    assert logged['source'] == str(source)
    assert logged['destination'] == item.destination
    assert logged['summary_destination'] == item.summary_destination
    assert logged['sha256'] == digest(Path(item.summary_destination))


@pytest.mark.parametrize('existing', ['primary', 'summary', 'both', 'alternate_primary'])
def test_missing_copy_is_completed_and_existing_content_is_never_rewritten(tmp_path, existing):
    source = write_minutes(tmp_path)
    item = engine.scan(tmp_path, 'weekly').items[0]
    primary, summary = Path(item.destination), Path(item.summary_destination)
    if existing in {'primary', 'both', 'alternate_primary'}:
        primary.parent.mkdir(parents=True)
        if existing == 'alternate_primary':
            primary = primary.with_name('历史原文件名.docx')
        shutil.copy2(source, primary)
    if existing in {'summary', 'both'}:
        summary.parent.mkdir(parents=True)
        shutil.copy2(source, summary)
    prior = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (primary, summary) if p.exists()}
    plan = engine.scan(tmp_path, 'weekly')
    item = plan.items[0]
    if existing == 'both':
        assert item.status == 'duplicate'
        return
    assert item.status == 'ready'
    result = engine.execute(plan, [source.name])
    assert primary.read_bytes() == summary.read_bytes()
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in prior.items())
    if existing in {'primary', 'alternate_primary'}:
        assert result.copied == 1 and result.moved == 0 and source.exists()
    else:
        assert result.moved == 1 and not source.exists()


def test_summary_collision_after_preview_blocks_both_destinations(tmp_path):
    source = write_minutes(tmp_path)
    plan = engine.scan(tmp_path, 'weekly')
    item = plan.items[0]
    summary = Path(item.summary_destination)
    summary.parent.mkdir(parents=True)
    summary.write_bytes(b'another document')
    result = engine.execute(plan, [source.name])
    assert result.items[0].status == 'collision'
    assert source.exists() and not Path(item.destination).exists()
    assert summary.read_bytes() == b'another document'


def test_failed_primary_move_keeps_source_and_summary_then_retry_finishes(tmp_path, monkeypatch):
    source = write_minutes(tmp_path)
    plan = engine.scan(tmp_path, 'weekly')
    item = plan.items[0]
    native_move = engine._move_no_replace

    def fail(*args):
        raise OSError('simulated primary archive failure')

    monkeypatch.setattr(engine, '_move_no_replace', fail)
    first = engine.execute(plan, [source.name])
    summary = Path(item.summary_destination)
    assert first.items[0].status == 'error' and source.exists()
    assert summary.read_bytes() == source.read_bytes()
    before = summary.stat().st_mtime_ns
    monkeypatch.setattr(engine, '_move_no_replace', native_move)
    second = engine.execute(engine.scan(tmp_path, 'weekly'), [source.name])
    assert second.moved == 1 and not source.exists()
    assert summary.stat().st_mtime_ns == before
    assert Path(item.destination).read_bytes() == summary.read_bytes()


def test_failed_partial_copy_is_cleaned_and_source_is_kept(tmp_path, monkeypatch):
    source = write_minutes(tmp_path)
    plan = engine.scan(tmp_path, 'weekly')

    def fail(src, dst, length):
        dst.write(b'partial')
        raise OSError('simulated copy failure')

    monkeypatch.setattr(engine.shutil, 'copyfileobj', fail)
    result = engine.execute(plan, [source.name])
    assert result.items[0].status == 'error' and source.exists()
    assert not Path(plan.items[0].destination).exists()
    assert not Path(plan.items[0].summary_destination).exists()


def test_duplicate_source_after_success_is_not_copied_a_third_time(tmp_path):
    source = write_minutes(tmp_path)
    plan = engine.scan(tmp_path, 'weekly')
    assert engine.execute(plan, [source.name]).moved == 1
    shutil.copy2(plan.items[0].destination, source)
    before = inventory(tmp_path)
    assert engine.scan(tmp_path, 'weekly').items[0].status == 'duplicate'
    assert inventory(tmp_path) == before


def test_cross_month_week_without_date_is_held_for_review(tmp_path):
    write_minutes(tmp_path, text=['医学信息工程系第7周会议纪要', '一、工作安排'])
    item = engine.scan(tmp_path, 'weekly').items[0]
    assert item.status == 'review' and '跨月' in item.reason
    assert not item.destination and not item.summary_destination


def test_attendance_has_only_original_destination(tmp_path):
    source = write_minutes(tmp_path, name='医学信息工程系第7周考勤.docx',
                           text=['医学信息工程系第7周考勤', '考勤日期：2026年10月27日'])
    plan = engine.scan(tmp_path, ('attendance',))
    assert plan.items[0].status == 'ready' and not plan.items[0].summary_destination
    assert engine.execute(plan, [source.name]).moved == 1


def test_tampered_summary_destination_cannot_write_outside_root(tmp_path):
    source = write_minutes(tmp_path)
    plan = engine.scan(tmp_path, 'weekly')
    plan.items[0].summary_destination = str(tmp_path.parent / 'outside.docx')
    result = engine.execute(plan, [source.name])
    assert result.items[0].status == 'changed' and source.exists()
    assert not Path(plan.items[0].destination).exists()


def test_summary_destination_race_keeps_other_file_and_source(tmp_path, monkeypatch):
    source = write_minutes(tmp_path)
    plan = engine.scan(tmp_path, 'weekly')
    item = plan.items[0]
    native_copy = engine._copy_no_replace

    def race(stream, target, digest):
        target.write_bytes(b'created by another process')
        native_copy(stream, target, digest)

    monkeypatch.setattr(engine, '_copy_no_replace', race)
    result = engine.execute(plan, [source.name])
    assert result.items[0].status == 'error' and source.exists()
    assert not Path(item.destination).exists()
    assert Path(item.summary_destination).read_bytes() == b'created by another process'


def test_changed_summary_after_primary_move_is_not_reported_as_success(tmp_path, monkeypatch):
    source = write_minutes(tmp_path)
    plan = engine.scan(tmp_path, 'weekly')
    item = plan.items[0]
    original = source.read_bytes()
    native_move = engine._move_no_replace

    def change_summary(src, dst, stream):
        native_move(src, dst, stream)
        Path(item.summary_destination).write_bytes(b'changed after copy')

    monkeypatch.setattr(engine, '_move_no_replace', change_summary)
    result = engine.execute(plan, [source.name])
    assert result.items[0].status == 'error' and result.moved == 0
    assert Path(item.destination).read_bytes() == original
    assert '月度汇总副本发生变化' in result.items[0].reason
