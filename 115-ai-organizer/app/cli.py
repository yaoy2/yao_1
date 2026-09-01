from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .config import load_settings
from .db import db_session, file_stats, init_db
from .diagnostics import (
    DEFAULT_OPENLIST_DATA_DIR,
    ListingDiagnosticError,
    diagnose_open115_listing,
    load_open115_storage,
)
from .logging_utils import setup_logger
from .open115_provider import Open115ReadOnlyError, Open115ReadOnlyProvider
from .openlist_client import OpenListClient, OpenListError, extract_native_id
from .operations import (
    Open115Writer,
    OperationError,
    approve_safe_plans,
    build_manifest,
    execute_manifest,
    load_manifest,
    save_manifest,
)
from .planner import rebuild_plans
from .reporting import export_reports
from .safety import assert_under_allowed_root
from .scanner import scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="115 AI 文件整理系统")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="检查 OpenList 连接状态")

    probe = sub.add_parser("probe", help="列出一个目录，查看 OpenList 实际返回了哪些字段")
    probe.add_argument("--dir", dest="scan_dir", default="")

    diagnose = sub.add_parser(
        "diagnose-listing",
        help="只读诊断 OpenList 空列表与 115 隐藏属性，不显示文件名或 Token",
    )
    diagnose.add_argument(
        "--openlist-data-dir",
        default=str(DEFAULT_OPENLIST_DATA_DIR),
        help="OpenList data 目录，默认 E:\\OpenList\\data",
    )
    diagnose.add_argument("--mount-path", default="", help="OpenList 挂载路径")

    scan_cmd = sub.add_parser("scan", help="扫描云下载并写入本地索引")
    scan_cmd.add_argument("--dir", dest="scan_dir", default="")
    scan_cmd.add_argument("--depth", type=int, default=None, help="扫描深度，0 表示只扫当前目录")
    scan_cmd.add_argument("--max-files", type=int, default=None, help="最大文件数，默认 50。0 表示不限制")

    direct_scan = sub.add_parser(
        "scan-open115",
        help="通过115官方 Open API 只读扫描，并保留原生 file_id",
    )
    direct_scan.add_argument("--root-folder-id", required=True, help="本次扫描根文件夹 ID")
    direct_scan.add_argument("--dir", dest="scan_dir", default="")
    direct_scan.add_argument("--depth", type=int, default=None)
    direct_scan.add_argument("--max-files", type=int, default=None)
    direct_scan.add_argument(
        "--openlist-data-dir",
        default=str(DEFAULT_OPENLIST_DATA_DIR),
        help="OpenList data 目录，默认 E:\\OpenList\\data",
    )

    sub.add_parser("rebuild-plans", help="按当前规则重新生成整理计划，不扫描 115")
    sub.add_parser("stats", help="查看本地索引统计")

    report = sub.add_parser("report", help="导出 HTML、Excel 和 JSON 整理报告")
    report.add_argument("--output-dir", default="reports")

    sub.add_parser(
        "approve-safe",
        help="本地批准高/中置信度、非重复、具有原生ID的安全候选",
    )

    prepare = sub.add_parser(
        "prepare-execution",
        help="把已批准计划生成为带确认码的115操作清单，不修改115",
    )
    prepare.add_argument("--scan-root-id", required=True)
    prepare.add_argument("--scan-root-path", default="")
    prepare.add_argument("--organize-dir", default="已整理")
    prepare.add_argument("--include-low-confidence", action="store_true")
    prepare.add_argument("--include-duplicates", action="store_true")
    prepare.add_argument("--include-auxiliary", action="store_true")
    prepare.add_argument("--output", default="")

    execute = sub.add_parser(
        "execute-open115",
        help="按已审核清单执行建目录、改名和移动；永不删除",
    )
    execute.add_argument("--manifest", required=True)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--continue-on-error", action="store_true")
    execute.add_argument(
        "--openlist-data-dir",
        default=str(DEFAULT_OPENLIST_DATA_DIR),
    )

    full = sub.add_parser(
        "full-workflow",
        help="完整只读扫描指定文件夹并导出 HTML/Excel/JSON 报告",
    )
    full.add_argument("--root-folder-id", required=True)
    full.add_argument("--dir", dest="scan_dir", default="")
    full.add_argument("--depth", type=int, default=None)
    full.add_argument("--max-files", type=int, default=0)
    full.add_argument("--output-dir", default="reports")
    full.add_argument(
        "--openlist-data-dir",
        default=str(DEFAULT_OPENLIST_DATA_DIR),
    )
    return parser


def cmd_status(settings) -> int:
    client = OpenListClient(settings)
    info = client.ping()
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if info.get("logged_in") else 1


def cmd_probe(settings, scan_dir: str) -> int:
    client = OpenListClient(settings)
    client.login()
    target = assert_under_allowed_root(scan_dir or settings.default_scan_dir, settings)
    listing = client.list_dir(target)
    content = listing.get("content") or []
    refresh_error = ""
    if not content:
        try:
            listing = client.list_dir(target, refresh=True)
            content = listing.get("content") or []
        except OpenListError as exc:
            refresh_error = str(exc)
    sample = content[0] if content else {}
    native_ids = [extract_native_id(item) for item in content]
    native_count = sum(1 for item in native_ids if item)
    report = {
        "path": target,
        "item_count": len(content),
        "sample_keys": sorted(sample.keys()) if sample else [],
        "sample": sample,
        "native_id_count": native_count,
        "native_id_available": native_count > 0,
        "refresh_error": refresh_error,
        "diagnosis": (
            "listing_available"
            if content
            else "empty_listing_refresh_denied"
            if "Refresh without permission" in refresh_error
            else "empty_listing"
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if content and native_count == 0:
        print("警告：没有原生 file_id。程序会停在小范围探测，不会用文件名伪装成 file_id。", file=sys.stderr)
        return 2
    if not content:
        print("错误：目录列表为空，不能把这次探测当作成功。请运行 diagnose-listing。", file=sys.stderr)
        return 3
    return 0


def cmd_diagnose_listing(settings, data_dir: str, mount_path: str) -> int:
    try:
        report = diagnose_open115_listing(
            Path(data_dir),
            mount_path or settings.openlist_mount_path,
        )
    except ListingDiagnosticError as exc:
        print(json.dumps({"diagnosis": "diagnostic_failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["diagnosis"] != "listing_available" else 0


def cmd_scan(settings, scan_dir: str, depth: int | None, max_files: int | None) -> int:
    logger = setup_logger(settings.log_path)
    client = OpenListClient(settings)
    result = scan(
        settings,
        client=client,
        scan_dir=scan_dir or settings.default_scan_dir,
        max_depth=depth,
        max_files=max_files,
    )
    logger.info("scan finished: %s", result.as_dict())
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    if result.status == "stopped_no_native_id":
        return 2
    return 0 if result.status == "ok" else 1


def cmd_scan_open115(
    settings,
    root_folder_id: str,
    scan_dir: str,
    depth: int | None,
    max_files: int | None,
    data_dir: str,
) -> int:
    try:
        access_token, mounted_root_id = load_open115_storage(
            Path(data_dir), settings.openlist_mount_path
        )
        provider = Open115ReadOnlyProvider(
            access_token=access_token,
            mounted_root_id=mounted_root_id,
            scan_root_id=root_folder_id,
            logical_root=scan_dir or settings.default_scan_dir,
        )
        provider.validate_scan_root()
        result = scan(
            settings,
            scan_dir=scan_dir or settings.default_scan_dir,
            max_depth=depth,
            max_files=max_files,
            list_fn=provider.list_dir,
            scan_root_id=root_folder_id,
        )
    except (ListingDiagnosticError, Open115ReadOnlyError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status == "ok" else 1


def cmd_stats(settings) -> int:
    init_db(settings.db_path)
    with db_session(settings.db_path) as conn:
        print(json.dumps(file_stats(conn), ensure_ascii=False, indent=2))
    return 0


def cmd_prepare_execution(settings, args) -> int:
    manifest = build_manifest(
        settings,
        scan_root_id=args.scan_root_id,
        scan_root_path=args.scan_root_path or settings.default_scan_dir,
        organize_dir=args.organize_dir,
        include_low_confidence=args.include_low_confidence,
        include_duplicates=args.include_duplicates,
        include_auxiliary=args.include_auxiliary,
    )
    output = args.output or str(
        Path("reports") / f"115_操作清单_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    path = save_manifest(manifest, output)
    print(json.dumps({
        "manifest": str(path),
        "operation_count": manifest["operation_count"],
        "blocked_count": manifest["blocked_count"],
        "confirmation_code": manifest["confirmation_code"],
        "remote_writes_performed": False,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_execute_open115(settings, args) -> int:
    try:
        manifest = load_manifest(args.manifest)
        access_token, mounted_root_id = load_open115_storage(
            Path(args.openlist_data_dir), settings.openlist_mount_path
        )
        provider = Open115ReadOnlyProvider(
            access_token=access_token,
            mounted_root_id=mounted_root_id,
            scan_root_id=str(manifest["scan_root_id"]),
            logical_root=str(manifest["scan_root_path"]),
        )
        provider.validate_scan_root()
        writer = Open115Writer(access_token, str(manifest["scan_root_id"]))
        result = execute_manifest(
            settings,
            manifest,
            args.confirm,
            writer,
            continue_on_error=args.continue_on_error,
        )
    except (ListingDiagnosticError, Open115ReadOnlyError, OperationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.failed == 0 else 1


def cmd_full_workflow(settings, args) -> int:
    code = cmd_scan_open115(
        settings,
        args.root_folder_id,
        args.scan_dir,
        args.depth,
        args.max_files,
        args.openlist_data_dir,
    )
    if code != 0:
        return code
    result = export_reports(settings, args.output_dir)
    print(json.dumps({"reports": result, "remote_writes_performed": False}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    if args.command == "status":
        return cmd_status(settings)
    if args.command == "probe":
        return cmd_probe(settings, args.scan_dir)
    if args.command == "diagnose-listing":
        return cmd_diagnose_listing(settings, args.openlist_data_dir, args.mount_path)
    if args.command == "scan":
        return cmd_scan(settings, args.scan_dir, args.depth, args.max_files)
    if args.command == "scan-open115":
        return cmd_scan_open115(
            settings,
            args.root_folder_id,
            args.scan_dir,
            args.depth,
            args.max_files,
            args.openlist_data_dir,
        )
    if args.command == "rebuild-plans":
        count = rebuild_plans(settings)
        print(json.dumps({"updated": count}, ensure_ascii=False))
        return 0
    if args.command == "stats":
        return cmd_stats(settings)
    if args.command == "report":
        print(json.dumps(export_reports(settings, args.output_dir), ensure_ascii=False, indent=2))
        return 0
    if args.command == "approve-safe":
        print(json.dumps(approve_safe_plans(settings), ensure_ascii=False, indent=2))
        return 0
    if args.command == "prepare-execution":
        return cmd_prepare_execution(settings, args)
    if args.command == "execute-open115":
        return cmd_execute_open115(settings, args)
    if args.command == "full-workflow":
        return cmd_full_workflow(settings, args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
