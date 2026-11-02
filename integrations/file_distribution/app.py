"""Portable M20 entry: its containing folder is the default source folder."""

import argparse
import json
from pathlib import Path
import sys

from .engine import scan
from .gui import run_gui
from .rules import ENTRY_FILENAME, RELEASE_DATE, VERSION


def default_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="M20 文件分发：先预览，再手动分发")
    parser.add_argument("--root", type=Path, help="源文件夹；打包程序默认使用自身所在目录")
    parser.add_argument("--mode", choices=("monthly", "weekly", "invoice"), default="monthly")
    parser.add_argument("--preview-report", type=Path, help="仅预览并写入一个新的JSON报告；绝不分发")
    args = parser.parse_args(argv)
    root = args.root or default_root()
    try:
        if args.preview_report:
            plan = scan(root, args.mode)
            with args.preview_report.open("x", encoding="utf-8") as output:
                json.dump({"version": VERSION, "release_date": RELEASE_DATE, "entry": ENTRY_FILENAME,
                           **plan.to_dict()}, output, ensure_ascii=False, indent=2)
            return 0
        run_gui(str(root), args.mode)
        return 0
    except Exception as exc:
        if args.preview_report:
            if sys.stderr:
                print(str(exc), file=sys.stderr)
        else:
            from tkinter import messagebox
            messagebox.showerror("文件分发", f"无法打开文件分发：\n{exc}")
        return 1
