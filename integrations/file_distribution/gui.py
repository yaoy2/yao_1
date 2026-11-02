"""M20 desktop controls for the shared, local-only distribution engine."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Iterable

from .models import ExecutionResult, MODE_LABELS, Plan, PlanItem, STATUS_LABELS


class DistributionWindow:
    """Keep all Tk calls on the main thread; workers only return queue messages."""

    def __init__(
        self,
        window: tk.Tk,
        root: str,
        mode: str,
        *,
        scan_fn: Callable[[str, str], Plan],
        execute_fn: Callable[[Plan, Iterable[str]], ExecutionResult],
        auto_preview: bool = True,
    ) -> None:
        if mode not in MODE_LABELS:
            raise ValueError("请选择月报、纪要考勤或发票归档。")
        self.window = window
        self._scan_fn = scan_fn
        self._execute_fn = execute_fn
        self._plan: Plan | None = None
        self._items: list[PlanItem] = []
        self._rows: dict[str, PlanItem] = {}
        self._selected: set[str] = set()
        self._consumed = False
        self._busy = ""
        self._closed = False
        self._close_when_done = False
        self._job_token = 0
        self._messages: queue.Queue = queue.Queue()
        self._log_path = ""
        self.source_var = tk.StringVar(window, str(Path(root).absolute()))
        self.mode_var = tk.StringVar(window, mode)
        self.summary_var = tk.StringVar(window, "正在准备预览。")
        self.notice_var = tk.StringVar(window, "打开窗口只预览；点击“分发已选”后才移动文件。")
        self.log_var = tk.StringVar(window, "")
        self._build()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_id = self.window.after(80, self._poll_messages)
        if auto_preview:
            self.window.after_idle(self.preview)

    def _build(self) -> None:
        self.window.title("M20 · 文件分发")
        width = min(1250, max(1000, self.window.winfo_screenwidth() - 100))
        height = min(760, max(620, self.window.winfo_screenheight() - 100))
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(960, 580)
        self.window.configure(background="#F5F6F8")
        style = ttk.Style(self.window)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#F5F6F8")
        style.configure("TLabel", background="#F5F6F8", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(9, 5))
        style.configure("TRadiobutton", background="#F5F6F8", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Muted.TLabel", foreground="#5E6674", font=("Microsoft YaHei UI", 9))
        style.configure("Treeview", font=("Microsoft YaHei UI", 10), rowheight=29)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Accent.TButton", foreground="white", background="#185B91")
        style.map("Accent.TButton", background=[("disabled", "#BAC4CF"), ("active", "#174C78")])

        frame = ttk.Frame(self.window, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="M20 · 文件分发", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="查看分发规则", command=self._show_rules).pack(side="right")

        source = ttk.Frame(frame)
        source.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        source.columnconfigure(1, weight=1)
        ttk.Label(source, text="材料目录").grid(row=0, column=0, padx=(0, 8))
        self.source_entry = ttk.Entry(source, textvariable=self.source_var, state="readonly")
        self.source_entry.grid(row=0, column=1, sticky="ew")
        self.browse_button = ttk.Button(source, text="选择文件夹", command=self.choose_root)
        self.browse_button.grid(row=0, column=2, padx=(8, 0))

        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.mode_buttons: list[ttk.Radiobutton] = []
        for key, label in MODE_LABELS.items():
            button = ttk.Radiobutton(
                controls, text=label, value=key, variable=self.mode_var,
                command=self.change_mode,
            )
            button.pack(side="left", padx=(0, 14))
            self.mode_buttons.append(button)
        self.preview_button = ttk.Button(controls, text="重新预览", command=self.preview)
        self.preview_button.pack(side="left", padx=(0, 8))
        self.all_button = ttk.Button(controls, text="全选可分发", command=self.select_all)
        self.all_button.pack(side="left", padx=(0, 6))
        self.clear_button = ttk.Button(controls, text="清空选择", command=self.clear_selection)
        self.clear_button.pack(side="left")
        self.execute_button = ttk.Button(
            controls, text="分发已选（0）", style="Accent.TButton", command=self.distribute,
        )
        self.execute_button.pack(side="right")
        ttk.Label(frame, textvariable=self.summary_var).grid(row=3, column=0, sticky="w", pady=(0, 6))

        table = ttk.Frame(frame)
        table.grid(row=4, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table, columns=("select", "status", "name", "target", "reason"),
            show="headings", selectmode="browse", height=13,
        )
        for key, label, size, stretch in (
            ("select", "选择", 48, False), ("status", "状态", 90, False),
            ("name", "文件名", 350, True), ("target", "目标文件夹", 380, True),
            ("reason", "说明", 270, True),
        ):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=size, minwidth=45 if key == "select" else 75,
                             stretch=stretch, anchor="center" if key in {"select", "status"} else "w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        for tag, color in {"ready": "#195C3C", "moved": "#175887", "review": "#8B540B",
                           "collision": "#8B540B", "error": "#A32929", "changed": "#A32929",
                           "duplicate": "#66717F", "skip": "#66717F"}.items():
            self.tree.tag_configure(tag, foreground=color)
        self.tree.bind("<Button-1>", self._click_row)
        self.tree.bind("<space>", self._space_row)
        self.tree.bind("<<TreeviewSelect>>", self._show_details)

        details_frame = ttk.Frame(frame)
        details_frame.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(details_frame, text="选中文件的完整信息", style="Muted.TLabel").pack(anchor="w")
        self.details = tk.Text(
            details_frame, height=5, wrap="word", relief="flat", borderwidth=0,
            font=("Microsoft YaHei UI", 9), background="#FFFFFF", foreground="#303743",
            padx=8, pady=5, state="disabled",
        )
        detail_scroll = ttk.Scrollbar(details_frame, orient="vertical", command=self.details.yview)
        detail_scroll.pack(side="right", fill="y", pady=(3, 0))
        self.details.configure(yscrollcommand=detail_scroll.set)
        self.details.pack(fill="x", pady=(3, 0))
        footer = ttk.Frame(frame)
        footer.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.notice_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self.log_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.log_button = ttk.Button(footer, text="打开记录目录", command=self.open_log_folder)
        self.log_button.grid(row=0, column=1, rowspan=2, padx=(10, 0))
        self._update_controls()

    def _update_controls(self) -> None:
        idle = not self._busy
        for widget in [self.browse_button, self.preview_button, *self.mode_buttons]:
            widget.configure(state="normal" if idle else "disabled")
        selectable = idle and self._plan is not None and not self._consumed
        ready = {item.name for item in self._items if item.status == "ready"}
        self._selected.intersection_update(ready)
        self.all_button.configure(state="normal" if selectable and ready else "disabled")
        self.clear_button.configure(state="normal" if selectable and self._selected else "disabled")
        self.execute_button.configure(
            text=f"分发已选（{len(self._selected)}）",
            state="normal" if selectable and self._selected else "disabled",
        )
        self.log_button.configure(state="normal" if self._log_path and idle else "disabled")

    def _invalidate(self) -> None:
        self._plan = None
        self._items = []
        self._rows = {}
        self._selected.clear()
        self._consumed = False
        self._log_path = ""
        self.log_var.set("")
        self.tree.delete(*self.tree.get_children())
        self._set_details("")
        self._update_controls()

    def choose_root(self) -> None:
        if self._busy:
            return
        chosen = filedialog.askdirectory(
            parent=self.window, title="选择放置原始材料的 Ding2026 文件夹",
            initialdir=self.source_var.get(), mustexist=True,
        )
        if chosen and Path(chosen) != Path(self.source_var.get()):
            self.source_var.set(str(Path(chosen).absolute()))
            self.preview()

    def change_mode(self) -> None:
        if not self._busy:
            self.preview()

    def preview(self) -> None:
        if self._busy or self._closed:
            return
        self._invalidate()
        root, mode = self.source_var.get(), self.mode_var.get()
        self.summary_var.set("正在读取根目录文件并核对归档位置……")
        self.notice_var.set("预览只读取文件，不移动材料。")
        self._start_job("scan", lambda: self._scan_fn(root, mode))

    def _start_job(self, operation: str, action: Callable) -> None:
        self._busy = operation
        self._job_token += 1
        token = self._job_token
        self._update_controls()

        def work() -> None:
            try:
                self._messages.put((token, operation, action(), None))
            except Exception as error:
                self._messages.put((token, operation, None, error))

        threading.Thread(target=work, daemon=True, name=f"m20-{operation}").start()

    def _poll_messages(self) -> None:
        if self._closed:
            return
        try:
            while True:
                token, operation, value, error = self._messages.get_nowait()
                if token != self._job_token:
                    continue
                self._busy = ""
                if error is not None:
                    self._selected.clear()
                    if operation == "execute":
                        self.notice_var.set("分发中断，请重新预览核对文件的实际位置。")
                    else:
                        self.summary_var.set("预览未完成。")
                        self.notice_var.set("请检查材料目录后重新预览。")
                    self._refresh_checks()
                    if not self._close_when_done:
                        messagebox.showerror("分发中断" if operation == "execute" else "无法预览",
                                             str(error), parent=self.window)
                elif operation == "scan":
                    self._show_plan(value)
                else:
                    self._show_result(value)
                if self._close_when_done:
                    self._destroy()
                    return
        except queue.Empty:
            pass
        self._poll_id = self.window.after(80, self._poll_messages)

    def _show_plan(self, plan: Plan) -> None:
        self._plan = plan
        self._items = list(plan.items)
        self._consumed = False
        self._selected = {item.name for item in self._items if item.status == "ready"}
        self._render_rows()
        self._update_summary()
        self.notice_var.set("已自动勾选可分发文件；月报和纪要模式也会核对发票。核对目标后点击“分发已选”。")
        self._update_controls()

    def _target_label(self, item: PlanItem) -> str:
        if not item.destination:
            return "—"
        target = Path(item.destination).parent
        try:
            return str(target.relative_to(Path(self.source_var.get())))
        except ValueError:
            return str(target)

    def _row_values(self, item: PlanItem) -> tuple[str, ...]:
        enabled = item.status == "ready" and not self._consumed
        checked = "☑" if item.name in self._selected else "☐"
        label = STATUS_LABELS.get(item.status, item.status)
        if self._consumed and item.status == "ready":
            label = "未处理"
        return (checked if enabled else "", label, item.name, self._target_label(item), item.reason)

    def _render_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        for index, item in enumerate(self._items):
            row_id = f"file-{index}"
            self._rows[row_id] = item
            self.tree.insert("", "end", iid=row_id, values=self._row_values(item), tags=(item.status,))
        if self._rows:
            first = next(iter(self._rows))
            self.tree.selection_set(first)
            self.tree.focus(first)
            self._show_details()
        else:
            self._set_details("没有找到属于本项分发的文件。原始材料请放在所选目录的第一层。")

    def _update_summary(self) -> None:
        counts = Counter(item.status for item in self._items)
        pending = sum(counts[status] for status in ("review", "changed", "error"))
        parts = [f"扫描 {self._plan.scanned_count if self._plan else 0} 个文件",
                 f"可分发 {counts['ready']}", f"待核对 {pending}",
                 f"重复或同名 {counts['duplicate'] + counts['collision']}", f"跳过 {counts['skip']}"]
        if self._consumed:
            parts[1] = f"本次已分发 {counts['moved']}"
        self.summary_var.set("    ".join(parts))

    def _refresh_checks(self) -> None:
        for row_id, item in self._rows.items():
            self.tree.item(row_id, values=self._row_values(item))
        self._update_controls()

    def _toggle(self, row_id: str) -> None:
        item = self._rows.get(row_id)
        if self._busy or self._consumed or item is None or item.status != "ready":
            return
        if item.name in self._selected:
            self._selected.remove(item.name)
        else:
            self._selected.add(item.name)
        self._refresh_checks()

    def _click_row(self, event) -> None:
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            self._toggle(self.tree.identify_row(event.y))

    def _space_row(self, _event) -> str:
        self._toggle(self.tree.focus())
        return "break"

    def select_all(self) -> None:
        if not self._busy and not self._consumed and self._plan is not None:
            self._selected = {item.name for item in self._items if item.status == "ready"}
            self._refresh_checks()

    def clear_selection(self) -> None:
        if not self._busy:
            self._selected.clear()
            self._refresh_checks()

    def _set_details(self, value: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", value)
        self.details.configure(state="disabled")

    def _show_details(self, _event=None) -> None:
        selected = self.tree.selection()
        item = self._rows.get(selected[0]) if selected else None
        if item is not None:
            self._set_details(
                f"文件：{item.name}\n来源：{item.source}\n目标：{item.destination or '尚不能确定'}\n"
                f"状态：{STATUS_LABELS.get(item.status, item.status)}    说明：{item.reason}"
            )

    def distribute(self) -> None:
        if self._busy or self._consumed or self._plan is None:
            return
        names = [item.name for item in self._items if item.status == "ready" and item.name in self._selected]
        if not names:
            return
        if not messagebox.askokcancel(
            "确认分发", f"将移动已勾选的 {len(names)} 个文件。\n\n"
            f"材料目录：{self._plan.root}\n分发类别：{MODE_LABELS[self._plan.mode]}\n\n"
            "目标位置见预览列表。确认后开始分发。", parent=self.window,
        ):
            return
        plan = self._plan
        self._consumed = True
        self.notice_var.set("正在分发并核验文件，请等待结果。")
        self._start_job("execute", lambda: self._execute_fn(plan, names))

    def _show_result(self, result: ExecutionResult) -> None:
        outcomes = {item.name: item for item in result.items}
        self._items = [outcomes.get(item.name, item) for item in self._items]
        self._selected.clear()
        self._log_path = result.log_path
        self.log_var.set(f"分发记录：{Path(result.log_path).name}" if result.log_path else "")
        self._render_rows()
        self._update_summary()
        self.notice_var.set("本次分发已结束。需要继续处理时，请先重新预览。")
        self._update_controls()

    def open_log_folder(self) -> None:
        if not self._log_path or self._busy:
            return
        folder = Path(self._log_path).parent
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(folder))
            else:
                messagebox.showinfo("分发记录", str(folder), parent=self.window)
        except OSError as error:
            messagebox.showerror("无法打开目录", str(error), parent=self.window)

    def _show_rules(self) -> None:
        from .rules import USER_GUIDE, VERSION

        guide = tk.Toplevel(self.window)
        guide.title(f"M20 · 分发规则 {VERSION}")
        guide.geometry("820x580")
        guide.transient(self.window)
        guide.columnconfigure(0, weight=1)
        guide.rowconfigure(0, weight=1)
        content = tk.Text(guide, wrap="word", font=("Microsoft YaHei UI", 10), padx=16, pady=12)
        content.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(guide, orient="vertical", command=content.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        content.configure(yscrollcommand=scrollbar.set)
        content.insert("1.0", USER_GUIDE)
        content.configure(state="disabled")
        ttk.Button(guide, text="关闭", command=guide.destroy).grid(row=1, column=0, pady=8)

    def close(self) -> None:
        if self._busy == "execute":
            self._close_when_done = True
            self.notice_var.set("正在完成已开始的分发，结束后关闭窗口。")
            return
        self._destroy()

    def _destroy(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.window.after_cancel(self._poll_id)
        self.window.destroy()


def run_gui(root: str, mode: str) -> None:
    """Open the shared M20 local interface; it performs no automatic moves."""
    from .engine import execute, scan

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    window = tk.Tk()
    DistributionWindow(window, root, mode, scan_fn=scan, execute_fn=execute)
    window.mainloop()
