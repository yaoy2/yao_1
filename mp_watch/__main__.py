# -*- coding: utf-8 -*-
"""python -m mp_watch [--dry-run] [--config path]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .paths import DEFAULT_CONFIG_PATH
from .runner import run_watch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="微信公众号监控归档（免费发现源 + 本地 wechat_core）")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="配置文件路径（默认仓库 config/mp_watch_sources.json）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只发现与去重，不调用 Playwright 归档",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="向 stdout 打印摘要 JSON",
    )
    args = parser.parse_args(argv)

    def progress(msg: str) -> None:
        print(msg, flush=True)

    try:
        summary = run_watch(config_path=args.config, dry_run=args.dry_run, progress=progress)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"运行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    # 有采集错误且本轮零归档时用非零退出，方便任务计划发现问题
    if summary.get("errors") and not summary.get("archived"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
