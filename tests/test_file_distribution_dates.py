"""Creation-date ranges are checked with synthetic Windows files only."""

from datetime import date, datetime, timedelta
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from integrations.file_distribution import app, engine, file_dates
from tests.test_file_distribution_engine import write_minutes, read_events


def set_creation_time(path, value):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(str(path), 0x100, 0x7, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    ticks = int(value.timestamp()) * 10_000_000 + value.microsecond * 10 + 116444736000000000
    creation = wintypes.FILETIME(ticks & 0xFFFFFFFF, ticks >> 32)
    set_time = kernel.SetFileTime
    set_time.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.c_void_p, ctypes.c_void_p]
    set_time.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    try:
        if not set_time(handle, ctypes.byref(creation), None, None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        close(handle)


@pytest.mark.parametrize('value', ['', '10月1日', '2026-1-01', '2026-02-30', '2026-11-03'])
def test_invalid_or_future_start_date_rejected(value):
    with pytest.raises(ValueError):
        file_dates.validate_start_date(value, today=date(2026, 11, 2))


def test_boundaries_are_local_midnight_through_exact_preview_time():
    end = datetime(2026, 11, 2, 13, 14, 15, 123456).astimezone()
    lower, upper = file_dates.creation_date_bounds('2026-10-01', end.isoformat())
    assert lower == int(datetime(2026, 10, 1).timestamp()) * 1_000_000_000
    assert upper == int(end.timestamp()) * 1_000_000_000 + 123456000
    assert file_dates.validate_start_date('2024-02-29', today=end.date()) == '2024-02-29'
    with pytest.raises(ValueError):
        file_dates.creation_date_bounds('2026-10-01', '2026-11-02T13:14:15')


def test_unix_ctime_is_not_used_as_creation_time(monkeypatch):
    monkeypatch.setattr(file_dates, 'os', SimpleNamespace(name='posix'))
    with pytest.raises(ValueError, match='创建时间'):
        file_dates.creation_time_ns(SimpleNamespace(st_ctime_ns=123))


@pytest.mark.skipif(os.name != 'nt', reason='Windows birth-time boundary integration')
def test_date_filter_includes_start_and_end_excludes_old_and_future_before_reading(tmp_path, monkeypatch):
    cutoff = datetime.combine(date.today(), datetime.min.time()).astimezone() + timedelta(hours=12)
    start = cutoff - timedelta(days=3, hours=12)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cutoff.astimezone(tz) if tz else cutoff.replace(tzinfo=None)

    monkeypatch.setattr(engine, 'datetime', Clock)
    files = []
    for label, created in [('早于范围', start - timedelta(microseconds=1)), ('起始零点', start),
                           ('截止时刻', cutoff), ('晚于截止', cutoff + timedelta(microseconds=1))]:
        path = write_minutes(tmp_path, label, week=len(files) + 1)
        set_creation_time(path, created)
        # Modified time intentionally contradicts the creation-time selection.
        os.utime(path, (start.timestamp() - 86400, start.timestamp() - 86400))
        files.append(path)
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}
    classify = Mock(wraps=engine._classify)
    monkeypatch.setattr(engine, '_classify', classify)
    plan = engine.scan(tmp_path, 'weekly', start_date=start.date().isoformat())
    assert {item.name for item in plan.items} == {files[1].name, files[2].name}
    assert all(item.status == 'ready' and item.period == '2026-2027-1' for item in plan.items)
    assert plan.date_excluded_count == 2
    assert plan.end_time == cutoff.isoformat()
    assert classify.call_count == 2
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files} == before
    assert not (tmp_path / '98_系统').exists()
    assert len(engine.scan(tmp_path, 'weekly').items) == 4


@pytest.mark.skipif(os.name != 'nt', reason='Windows creation-time execution recheck')
@pytest.mark.parametrize('change', [False, True])
def test_execution_records_filter_and_rejects_changed_creation_time(tmp_path, change):
    source = write_minutes(tmp_path)
    now = datetime.now().astimezone()
    set_creation_time(source, now - timedelta(days=1))
    start = (now.date() - timedelta(days=3)).isoformat()
    plan = engine.scan(tmp_path, 'weekly', start_date=start)
    assert plan.items[0].status == 'ready'
    if change:
        set_creation_time(source, now - timedelta(days=2))
    result = engine.execute(plan, [source.name])
    assert result.moved == (0 if change else 1)
    assert source.exists() == change
    events = read_events(result)
    assert events[0]['date_basis'] == 'local_creation_time'
    assert events[0]['start_date'] == start and events[0]['end_time'] == plan.end_time
    if change:
        assert result.items[0].status == 'changed'
        assert 'planned' not in [event['event'] for event in events]


def test_unreadable_creation_time_remains_for_review_without_content_read(tmp_path, monkeypatch):
    write_minutes(tmp_path)
    monkeypatch.setattr(engine, 'creation_time_ns', Mock(side_effect=ValueError('无法读取创建时间')))
    classify = Mock()
    monkeypatch.setattr(engine, '_classify', classify)
    plan = engine.scan(tmp_path, 'weekly', start_date=date.today().isoformat())
    assert plan.items[0].status == 'review'
    assert '无法读取创建时间' in plan.items[0].reason
    classify.assert_not_called()


def test_cli_preview_keeps_date_filter_and_invalid_dates_do_not_write_report(tmp_path):
    report = tmp_path / 'preview.json'
    assert app.main(['--root', str(tmp_path), '--start-date', date.today().isoformat(),
                     '--preview-report', str(report)]) == 0
    data = json.loads(report.read_text(encoding='utf-8'))
    assert data['start_date'] == date.today().isoformat() and data['end_time']
    invalid_report = tmp_path / 'invalid.json'
    assert app.main(['--root', str(tmp_path), '--start-date', '2026-02-30',
                     '--preview-report', str(invalid_report)]) == 1
    assert not invalid_report.exists()
