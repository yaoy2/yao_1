"""Command line entry point for a local mail workspace (no login or credentials)."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils import mail_workspace


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Archive verified mail batches and build private dashboard snapshots.")
    parser.add_argument("--root", required=True, help="Explicit absolute local archive directory")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--account", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--batch", required=True, help="UTF-8 JSON collection batch; no cookies or tokens")
    report = commands.add_parser("report")
    report.add_argument("--kind", choices=("daily", "morning", "weekly"), required=True)
    report.add_argument("--at", required=True, help="ISO 8601 timestamp including timezone")
    publish = commands.add_parser("publish", help="Export a sanitized snapshot; does not upload")
    publish.add_argument("--output", required=True, help="Absolute destination JSON path")
    commands.add_parser("status")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = mail_workspace.initialize(args.root, args.account)
        elif args.command == "ingest":
            with Path(args.batch).open("r", encoding="utf-8-sig") as handle:
                batch = json.load(handle)
            result = mail_workspace.ingest(args.root, batch)
        elif args.command == "report":
            result = mail_workspace.generate_report(args.root, args.kind, args.at)
        elif args.command == "publish":
            result = mail_workspace.export_snapshot(args.root, args.output)
        else:
            result = mail_workspace.status(args.root)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") != "partial" else 2
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        # Exception strings can contain local paths or input values. Keep logs terse.
        print(json.dumps({"status": "error", "error_type": type(exc).__name__,
                          "message": "操作未完成；请核对输入格式、归档状态与文件可访问性。"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
