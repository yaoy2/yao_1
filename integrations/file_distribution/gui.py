"""M20 desktop controls for the shared, local-only distribution engine."""

from __future__ import annotations

import os
import calendar
import queue
import subprocess
import threading
import tkinter as tk
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Iterable

from .models import ExecutionResult, Plan, PlanItem, ProgressEvent, RULE_LABELS, STATUS_LABELS, selected_rules
from .file_dates import validate_start_date
from .rules import RELEASE_DATE, VERSION
from .school_calendar import CALENDAR_LABEL, CALENDAR_PERIOD


class DistributionWindow:
    """Keep all Tk calls on the main thread; workers only return queue messages."""

    def __init__(
        self,
        window: tk.Tk,
        root: str,
        mode: str,
        *,
        scan_fn: Callable[..., Plan],
        execute_fn: Callable[..., ExecutionResult],
        auto_preview: bool = True,
        calendar_period: str = CALENDAR_PERIOD,
        start_date: str = "",
    ) -> None:
        initial_rules = selected_rules(mode)
        if calendar_period not in ("", CALENDAR_PERIOD):
            raise ValueError("尚未配置该学期校历")
        self.window = window
        self._scan_fn = scan_fn
        self._execute_fn = execute_fn
        self._plan: Plan | None = None
        self._items: list[PlanItem] = []
        self._rows: dict[str, PlanItem] = {}
        self._context_row = ""
        self._selected: set[str] = set()
        self._consumed = False
        self._busy = ""
        self._closed = False
        self._close_when_done = False
        self._job_token = 0
        self._messages: queue.Queue = queue.Queue()
        self._log_path = ""
        self.source_var = tk.StringVar(window, str(Path(root).absolute()))
        self.rule_vars = {key: tk.BooleanVar(window, key in initial_rules) for key in RULE_LABELS}
        self.calendar_var = tk.BooleanVar(window, bool(calendar_period))
        self.date_filter_var = tk.BooleanVar(window, bool(start_date))
        self.start_date_var = tk.StringVar(window, validate_start_date(start_date) if start_date else date.today().isoformat())
        self.summary_var = tk.StringVar(window, "正在准备预览。")
        self.notice_var = tk.StringVar(window, "打开窗口只预览；点击“分发已选”后才移动文件。")
        self.log_var = tk.StringVar(window, "")
        self.progress_var = tk.StringVar(window, "尚未执行分发")
        self._build()
        self.start_date_var.trace_add("write", self._date_input_changed)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_id = self.window.after(80, self._poll_messages)
        if auto_preview:
            self.window.after_idle(self.preview)

    def _build(self) -> None:
        self.window.title(f"M20 · 文件分发 {VERSION} · {RELEASE_DATE}")
        width = min(1250, max(1000, self.window.winfo_screenwidth() - 100))
        height = min(760, max(620, self.window.winfo_screenheight() - 100))
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(960, 620)
        self.window.configure(background="#F5F6F8")
        style = ttk.Style(self.window)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#F5F6F8")
        style.configure("TLabel", background="#F5F6F8", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(9, 5))
        style.configure("TCheckbutton", background="#F5F6F8", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Muted.TLabel", foreground="#5E6674", font=("Microsoft YaHei UI", 9))
        style.configure("Treeview", font=("Microsoft YaHei UI", 10), rowheight=29)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Accent.TButton", foreground="white", background="#185B91")
        style.map("Accent.TButton", background=[("disabled", "#BAC4CF"), ("active", "#174C78")])

        frame = ttk.Frame(self.window, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="M20 · 文件分发", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text=f"v{VERSION} · {RELEASE_DATE}", style="Muted.TLabel").pack(side="left", padx=(12, 0))
        ttk.Button(header, text="查看分发规则", command=self._show_rules).pack(side="right")

        source = ttk.Frame(frame)
        source.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        source.columnconfigure(1, weight=1)
        ttk.Label(source, text="材料目录").grid(row=0, column=0, padx=(0, 8))
        self.source_entry = ttk.Entry(source, textvariable=self.source_var, state="readonly")
        self.source_entry.grid(row=0, column=1, sticky="ew")
        self.browse_button = ttk.Button(source, text="选择文件夹", command=self.choose_root)
        self.browse_button.grid(row=0, column=2, padx=(8, 0))
        calendar_row = ttk.Frame(source)
        calendar_row.grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 0))
        ttk.Label(calendar_row, text=f"本批校历：{CALENDAR_LABEL}", style="Muted.TLabel").pack(side="left")
        self.calendar_button = ttk.Checkbutton(calendar_row, text="仅有周次或月日时，按本批校历补全学期",
                                               variable=self.calendar_var, command=self.change_rules)
        self.calendar_button.pack(side="left", padx=(15, 0))

        date_row = ttk.Frame(source)
        date_row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(7, 0))
        self.date_filter_button = ttk.Checkbutton(
            date_row, text="限定检索日期", variable=self.date_filter_var, command=self.change_date_filter,
        )
        self.date_filter_button.pack(side="left")
        ttk.Label(date_row, text="从").pack(side="left", padx=(10, 5))
        self.start_date_entry = ttk.Entry(date_row, textvariable=self.start_date_var, width=12)
        self.start_date_entry.pack(side="left")
        self.date_picker_button = ttk.Button(date_row, text="选日期", command=self.pick_start_date)
        self.date_picker_button.pack(side="left", padx=5)
        ttk.Label(date_row, text="至今（含起始日） · 按本机创建日期；不勾选则检索全部日期",
                  style="Muted.TLabel").pack(side="left")

        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(controls, text="分发规则：").pack(side="left")
        self.rule_buttons: list[ttk.Checkbutton] = []
        for key, label in RULE_LABELS.items():
            button = ttk.Checkbutton(
                controls, text=label, variable=self.rule_vars[key],
                command=self.change_rules,
            )
            button.pack(side="left", padx=(0, 14))
            self.rule_buttons.append(button)
        self.preview_button = ttk.Button(controls, text="预览所选规则", command=self.preview)
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

        progress_frame = ttk.Frame(frame)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        progress_frame.columnconfigure(1, weight=1)
        self.progress = ttk.Progressbar(progress_frame, mode="determinate", length=185)
        self.progress.grid(row=0, column=0, padx=(0, 10))
        ttk.Label(progress_frame, textvariable=self.progress_var, style="Muted.TLabel").grid(row=0, column=1, sticky="w")

        table = ttk.Frame(frame)
        table.grid(row=5, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table, columns=("select", "status", "name", "new_name", "target", "reason"),
            show="headings", selectmode="browse", height=13,
        )
        for key, label, size, stretch in (
            ("select", "选择", 48, False), ("status", "状态", 90, False),
            ("name", "原文件名", 280, True), ("new_name", "分发后文件名", 240, True),
            ("target", "目标文件夹", 280, True), ("reason", "说明", 240, True),
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
        self.file_menu = tk.Menu(self.window, tearoff=False, font=("Microsoft YaHei UI", 10))
        self.file_menu.add_command(label="打开文件所在位置", command=self.open_file_location)
        self.file_menu.add_command(label="打开原始文件夹", command=lambda: self.open_file_location(original_folder=True))
        self.tree.bind("<Button-3>", self._show_file_menu)

        self.tabs = ttk.Notebook(frame)
        self.tabs.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        activity_frame = ttk.Frame(self.tabs)
        details_frame = ttk.Frame(self.tabs)
        self.tabs.add(activity_frame, text="处理过程")
        self.tabs.add(details_frame, text="文件详情")
        self.activity = tk.Text(activity_frame, height=5, wrap="word", relief="flat",
                                font=("Microsoft YaHei UI", 9), state="disabled", padx=8, pady=5)
        activity_scroll = ttk.Scrollbar(activity_frame, orient="vertical", command=self.activity.yview)
        activity_scroll.pack(side="right", fill="y")
        self.activity.configure(yscrollcommand=activity_scroll.set)
        self.activity.pack(fill="x")
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
        footer.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.notice_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self.log_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.log_button = ttk.Button(footer, text="打开记录目录", command=self.open_log_folder)
        self.log_button.grid(row=0, column=1, rowspan=2, padx=(10, 0))
        self._update_controls()

    def _update_controls(self) -> None:
        idle = not self._busy
        for widget in [self.browse_button, self.calendar_button, self.date_filter_button, *self.rule_buttons]:
            widget.configure(state="normal" if idle else "disabled")
        for widget in [self.start_date_entry, self.date_picker_button]:
            widget.configure(state="normal" if idle and self.date_filter_var.get() else "disabled")
        self.preview_button.configure(state="normal" if idle and self._chosen_rules() else "disabled")
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
        self.file_menu.unpost()
        self._context_row = ""
        self._plan = None
        self._items = []
        self._rows = {}
        self._selected.clear()
        self._consumed = False
        self._log_path = ""
        self.log_var.set("")
        self.tree.delete(*self.tree.get_children())
        self._set_details("")
        self.progress.configure(value=0)
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

    def _chosen_rules(self) -> tuple[str, ...]:
        return tuple(key for key, value in self.rule_vars.items() if value.get())

    def change_rules(self) -> None:
        if not self._busy:
            self._invalidate()
            self.summary_var.set("已更改规则，请点击“预览所选规则”。" if self._chosen_rules() else "请至少勾选一项分发规则。")
            self.notice_var.set("只处理已勾选的规则；未选规则不会参与分发。")
            self.progress_var.set("等待预览")

    def _date_input_changed(self, *_args) -> None:
        if self.date_filter_var.get():
            self.change_date_filter()

    def change_date_filter(self) -> None:
        if not self._busy and not self._closed:
            self._invalidate()
            self.summary_var.set("已更改检索日期，请点击“预览所选规则”。")
            self.notice_var.set("按本机创建日期筛选，起始日包含在内；不勾选则检索全部日期。")
            self.progress_var.set("等待预览")

    def pick_start_date(self) -> None:
        if self._busy or not self.date_filter_var.get():
            return
        today = date.today()
        try:
            selected = date.fromisoformat(validate_start_date(self.start_date_var.get()))
        except ValueError:
            selected = today
        picker = tk.Toplevel(self.window)
        picker.title("选择检索起始日期")
        picker.transient(self.window)
        picker.resizable(False, False)
        header = ttk.Frame(picker, padding=8)
        header.pack(fill="x")
        year = tk.StringVar(picker, str(selected.year))
        month = tk.StringVar(picker, str(selected.month))
        year_choice = ttk.Combobox(header, textvariable=year, width=6, state="readonly",
                                  values=list(range(min(today.year - 30, selected.year), today.year + 1)))
        year_choice.pack(side="left")
        ttk.Label(header, text="年").pack(side="left", padx=3)
        month_choice = ttk.Combobox(header, textvariable=month, width=4, state="readonly", values=list(range(1, 13)))
        month_choice.pack(side="left")
        ttk.Label(header, text="月").pack(side="left", padx=3)
        days = ttk.Frame(picker, padding=8)
        days.pack()

        def choose(day: date) -> None:
            self.start_date_var.set(day.isoformat())
            picker.destroy()

        def render(_event=None) -> None:
            for widget in days.winfo_children():
                widget.destroy()
            for column, label in enumerate("一二三四五六日"):
                ttk.Label(days, text=label, anchor="center", width=4).grid(row=0, column=column)
            for row, week in enumerate(calendar.monthcalendar(int(year.get()), int(month.get())), 1):
                for column, number in enumerate(week):
                    if number:
                        day = date(int(year.get()), int(month.get()), number)
                        ttk.Button(days, text=str(number), width=3,
                                   style="Accent.TButton" if day == selected else "TButton",
                                   state="normal" if day <= today else "disabled",
                                   command=lambda value=day: choose(value)).grid(row=row, column=column, padx=1, pady=1)

        year_choice.bind("<<ComboboxSelected>>", render)
        month_choice.bind("<<ComboboxSelected>>", render)
        render()
        ttk.Button(picker, text="今天", command=lambda: choose(today)).pack(pady=(0, 8))
        picker.bind("<Escape>", lambda _event: picker.destroy())
        picker.grab_set()

    @staticmethod
    def _date_scope(plan: Plan) -> str:
        if not plan.start_date:
            return "创建日期：全部"
        end = datetime.fromisoformat(plan.end_time).astimezone()
        return f"创建日期：{plan.start_date} 00:00 至 {end:%Y-%m-%d %H:%M:%S}"

    def preview(self) -> None:
        if self._busy or self._closed or not self._chosen_rules():
            return
        self._invalidate()
        try:
            start_date = validate_start_date(self.start_date_var.get()) if self.date_filter_var.get() else ""
        except ValueError as error:
            self.summary_var.set("日期无效，尚未检索。")
            self.notice_var.set(str(error))
            self.progress_var.set("等待选择有效日期")
            messagebox.showerror("请检查检索日期", str(error), parent=self.window)
            return
        root, rules = self.source_var.get(), self._chosen_rules()
        calendar_period = CALENDAR_PERIOD if self.calendar_var.get() else ""
        self.summary_var.set("正在读取根目录文件并核对归档位置……")
        self.notice_var.set("预览只读取文件，不移动材料。")
        self._append_activity("开始预览：" + "、".join(RULE_LABELS[key] for key in rules))
        self._start_job("scan", lambda progress: self._scan_fn(
            root, rules, calendar_period=calendar_period, start_date=start_date, on_progress=progress))

    def _start_job(self, operation: str, action: Callable) -> None:
        self._busy = operation
        self._job_token += 1
        token = self._job_token
        self._update_controls()

        def progress(event: ProgressEvent) -> None:
            self._messages.put((token, "progress", event, None))

        def work() -> None:
            try:
                self._messages.put((token, operation, action(progress), None))
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
                if operation == "progress":
                    self._show_progress(value)
                    continue
                self._busy = ""
                if error is not None:
                    self._selected.clear()
                    self.progress_var.set("处理已中断，请查看原因并重新预览")
                    self._append_activity(f"处理失败：{error}")
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
        self.notice_var.set(self._date_scope(plan) + "。已勾选可分发文件；核对目标后点击“分发已选”。")
        self.progress.configure(maximum=1, value=1)
        self.progress_var.set("预览完成，等待点击分发")
        self._append_activity(self._date_scope(plan) + "；" + self.summary_var.get())
        self._update_controls()

    def _append_activity(self, message: str) -> None:
        self.activity.configure(state="normal")
        self.activity.insert("end", f"{datetime.now():%H:%M:%S}  {message}\n")
        self.activity.see("end")
        self.activity.configure(state="disabled")

    def _show_progress(self, event: ProgressEvent) -> None:
        self.progress.configure(maximum=max(event.total, 1), value=event.completed)
        self.progress_var.set(f"{event.completed}/{event.total}  {event.message}")
        item = event.item
        if event.stage == "moving":
            self._append_activity(event.message)
            for row_id, row_item in self._rows.items():
                if item and row_item.name == item.name:
                    values = list(self._row_values(row_item))
                    values[1] = "处理中"
                    self.tree.item(row_id, values=values)
                    self.tree.see(row_id)
                    break
        elif item:
            label = STATUS_LABELS.get(item.status, item.status)
            self._append_activity(f"{label} · {item.name} · {item.reason}")
            if event.stage == "result":
                self._items = [item if previous.name == item.name else previous for previous in self._items]
                for row_id, previous in self._rows.items():
                    if previous.name == item.name:
                        self._rows[row_id] = item
                        self.tree.item(row_id, values=self._row_values(item), tags=(item.status,))
                        break
                self._update_summary()

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
        new_name = Path(item.destination).name if item.destination else "—"
        return (checked if enabled else "", label, item.name, new_name, self._target_label(item), item.reason)

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
            self._set_details("没有找到符合所选规则和日期范围的文件。可调整起始日期或取消日期筛选；原始材料请放在所选目录的第一层。")

    def _update_summary(self) -> None:
        counts = Counter(item.status for item in self._items)
        pending = sum(counts[status] for status in ("review", "changed", "error"))
        parts = [f"扫描 {self._plan.scanned_count if self._plan else 0} 个文件",
                 f"可分发 {counts['ready']}", f"待核对 {pending}",
                 f"重复或同名 {counts['duplicate'] + counts['collision']}", f"跳过 {counts['skip']}"]
        if self._consumed:
            parts[1] = f"本次已分发 {counts['moved']}"
        if self._plan and self._plan.start_date:
            parts.append(f"日期范围外 {self._plan.date_excluded_count}")
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

    def _show_file_menu(self, event) -> str:
        self.file_menu.unpost()
        self._context_row = ""
        if self._busy or self._closed:
            return "break"
        row_id = self.tree.identify_row(event.y)
        if row_id not in self._rows or self.tree.identify_region(event.x, event.y) != "cell":
            return "break"
        self._context_row = row_id
        self.tree.selection_set(row_id)
        self.tree.focus(row_id)
        self._show_details()
        try:
            self.file_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.file_menu.grab_release()
        return "break"

    def open_file_location(self, *, original_folder: bool = False) -> None:
        item = self._rows.get(self._context_row)
        if self._busy or self._closed or item is None:
            return
        # A new file with the same name may already be back in the source folder.
        # Completed rows must still reveal the archived file from this run.
        path = Path(item.destination if item.status == "moved" and item.destination else item.source)
        if original_folder:
            path = Path(item.source).parent
        try:
            select_file = not original_folder and path.is_file()
            folder = path.parent if not original_folder else path
            if not folder.is_dir():
                raise FileNotFoundError(f"文件夹已不存在：{folder}\n请重新预览核对文件位置。")
            if select_file and os.name == "nt":
                explorer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe"
                # No command shell; quote the complete filename for Explorer's /select syntax.
                command = subprocess.list2cmdline([str(explorer)]) + f' /select,"{path}"'
                subprocess.Popen(command)
            elif hasattr(os, "startfile"):
                os.startfile(str(folder))
            else:
                messagebox.showinfo("文件所在位置", str(folder), parent=self.window)
            if not original_folder and not select_file:
                self.notice_var.set("文件不在记录的位置，已打开所在文件夹；请重新预览核对。")
        except OSError as error:
            messagebox.showerror("无法打开文件位置", str(error), parent=self.window)

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
            created = (f"本机创建时间：{datetime.fromtimestamp(item.creation_time_ns / 1_000_000_000):%Y-%m-%d %H:%M:%S}\n"
                       if item.creation_time_ns else "")
            self._set_details(
                f"文件：{item.name}\n来源：{item.source}\n目标：{item.destination or '尚不能确定'}\n"
                f"{created}状态：{STATUS_LABELS.get(item.status, item.status)}    说明：{item.reason}"
            )

    def distribute(self) -> None:
        if self._busy or self._consumed or self._plan is None:
            return
        names = [item.name for item in self._items if item.status == "ready" and item.name in self._selected]
        if not names:
            return
        if not messagebox.askokcancel(
            "确认分发", f"将移动已勾选的 {len(names)} 个文件。\n\n"
            f"材料目录：{self._plan.root}\n分发规则：{'、'.join(RULE_LABELS[key] for key in selected_rules(self._plan.rules or self._plan.mode))}\n"
            f"{self._date_scope(self._plan)}\n\n"
            "系部纪要、考勤按预览名称统一命名；党政联席会纪要保留原名。\n"
            "文件将移到预览目标，原位置不保留副本。确认后开始分发。", parent=self.window,
        ):
            return
        plan = self._plan
        self._consumed = True
        self.progress.configure(maximum=len(names), value=0)
        self.progress_var.set(f"0/{len(names)}  准备分发")
        self.tabs.select(0)
        self._append_activity(f"开始分发 {len(names)} 个文件")
        self.notice_var.set("正在分发并核验文件，请等待结果。")
        self._start_job("execute", lambda progress: self._execute_fn(plan, names, on_progress=progress))

    def _show_result(self, result: ExecutionResult) -> None:
        outcomes = {item.name: item for item in result.items}
        self._items = [outcomes.get(item.name, item) for item in self._items]
        self._selected.clear()
        self._log_path = result.log_path
        self.log_var.set(f"分发记录：{Path(result.log_path).name}" if result.log_path else "")
        self._render_rows()
        self._update_summary()
        counts = Counter(item.status for item in self._items)
        summary = (f"分发完成：已移动 {counts['moved']}，失败 {counts['error']}，"
                   f"待核对 {counts['review'] + counts['changed']}，"
                   f"跳过/未处理 {sum(counts[key] for key in ('skip', 'ready', 'duplicate', 'collision'))}")
        self.progress_var.set(summary)
        self.progress.configure(maximum=1, value=1)
        self._append_activity(summary)
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
        from .rules import USER_GUIDE

        guide = tk.Toplevel(self.window)
        guide.title(f"M20 · 分发规则 {VERSION} · {RELEASE_DATE}")
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


def run_gui(root: str, mode: str, *, calendar_period: str = CALENDAR_PERIOD, start_date: str = "") -> None:
    """Open the shared M20 local interface; it performs no automatic moves."""
    from .engine import execute, scan

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    window = tk.Tk()
    DistributionWindow(window, root, mode, scan_fn=scan, execute_fn=execute,
                       calendar_period=calendar_period, start_date=start_date)
    window.mainloop()
