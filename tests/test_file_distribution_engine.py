"""Move actual synthetic files; never execute against the user's Ding2026."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from types import SimpleNamespace
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook
import pytest

from integrations.file_distribution import engine


@pytest.fixture
def root(tmp_path):
    directory = tmp_path / "Ding2026"
    directory.mkdir()
    return directory


def write_minutes(root, label="甲", *, name=None, text=None):
    path = root / (name or f"医学信息工程系2026-2027-1第7周会议纪要-{label}.docx")
    paragraphs = text or ["医学信息工程系会议纪要", "2026-2027学年第一学期第7周",
                          "一、工作安排", f"完成样例事项{label}，记录后续安排。"]
    body = "".join(f"<w:p><w:r><w:t>{escape(value)}</w:t></w:r></w:p>" for value in paragraphs)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="word/document.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>'
            '</Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}<w:sectPr/></w:body></w:document>",
        )
    return path


def write_monthly(root):
    path = root / "【健康学院】学院月报-副院长-10-11.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "当期月报"
    for address, value in {
        "A1": "健康学院2026年10月工作总结及11月工作计划", "A2": "副院长",
        "B2": "分管范围", "C2": "2026年10月工作总结", "D2": "2026年11月工作计划",
        "A3": "提交人甲", "B3": "教学管理", "C3": "完成两次课程检查。", "D3": "开展一次课程研讨。",
    }.items():
        sheet[address] = value
    workbook.save(path)
    workbook.close()
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    """Ignore access time, which a read may legitimately update."""
    output = {}
    for path in [root, *root.rglob("*")]:
        info = path.lstat()
        output[str(path.relative_to(root))] = (
            path.is_dir(), info.st_mtime_ns, info.st_size if path.is_file() else None,
            digest(path) if path.is_file() else None,
        )
    return output


def ready_plan(root, mode="weekly"):
    plan = engine.scan(root, mode)
    ready = [item for item in plan.items if item.status == "ready"]
    assert ready, [(item.name, item.status, item.reason) for item in plan.items]
    return plan, ready


def result_item(result, name):
    return next(item for item in result.items if item.name == name)


def read_events(result):
    return [json.loads(line) for line in Path(result.log_path).read_text(encoding="utf-8").splitlines()]


def test_preview_makes_no_writes_and_never_recurses_into_subfolders(root):
    source = write_minutes(root)
    (root / "便笺.txt").write_text("保留原处", encoding="utf-8")
    existing = root / "已有材料"
    existing.mkdir()
    write_minutes(existing, "子目录")
    before = inventory(root)
    plan, ready = ready_plan(root)
    assert [item.name for item in ready] == [source.name]
    assert plan.scanned_count == 2
    assert inventory(root) == before
    assert not (root / "98_系统").exists()
    assert not (root / "02_学期工作").exists()


@pytest.mark.parametrize("mode", ["monthly", "weekly"])
def test_real_move_preserves_filename_bytes_and_unrelated_material(root, mode):
    source = write_monthly(root) if mode == "monthly" else write_minutes(root)
    other = root / "无关材料.bin"
    other.write_bytes(b"do not modify")
    previous = root / "已有材料"
    previous.mkdir()
    (previous / "旧记录.txt").write_text("原文件", encoding="utf-8")
    unrelated_before = inventory(previous), digest(other), other.stat().st_mtime_ns
    original = source.read_bytes()
    plan, ready = ready_plan(root, mode)
    item = ready[0]
    result = engine.execute(plan, [item.name])
    target = Path(item.destination)
    assert result.moved == 1
    assert result_item(result, source.name).status == "moved"
    assert not source.exists()
    assert target.name == source.name
    assert target.read_bytes() == original
    assert digest(target) == item.sha256
    assert (inventory(previous), digest(other), other.stat().st_mtime_ns) == unrelated_before
    assert Path(result.log_path).parent == root / "98_系统/文件分发记录"


def test_execute_only_moves_selected_ready_item(root):
    first = write_minutes(root, "甲")
    second = write_minutes(root, "乙")
    unresolved = write_minutes(root, name="医学影像系考勤记录.docx", text=["医学影像系考勤记录", "第七周"])
    plan, _ = ready_plan(root)
    assert next(item for item in plan.items if item.name == unresolved.name).status == "review"
    result = engine.execute(plan, [first.name])
    assert result.moved == 1
    assert not first.exists()
    assert second.exists() and unresolved.exists()
    assert result_item(result, second.name).status == "ready"


@pytest.mark.parametrize('rules, expected', [
    (('minutes',), {'minutes'}),
    (('attendance',), {'attendance'}),
    (('minutes', 'attendance'), {'minutes', 'attendance'}),
    (('monthly',), {'monthly'}),
    (('minutes', 'attendance', 'monthly'), {'minutes', 'attendance', 'monthly'}),
])
def test_rule_selection_moves_only_requested_categories(root, rules, expected):
    files = {
        'minutes': write_minutes(root),
        'attendance': write_minutes(root, name='医学影像系2026-2027-1第7周考勤记录.docx',
                                    text=['医学影像系考勤记录', '2026-2027学年第一学期第7周', '考勤明细']),
        'monthly': write_monthly(root),
    }
    original = {key: path.read_bytes() for key, path in files.items()}
    scans, events = [], []
    plan = engine.scan(root, rules, on_progress=scans.append)
    assert {item.name for item in plan.items} == {files[key].name for key in expected}
    assert all(item.status == 'ready' for item in plan.items)
    assert scans[-1].completed == scans[-1].total == 3
    result = engine.execute(plan, [item.name for item in plan.items], on_progress=events.append)
    assert result.moved == len(expected)
    assert [event.stage for event in events] == ['moving', 'result'] * len(expected)
    assert [event.completed for event in events if event.stage == 'result'] == list(range(1, len(expected) + 1))
    assert all(event.item.status == 'ready' for event in events if event.stage == 'moving')
    assert all(event.item.status == 'moved' for event in events if event.stage == 'result')
    for key, path in files.items():
        if key not in expected:
            assert path.read_bytes() == original[key]
        else:
            assert not path.exists()
            assert Path(result_item(result, path.name).destination).read_bytes() == original[key]
    assert read_events(result)[0]['rules'] == plan.rules


def test_progress_reports_changed_files_and_survives_display_errors(root):
    first, second = write_minutes(root, '甲'), write_minutes(root, '乙')
    plan, _ = ready_plan(root)
    first.write_bytes(b'changed after preview')
    events = []

    def progress(event):
        events.append(event)
        raise RuntimeError('display callback unavailable')

    result = engine.execute(plan, [first.name, second.name], on_progress=progress)
    assert result_item(result, first.name).status == 'changed'
    assert result_item(result, second.name).status == 'moved'
    assert [event.completed for event in events if event.stage == 'result'] == [1, 2]
    assert first.exists() and not second.exists()


@pytest.mark.parametrize("selection", ["empty", "unknown", "review"])
def test_invalid_selection_fails_before_creating_logs_or_moving_any_file(root, selection):
    source = write_minutes(root)
    unresolved = write_minutes(root, name="医学影像系考勤记录.docx", text=["医学影像系考勤记录", "第七周"])
    plan, _ = ready_plan(root)
    chosen = {"empty": [], "unknown": ["不存在的文件.docx"], "review": [source.name, unresolved.name]}[selection]
    before = inventory(root)
    with pytest.raises(ValueError):
        engine.execute(plan, chosen)
    assert inventory(root) == before


@pytest.mark.parametrize("change", ["content", "mtime"])
def test_preview_becomes_invalid_after_source_content_or_timestamp_changes(root, change):
    source = write_minutes(root)
    plan, ready = ready_plan(root)
    info = source.stat()
    if change == "content":
        payload = bytearray(source.read_bytes())
        payload[-1] ^= 1
        source.write_bytes(payload)
        os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns))
    else:
        os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
    result = engine.execute(plan, [source.name])
    assert result_item(result, source.name).status == "changed"
    assert source.exists()
    assert not Path(ready[0].destination).exists()
    assert result.moved == 0


@pytest.mark.parametrize("same_content,expected", [(True, "duplicate"), (False, "collision")])
def test_preexisting_target_is_detected_in_preview_and_kept_untouched(root, same_content, expected):
    source = write_minutes(root)
    _, ready = ready_plan(root)
    target = Path(ready[0].destination)
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes() if same_content else b"another approved version")
    before = inventory(root)
    preview = engine.scan(root, "weekly")
    assert next(item for item in preview.items if item.name == source.name).status == expected
    assert inventory(root) == before


@pytest.mark.parametrize("same_content,expected", [(True, "duplicate"), (False, "collision")])
def test_target_created_after_preview_is_rechecked_before_move(root, same_content, expected):
    source = write_minutes(root)
    plan, ready = ready_plan(root)
    target = Path(ready[0].destination)
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes() if same_content else b"do not overwrite")
    original_target = target.read_bytes()
    result = engine.execute(plan, [source.name])
    assert result_item(result, source.name).status == expected
    assert source.exists()
    assert target.read_bytes() == original_target
    assert result.moved == 0


def test_different_filename_with_same_content_is_not_duplicated(root):
    source = write_minutes(root)
    _, ready = ready_plan(root)
    target = Path(ready[0].destination)
    target.parent.mkdir(parents=True)
    existing = target.parent / "已归档原名.docx"
    shutil.copy2(source, existing)
    before = inventory(root)
    preview = engine.scan(root, "weekly")
    item = next(item for item in preview.items if item.name == source.name)
    assert item.status == "duplicate"
    assert existing.name in item.reason
    assert inventory(root) == before


def test_identical_files_in_same_batch_have_one_ready_candidate(root):
    source = write_minutes(root, "甲")
    copy = root / source.name.replace("-甲", "-乙")
    shutil.copy2(source, copy)
    plan, ready = ready_plan(root)
    assert len(ready) == 1
    duplicate = next(item for item in plan.items if item.status == "duplicate")
    assert ready[0].name in duplicate.reason
    result = engine.execute(plan, [ready[0].name])
    assert result.moved == 1
    assert Path(duplicate.source).exists()
    assert len(list(Path(ready[0].destination).parent.glob("*.docx"))) == 1


def test_old_preview_cannot_move_a_file_twice(root):
    source = write_minutes(root)
    plan, ready = ready_plan(root)
    first_result = engine.execute(plan, [source.name])
    target = Path(ready[0].destination)
    before_target = target.read_bytes(), target.stat().st_mtime_ns
    second_result = engine.execute(plan, [source.name])
    assert first_result.moved == 1
    assert second_result.moved == 0
    assert result_item(second_result, source.name).status == "changed"
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before_target


@pytest.mark.parametrize("tamper", ["source", "destination", "name"])
def test_tampered_paths_cannot_escape_root_or_move_other_files(root, tmp_path, tamper):
    source = write_minutes(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    outsider = write_minutes(outside)
    plan, ready = ready_plan(root)
    intended = Path(ready[0].destination)
    changed = next(item for item in plan.items if item.name == source.name)
    if tamper == "source":
        changed.source = str(outsider)
    elif tamper == "destination":
        changed.destination = str(outside / source.name)
    else:
        changed.name = "../outside/escape.docx"
    outside_before = inventory(outside)
    result = engine.execute(plan, [changed.name])
    assert result.moved == 0
    assert result_item(result, changed.name).status in {"error", "changed"}
    assert source.exists()
    assert not intended.exists()
    assert inventory(outside) == outside_before


def test_destination_race_does_not_overwrite_new_file(root, monkeypatch):
    source = write_minutes(root)
    plan, ready = ready_plan(root)
    native_move = engine._move_no_replace

    def racing_move(src, target, stream=None):
        target.write_bytes(b"created by another writer")
        native_move(src, target, stream)

    monkeypatch.setattr(engine, "_move_no_replace", racing_move)
    result = engine.execute(plan, [source.name])
    assert result.moved == 0
    assert result_item(result, source.name).status == "error"
    assert source.exists()
    assert Path(ready[0].destination).read_bytes() == b"created by another writer"


def test_log_persists_planned_before_move_and_result_after_hash_verification(root, monkeypatch):
    source = write_minutes(root)
    plan, ready = ready_plan(root)
    native_move = engine._move_no_replace
    expected_hash = ready[0].sha256
    events_seen_at_move = []

    def checked_move(src, target, stream=None):
        log_files = list((root / "98_系统/文件分发记录").glob("*.jsonl"))
        assert len(log_files) == 1
        records = [json.loads(line) for line in log_files[0].read_text(encoding="utf-8").splitlines()]
        events_seen_at_move.extend(record["event"] for record in records)
        assert records[-1]["event"] == "planned"
        assert records[-1]["file"]["sha256"] == expected_hash
        assert records[-1]["file"]["destination"] == str(target)
        assert not target.exists()
        native_move(src, target, stream)

    monkeypatch.setattr(engine, "_move_no_replace", checked_move)
    result = engine.execute(plan, [source.name])
    assert result.moved == 1
    assert events_seen_at_move == ["run", "planned"]
    events = read_events(result)
    assert [event["event"] for event in events] == ["run", "planned", "result", "complete"]
    assert events[2]["file"]["status"] == "moved"
    assert events[2]["file"]["sha256"] == digest(Path(ready[0].destination))
    assert events[-1]["moved"] == 1


def test_active_distribution_lock_prevents_second_run(root):
    source = write_minutes(root)
    plan, ready = ready_plan(root)
    log_dir = root / "98_系统/文件分发记录"
    log_dir.mkdir(parents=True)
    with engine._run_lock(log_dir / "running.lock"):
        with pytest.raises(RuntimeError):
            engine.execute(plan, [source.name])
    assert source.exists()
    assert not Path(ready[0].destination).exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows share-mode verification")
def test_windows_file_open_for_writing_is_not_moved(root):
    source = write_minutes(root)
    plan, ready = ready_plan(root)
    original = source.read_bytes()
    with source.open("r+b"):
        result = engine.execute(plan, [source.name])
    assert result.moved == 0
    assert result_item(result, source.name).status == "error"
    assert source.read_bytes() == original
    assert not Path(ready[0].destination).exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows rename/delete share-mode verification")
def test_windows_source_cannot_be_replaced_after_planned_record(root, monkeypatch):
    source = write_minutes(root)
    original = source.read_bytes()
    plan, ready = ready_plan(root)
    moved_aside = root / "another-writer-moved-source.docx"
    native_record = engine._write_record
    blocked = []

    def record_then_try_replacement(log, event, **payload):
        native_record(log, event, **payload)
        if event == "planned":
            with pytest.raises(OSError) as error:
                os.rename(source, moved_aside)
            blocked.append(error.value)

    monkeypatch.setattr(engine, "_write_record", record_then_try_replacement)
    result = engine.execute(plan, [source.name])
    assert len(blocked) == 1
    assert result.moved == 1
    assert not source.exists()
    assert not moved_aside.exists()
    assert Path(ready[0].destination).read_bytes() == original


@pytest.mark.skipif(os.name != "nt", reason="Windows replacement before stable move handle")
def test_windows_source_replaced_before_move_lock_is_rejected(root, monkeypatch):
    source = write_minutes(root)
    original = source.read_bytes()
    plan, ready = ready_plan(root)
    moved_aside = root / "previous-preview-version.docx"
    native_locked = engine._read_locked
    replaced = []

    @contextmanager
    def replace_before_move_lock(path, *, for_move=False):
        if for_move and path == source and not replaced:
            os.rename(source, moved_aside)
            write_minutes(root, "更新版本", name=source.name)
            replaced.append(source.read_bytes())
        with native_locked(path, for_move=for_move) as stream:
            yield stream

    monkeypatch.setattr(engine, "_read_locked", replace_before_move_lock)
    result = engine.execute(plan, [source.name])
    assert len(replaced) == 1
    assert result.moved == 0
    assert result_item(result, source.name).status in {"error", "changed"}
    assert not Path(ready[0].destination).exists()
    assert source.read_bytes() == replaced[0]
    assert source.read_bytes() != original
    assert moved_aside.read_bytes() == original
    assert "planned" not in [event["event"] for event in read_events(result)]


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only attribute verification")
def test_windows_read_only_document_moves_and_keeps_attribute(root):
    source = write_minutes(root)
    original = source.read_bytes()
    source.chmod(stat.S_IREAD)
    target = None
    try:
        plan, ready = ready_plan(root)
        target = Path(ready[0].destination)
        result = engine.execute(plan, [source.name])
        assert result.moved == 1, result_item(result, source.name).reason
        assert not source.exists()
        assert target.read_bytes() == original
        assert target.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
    finally:
        for path in (source, target):
            if path is not None and path.exists():
                path.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_gui_record_button_opens_receipt_directory_not_jsonl(root, monkeypatch):
    from integrations.file_distribution import gui

    source = write_minutes(root)
    plan, _ = ready_plan(root)
    result = engine.execute(plan, [source.name])
    opened = []
    monkeypatch.setattr(gui.os, "startfile", opened.append, raising=False)
    gui.DistributionWindow.open_log_folder(SimpleNamespace(_log_path=result.log_path, _busy="", window=None))
    assert opened == [str(Path(result.log_path).parent)]
    assert Path(opened[0]).is_dir()
