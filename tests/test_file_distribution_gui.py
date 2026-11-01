"""Desktop authorization boundaries; no test distributes real user files."""

from dataclasses import replace
import threading
import time
import tkinter as tk
from unittest.mock import Mock

import pytest

from integrations.file_distribution.gui import DistributionWindow
from integrations.file_distribution.models import ExecutionResult, Plan, PlanItem


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


def test_preview_never_executes_and_only_ready_rows_can_be_selected(make_window):
    app, scanner, executor, _ = make_window()
    app.preview()
    wait_idle(app)
    scanner.assert_called_once_with(app.source_var.get(), "monthly")
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
    executor.assert_called_once_with(plan, ["月报甲.xlsx"])
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

    def scan_new(root, mode):
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

    def blocked_scan(root, mode):
        release.wait(3)
        return Plan(root=root, mode=mode, created_at="test", plan_id="busy", scanned_count=0)

    app, _, executor, _ = make_window(scan_fn=blocked_scan)
    try:
        app.preview()
        for control in (app.browse_button, app.preview_button, *app.mode_buttons, app.execute_button):
            assert "disabled" in control.state()
        app.distribute()
        executor.assert_not_called()
    finally:
        release.set()
    wait_idle(app)
    assert "disabled" not in app.preview_button.state()
