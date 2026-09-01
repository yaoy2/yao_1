from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from .classifier import classify_item
from .config import Settings, normalize_path
from .db import (
    add_operation_log,
    db_session,
    finish_scan_run,
    init_db,
    start_scan_run,
    upsert_file,
    upsert_plan,
    utc_now,
)
from .openlist_client import (
    OpenListClient,
    extract_media_fields,
    extract_native_id,
    extract_sha1,
    join_child_path,
)
from .safety import assert_under_allowed_root


ListFn = Callable[..., dict[str, Any]]


@dataclass
class ScanResult:
    run_id: int
    scan_dir: str
    folder_count: int = 0
    file_count: int = 0
    total_size: int = 0
    native_file_id_found: bool = False
    native_id_count: int = 0
    duplicate_native_id_count: int = 0
    missing_id_count: int = 0
    status: str = "ok"
    error: str = ""
    probed_keys: list[str] = field(default_factory=list)
    stopped_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scan_dir": self.scan_dir,
            "folder_count": self.folder_count,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "native_file_id_found": self.native_file_id_found,
            "native_id_count": self.native_id_count,
            "unique_native_id_count": self.native_id_count - self.duplicate_native_id_count,
            "duplicate_native_id_count": self.duplicate_native_id_count,
            "missing_id_count": self.missing_id_count,
            "status": self.status,
            "error": self.error,
            "probed_keys": self.probed_keys,
            "stopped_reason": self.stopped_reason,
        }


def _item_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or "").strip()


def _is_dir(item: dict[str, Any]) -> bool:
    return bool(item.get("is_dir") or item.get("is_directory"))


def _extension(name: str, is_directory: bool) -> str:
    if is_directory or "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def _time_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def scan(
    settings: Settings,
    client: OpenListClient | None = None,
    scan_dir: str | None = None,
    max_depth: int | None = None,
    max_files: int | None = None,
    list_fn: ListFn | None = None,
    scan_root_id: str = "",
) -> ScanResult:
    init_db(settings.db_path)
    target = assert_under_allowed_root(scan_dir or settings.default_scan_dir, settings)
    depth_limit = settings.default_scan_depth if max_depth is None else max(0, int(max_depth))
    file_limit = settings.default_max_files if max_files is None else max(0, int(max_files))
    if file_limit == 0:
        file_limit = 10**9

    if list_fn is None:
        live_client = client or OpenListClient(settings)
        if not live_client.token:
            live_client.login()
        list_fn = live_client.list_dir

    with db_session(settings.db_path) as conn:
        run_id = start_scan_run(conn, target, depth_limit, file_limit if file_limit < 10**9 else 0)
        result = ScanResult(run_id=run_id, scan_dir=target)
        try:
            queue: deque[tuple[str, int, str]] = deque([(target, 0, scan_root_id)])
            seen_dirs: set[str] = set()
            seen_native_ids: set[str] = set()
            while queue:
                current, depth, parent_id = queue.popleft()
                current = normalize_path(current)
                if current in seen_dirs:
                    continue
                seen_dirs.add(current)
                listing = list_fn(current) or {}
                content = listing.get("content") or []
                if content and not result.probed_keys:
                    result.probed_keys = sorted(content[0].keys())
                result.folder_count += 1
                upsert_file(
                    conn,
                    {
                        "file_id": parent_id,
                        "parent_id": "",
                        "name": current.rsplit("/", 1)[-1] or current,
                        "full_path": current,
                        "is_directory": True,
                        "extension": "",
                        "size": 0,
                        "file_id_source": "native" if parent_id else "missing",
                        "scan_time": utc_now(),
                    },
                )
                for item in content:
                    name = _item_name(item)
                    if not name:
                        continue
                    full_path = join_child_path(current, name)
                    is_directory = _is_dir(item)
                    native_id = extract_native_id(item)
                    if native_id:
                        result.native_file_id_found = True
                        result.native_id_count += 1
                        if native_id in seen_native_ids:
                            result.duplicate_native_id_count += 1
                            continue
                        seen_native_ids.add(native_id)
                        source = "native"
                    else:
                        result.missing_id_count += 1
                        source = "missing"
                    media = extract_media_fields(item)
                    record = {
                        "file_id": native_id,
                        "parent_id": str(item.get("parent_id") or parent_id),
                        "name": name,
                        "full_path": full_path,
                        "is_directory": is_directory,
                        "extension": _extension(name, is_directory),
                        "size": int(item.get("size") or 0),
                        "created_at": _time_text(item.get("created")),
                        "updated_at": _time_text(item.get("modified")),
                        "duration": media["duration"],
                        "width": media["width"],
                        "height": media["height"],
                        "media_type": media["media_type"],
                        "hash_sha1": extract_sha1(item),
                        "file_id_source": source,
                        "extra_json": item,
                        "scan_time": utc_now(),
                    }
                    if is_directory:
                        if depth < depth_limit and result.file_count < file_limit:
                            queue.append((full_path, depth + 1, native_id))
                        continue
                    if result.file_count >= file_limit:
                        result.stopped_reason = f"已达到最大文件数 {file_limit}"
                        break
                    file_row_id = upsert_file(conn, record)
                    result.file_count += 1
                    result.total_size += int(record["size"] or 0)
                    classification = classify_item(
                        name=name,
                        full_path=full_path,
                        is_directory=False,
                        extension=record["extension"],
                    )
                    upsert_plan(
                        conn,
                        {
                            "file_row_id": file_row_id,
                            "file_id": native_id,
                            "original_path": full_path,
                            "original_name": name,
                            **classification.as_dict(),
                        },
                    )
                if result.file_count >= file_limit:
                    break

            if result.file_count and not result.native_file_id_found:
                result.status = "stopped_no_native_id"
                result.stopped_reason = (
                    "OpenList 列表接口没有返回原生 115 file_id。"
                    "已停在本次扫描范围内，不会用文件名伪装成 file_id，也不会继续扩大扫描。"
                )
                add_operation_log(
                    conn,
                    {
                        "operation_id": f"probe-no-id-{run_id}",
                        "operation": "probe_file_id",
                        "old_path": target,
                        "status": "blocked",
                        "error": result.stopped_reason,
                    },
                )
            finish_scan_run(conn, run_id, result.as_dict())
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
            finish_scan_run(conn, run_id, result.as_dict())
            raise
    return result
