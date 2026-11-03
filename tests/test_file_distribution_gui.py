"""Desktop authorization boundaries; no test distributes real user files."""

from dataclasses import replace
from datetime import date, datetime, timedelta
import gc
import os
from pathlib import Path
from types import SimpleNamespace
import threading
import time
import tkinter as tk
from unittest.mock import ANY, Mock

import pytest

from integrations.file_distribution.gui import DistributionWindow
from integrations.file_distribution.models import ExecutionResult, Plan, PlanItem, ProgressEvent


def wait_idle(app):
    deadline = time.monotonic() + 5
    while app._busy and time.monotonic() < deadline:
        app.window.update()
        time.sleep(0.01)
    assert not app._busy, "GUI worker did not finish"
    app.window.update()


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display is unavailable: {error}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def make_window(tmp_path, tk_root):
    windows = []

    def create(scan_fn=None, execute_fn=None):
        window = tk.Toplevel(tk_root)
        window.withdraw()
        items = [
            PlanItem(name="月报甲.xlsx", source=str(tmp_path / "月报甲.xlsx"),
                     destination=str(tmp_path / "月报/10月/学院月报/月报甲.xlsx"), status="ready"),
            PlanItem(name="月报乙.xlsx", source=str(tmp_path / "月报乙.xlsx"),
                     destination=str(tmp_path / "月报/10月/学院月报/月报乙.xlsx"), status="ready"),
            PlanItem(name="月份冲突.xlsx", source=str(tmp_path / "月份冲突.xlsx"), status="review"),
            PlanItem(name="重复副本.xlsx", source=str(tmp_path / "重复副本.xlsx"), status="duplicate"),
        ]
        plan = Plan(root=str(tmp_path), mode="monthly", created_at="2026-11-01T10:00:00+08:00",
                    plan_id="synthetic-preview", scanned_count=8, items=items)
        scanner = scan_fn or Mock(return_value=plan)
        executor = execute_fn or Mock(return_value=ExecutionResult([], ""))
        app = DistributionWindow(window, str(tmp_path), "monthly", scan_fn=scanner,
                                 execute_fn=executor, auto_preview=False)
        windows.append(app)
        return app, scanner, executor, plan

    yield create
    for app in windows:
        if not app._closed:
            app._destroy()
    windows.clear()
    if 'app' in locals():
        del app
    # Tk variable finalizers must run on this thread, not a later AppTest worker.
    gc.collect()


def test_preview_never_executes_and_only_ready_rows_can_be_selected(make_window):
    app, scanner, executor, _ = make_window()
    app.preview()
    wait_idle(app)
    scanner.assert_called_once_with(app.source_var.get(), ("monthly",), calendar_period="2026-2027-1", start_date="", on_progress=ANY)
    executor.assert_not_called()
    assert app._selected == {"月报甲.xlsx", "月报乙.xlsx"}
    app._toggle("file-2")
    app._toggle("file-3")
    assert app._selected == {"月报甲.xlsx", "月报乙.xlsx"}
    app.clear_selection()
    assert "disabled" in app.execute_button.state()
    app.distribute()
    executor.assert_not_called()
    app.select_all()
    assert app._selected == {"月报甲.xlsx", "月报乙.xlsx"}


def test_cancel_confirmation_preserves_preview_and_never_executes(make_window, monkeypatch):
    app, _, executor, _ = make_window()
    app.preview()
    wait_idle(app)
    confirm = Mock(return_value=False)
    monkeypatch.setattr("integrations.file_distribution.gui.messagebox.askokcancel", confirm)
    app.distribute()
    confirm.assert_called_once()
    executor.assert_not_called()
    assert not app._consumed
    assert "disabled" not in app.execute_button.state()


def test_executes_selected_ready_files_once_and_requires_new_preview(make_window, monkeypatch, tmp_path):
    app, _, executor, plan = make_window()
    executor.return_value = ExecutionResult(
        [replace(plan.items[0], status="moved", reason="内容校验一致")],
        str(tmp_path / "分发记录/receipt.jsonl"),
    )
    monkeypatch.setattr("integrations.file_distribution.gui.messagebox.askokcancel", lambda *a, **k: True)
    app.preview()
    wait_idle(app)
    app._toggle("file-1")
    app.distribute()
    wait_idle(app)
    executor.assert_called_once_with(plan, ["月报甲.xlsx"], on_progress=ANY)
    assert app._items[0].status == "moved"
    assert app._items[1].status == "ready"
    assert app.tree.item("file-1", "values")[1] == "未处理"
    assert not app._selected
    assert "disabled" in app.execute_button.state()
    app.select_all()
    app.distribute()
    executor.assert_called_once()


def test_switching_source_invalidates_old_preview_before_scan_finishes(make_window, monkeypatch, tmp_path):
    app, scanner, executor, _ = make_window()
    app.preview()
    wait_idle(app)
    release = threading.Event()
    next_root = tmp_path / "另一批材料"
    next_root.mkdir()

    def scan_new(root, mode, **kwargs):
        release.wait(3)
        return Plan(root=root, mode=mode, created_at="later", plan_id="second", scanned_count=0)

    scanner.side_effect = scan_new
    monkeypatch.setattr("integrations.file_distribution.gui.filedialog.askdirectory", lambda **k: str(next_root))
    try:
        app.choose_root()
        assert app._plan is None
        assert not app._selected
        assert "disabled" in app.execute_button.state()
        app.distribute()
        executor.assert_not_called()
    finally:
        release.set()
    wait_idle(app)
    assert app._plan.root == str(next_root)


def test_execution_failure_cannot_reuse_previously_confirmed_plan(make_window, monkeypatch):
    app, _, executor, _ = make_window()
    executor.side_effect = OSError("文件已变化，请重新预览。")
    error_dialog = Mock()
    monkeypatch.setattr("integrations.file_distribution.gui.messagebox.askokcancel", lambda *a, **k: True)
    monkeypatch.setattr("integrations.file_distribution.gui.messagebox.showerror", error_dialog)
    app.preview()
    wait_idle(app)
    app.distribute()
    wait_idle(app)
    error_dialog.assert_called_once()
    assert app._consumed
    assert not app._selected
    app.select_all()
    app.distribute()
    executor.assert_called_once()
    assert "重新预览" in app.notice_var.get()


def test_busy_preview_disables_context_changes_and_never_moves_files(make_window):
    release = threading.Event()

    def blocked_scan(root, mode, **kwargs):
        release.wait(3)
        return Plan(root=root, mode=mode, created_at="test", plan_id="busy", scanned_count=0)

    app, _, executor, _ = make_window(scan_fn=blocked_scan)
    try:
        app.preview()
        for control in (app.browse_button, app.preview_button, app.calendar_button, app.date_filter_button,
                        app.start_date_entry, app.date_picker_button, *app.rule_buttons, app.execute_button):
            assert "disabled" in control.state()
        app.distribute()
        executor.assert_not_called()
    finally:
        release.set()
    wait_idle(app)
    assert "disabled" not in app.preview_button.state()


def test_rule_changes_clear_old_selection_and_scan_only_checked_rules(make_window):
    app, scanner, executor, _ = make_window()
    app.preview()
    wait_idle(app)
    app.rule_vars['monthly'].set(False)
    app.rule_vars['minutes'].set(True)
    app.rule_vars['attendance'].set(True)
    app.change_rules()
    assert app._plan is None and not app._selected
    app.distribute()
    executor.assert_not_called()
    app.preview()
    wait_idle(app)
    scanner.assert_called_with(app.source_var.get(), ('minutes', 'attendance'), calendar_period="2026-2027-1", start_date="", on_progress=ANY)
    for value in app.rule_vars.values():
        value.set(False)
    app.change_rules()
    assert 'disabled' in app.preview_button.state()
    assert 'disabled' in app.execute_button.state()


def test_live_progress_is_visible_before_execution_returns(make_window, monkeypatch):
    app, _, executor, plan = make_window()
    release = threading.Event()
    progress_sent = threading.Event()

    def run(plan, names, *, on_progress):
        on_progress(ProgressEvent('moving', 0, 2, '正在分发：月报甲.xlsx', plan.items[0]))
        on_progress(ProgressEvent('result', 1, 2, '内容校验一致', replace(plan.items[0], status='moved')))
        progress_sent.set()
        release.wait(3)
        return ExecutionResult([replace(item, status='moved') for item in plan.items[:2]], '')

    executor.side_effect = run
    monkeypatch.setattr('integrations.file_distribution.gui.messagebox.askokcancel', lambda *a, **k: True)
    app.preview()
    wait_idle(app)
    try:
        app.distribute()
        assert progress_sent.wait(2)
        deadline = time.monotonic() + 2
        while '1/2' not in app.progress_var.get() and time.monotonic() < deadline:
            app.window.update()
            time.sleep(0.01)
        assert app._busy == 'execute'
        assert app.tree.item('file-0', 'values')[1] == '已分发'
        assert '1/2' in app.progress_var.get()
        assert '正在分发：月报甲.xlsx' in app.activity.get('1.0', 'end')
        assert 'disabled' in app.execute_button.state()
    finally:
        release.set()
    wait_idle(app)
    assert '已移动 2' in app.progress_var.get()


def test_disabling_calendar_context_invalidates_previous_plan(make_window):
    app, scanner, executor, _ = make_window()
    app.preview()
    wait_idle(app)
    app.calendar_var.set(False)
    app.change_rules()
    assert app._plan is None and not app._selected
    app.distribute()
    executor.assert_not_called()
    app.preview()
    wait_idle(app)
    assert scanner.call_args.kwargs['calendar_period'] == ''


@pytest.mark.skipif(os.name != 'nt', reason='Windows Explorer selection')
@pytest.mark.parametrize('status', ['ready', 'review', 'duplicate', 'moved'])
def test_reveal_uses_source_until_moved_then_prefers_archive(make_window, monkeypatch, status):
    app, _, executor, plan = make_window()
    item = plan.items[0]
    source, target = Path(item.source), Path(item.destination)
    source.write_bytes(b'original or a newly received same-name file')
    target.parent.mkdir(parents=True)
    target.write_bytes(b'archived file')
    item.status = status
    app._show_plan(plan)
    app._context_row = 'file-0'
    launch = Mock()
    monkeypatch.setattr('integrations.file_distribution.gui.subprocess.Popen', launch)
    app.open_file_location()
    launch.assert_called_once()
    expected = target if status == 'moved' else source
    assert f'/select,"{expected}"' in launch.call_args.args[0]
    assert source.exists() and target.exists()
    executor.assert_not_called()


def test_original_folder_and_missing_file_open_folder_without_launching_file(make_window, monkeypatch):
    app, _, executor, plan = make_window()
    app._show_plan(plan)
    app._context_row = 'file-0'
    open_folder, launch = Mock(), Mock()
    monkeypatch.setattr('integrations.file_distribution.gui.os.startfile', open_folder, raising=False)
    monkeypatch.setattr('integrations.file_distribution.gui.subprocess.Popen', launch)
    app.open_file_location(original_folder=True)
    open_folder.assert_called_once_with(str(Path(plan.items[0].source).parent))
    open_folder.reset_mock()
    app.open_file_location()
    open_folder.assert_called_once_with(str(Path(plan.items[0].source).parent))
    assert '文件不在记录的位置' in app.notice_var.get()
    launch.assert_not_called()
    executor.assert_not_called()


def test_right_click_targets_clicked_row_without_changing_distribution_checks(make_window, monkeypatch):
    app, _, executor, plan = make_window()
    app._show_plan(plan)
    checked = app._selected.copy()
    monkeypatch.setattr(app.tree, 'identify_row', lambda y: 'file-1')
    monkeypatch.setattr(app.tree, 'identify_region', lambda x, y: 'cell')
    popup = Mock()
    monkeypatch.setattr(app.file_menu, 'tk_popup', popup)
    event = SimpleNamespace(x=100, y=50, x_root=200, y_root=150)
    app._show_file_menu(event)
    popup.assert_called_once_with(200, 150)
    assert app.tree.selection() == ('file-1',)
    assert app._context_row == 'file-1' and app._selected == checked
    popup.reset_mock()
    monkeypatch.setattr(app.tree, 'identify_row', lambda y: '')
    app._show_file_menu(event)
    assert app._context_row == ''
    popup.assert_not_called()
    executor.assert_not_called()


def test_reveal_during_execution_and_missing_folders_never_launch(make_window, monkeypatch, tmp_path):
    app, _, _, plan = make_window()
    plan.items[0].source = str(tmp_path / '不存在的目录/文件.pdf')
    app._show_plan(plan)
    app._context_row = 'file-0'
    launch, error = Mock(), Mock()
    monkeypatch.setattr('integrations.file_distribution.gui.subprocess.Popen', launch)
    monkeypatch.setattr('integrations.file_distribution.gui.messagebox.showerror', error)
    app._busy = 'execute'
    app.open_file_location()
    error.assert_not_called()
    app._busy = ''
    app.open_file_location()
    error.assert_called_once()
    launch.assert_not_called()


def test_date_controls_invalidate_preview_and_toggle_back_to_all_dates(make_window, monkeypatch):
    app, scanner, executor, plan = make_window()
    assert not app.date_filter_var.get()
    app.preview()
    wait_idle(app)
    app.date_filter_button.invoke()
    assert app._plan is None and not app._selected
    assert 'disabled' not in app.start_date_entry.state()
    start = (date.today() - timedelta(days=32)).isoformat()
    app.start_date_var.set(start)
    scanner.return_value = replace(plan, start_date=start, end_time=datetime.now().astimezone().isoformat(), date_excluded_count=3)
    app.preview()
    wait_idle(app)
    assert scanner.call_args.kwargs['start_date'] == start
    assert start in app.notice_var.get() and '日期范围外 3' in app.summary_var.get()
    confirm = Mock(return_value=False)
    monkeypatch.setattr('integrations.file_distribution.gui.messagebox.askokcancel', confirm)
    app.distribute()
    assert start in confirm.call_args.args[1]
    app.start_date_var.set(date.today().isoformat())
    assert app._plan is None and not app._selected
    app.distribute()
    executor.assert_not_called()
    app.date_filter_button.invoke()
    app.preview()
    wait_idle(app)
    assert scanner.call_args.kwargs['start_date'] == ''
    assert 'disabled' in app.start_date_entry.state()


@pytest.mark.parametrize('value', ['', '2026-02-30', '10月1日', '2999-01-01'])
def test_invalid_date_never_scans_or_reuses_previous_selection(make_window, monkeypatch, value):
    app, scanner, executor, _ = make_window()
    app.preview()
    wait_idle(app)
    scanner.reset_mock()
    app.date_filter_button.invoke()
    app.start_date_var.set(value)
    error = Mock()
    monkeypatch.setattr('integrations.file_distribution.gui.messagebox.showerror', error)
    app.preview()
    error.assert_called_once()
    scanner.assert_not_called()
    assert app._plan is None and not app._selected
    app.distribute()
    executor.assert_not_called()


def test_calendar_picker_can_choose_day_and_clear_previous_preview(make_window):
    app, scanner, _, _ = make_window()
    app.date_filter_button.invoke()
    app.preview()
    wait_idle(app)
    app.pick_start_date()
    picker = next(child for child in app.window.winfo_children() if isinstance(child, tk.Toplevel))
    days = [child for child in picker.winfo_children() if child.winfo_class() == 'TFrame'][1]
    first = next(child for child in days.winfo_children() if child.winfo_class() == 'TButton' and child.cget('text') == '1')
    first.invoke()
    assert app.start_date_var.get() == date.today().replace(day=1).isoformat()
    assert app._plan is None
    assert not picker.winfo_exists()
    app.preview()
    wait_idle(app)
    assert scanner.call_args.kwargs['start_date'] == app.start_date_var.get()


def test_preview_shows_original_and_final_names_before_distribution(make_window, monkeypatch):
    app, _, executor, plan = make_window()
    item = plan.items[0]
    item.name = '医学信息工程系第七周会议纪要.docx'
    item.destination = str(Path(item.source).parent / '归档' / '医学信息工程系-会议纪要-第7周.docx')
    app._show_plan(plan)
    values = app.tree.item('file-0', 'values')
    assert values[2] == item.name and values[3] == Path(item.destination).name
    assert app.tree.heading('new_name')['text'] == '分发后文件名'
    confirm = Mock(return_value=False)
    monkeypatch.setattr('integrations.file_distribution.gui.messagebox.askokcancel', confirm)
    app.distribute()
    assert '党政联席会纪要保留原名' in confirm.call_args.args[1]
    executor.assert_not_called()


def test_minute_preview_shows_both_locations_and_copy_completion(make_window):
    app, _, _, plan = make_window()
    item = plan.items[0]
    item.summary_destination = str(Path(plan.root) / '纪要' / '10月会议纪要-健康学院' / '医学影像系' / item.name)
    app._show_plan(plan)
    assert '月度副本' in app.tree.item('file-0', 'values')[4]
    assert item.summary_destination in app.details.get('1.0', 'end')
    app._show_result(ExecutionResult([replace(item, status='copied')], ''))
    assert '补齐副本 1' in app.progress_var.get()
