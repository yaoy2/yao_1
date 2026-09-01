from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests

from .config import Settings, normalize_path
from .db import (
    add_operation_log,
    db_session,
    init_db,
    set_plan_approved,
    set_plan_execute_status,
    utc_now,
)
from .safety import is_under_root


OPEN115_FILES_URL = "https://proapi.115.com/open/ufile/files"
OPEN115_MKDIR_URL = "https://proapi.115.com/open/folder/add"
OPEN115_MOVE_URL = "https://proapi.115.com/open/ufile/move"
OPEN115_RENAME_URL = "https://proapi.115.com/open/ufile/update"


class OperationError(RuntimeError):
    pass


AUTO_ORGANIZE_CATEGORIES = {
    "电影",
    "电视剧",
    "动漫",
    "纪录片",
    "综艺",
    "音乐视频",
    "普通视频",
}


def _valid_name(name: str) -> bool:
    text = str(name or "").strip()
    return (
        bool(text)
        and text not in {".", ".."}
        and "/" not in text
        and "\\" not in text
        and not any(ord(char) < 32 for char in text)
        and len(text.encode("utf-8")) <= 255
    )


def _canonical_manifest(manifest: dict[str, Any]) -> bytes:
    body = {key: value for key, value in manifest.items() if key != "confirmation_code"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def confirmation_code(manifest: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_manifest(manifest)).hexdigest()[:10].upper()
    return f"APPLY-{digest}"


def _plan_rows(settings: Settings) -> list[dict[str, Any]]:
    init_db(settings.db_path)
    with db_session(settings.db_path) as conn:
        current = conn.execute(
            "SELECT started_at FROM scan_runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        snapshot_start = current["started_at"] if current else ""
        return [dict(row) for row in conn.execute(
            """
            SELECT p.*, f.parent_id, f.size, f.hash_sha1, f.file_id_source
            FROM organize_plans p
            JOIN files f ON f.id = p.file_row_id
            WHERE f.scan_time >= ?
            ORDER BY p.id
            """,
            (snapshot_start,),
        )]


def _duplicate_plan_ids(rows: list[dict[str, Any]]) -> set[int]:
    groups: dict[tuple[str, int], list[int]] = defaultdict(list)
    for row in rows:
        sha1 = str(row.get("hash_sha1") or "").lower().strip()
        size = int(row.get("size") or 0)
        if sha1 and size > 0:
            groups[(sha1, size)].append(int(row["id"]))
    return {
        plan_id
        for ids in groups.values()
        if len(ids) > 1
        for plan_id in ids
    }


def approve_safe_plans(settings: Settings) -> dict[str, int]:
    rows = _plan_rows(settings)
    duplicates = _duplicate_plan_ids(rows)
    safe_ids = [
        int(row["id"])
        for row in rows
        if row.get("file_id")
        and row.get("file_id_source") == "native"
        and row.get("confidence") in {"high", "medium"}
        and row.get("category") in AUTO_ORGANIZE_CATEGORIES
        and int(row["id"]) not in duplicates
        and _valid_name(str(row.get("suggested_name") or ""))
    ]
    with db_session(settings.db_path) as conn:
        updated = set_plan_approved(conn, safe_ids, True)
    return {"eligible": len(safe_ids), "approved": int(updated)}


def build_manifest(
    settings: Settings,
    *,
    scan_root_id: str,
    scan_root_path: str,
    organize_dir: str = "已整理",
    include_low_confidence: bool = False,
    include_duplicates: bool = False,
    include_auxiliary: bool = False,
) -> dict[str, Any]:
    root_path = normalize_path(scan_root_path)
    if not is_under_root(root_path, settings.allowed_root):
        raise OperationError("整理根路径超出允许范围。")
    if not str(scan_root_id).isdigit():
        raise OperationError("扫描根文件夹 ID 格式无效。")
    if not _valid_name(organize_dir):
        raise OperationError("整理目录名无效或超过255字节。")

    rows = _plan_rows(settings)
    duplicates = _duplicate_plan_ids(rows)
    operations: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    targets: dict[str, int] = {}
    for row in rows:
        if not row.get("approved"):
            continue
        reasons: list[str] = []
        plan_id = int(row["id"])
        if not row.get("file_id") or row.get("file_id_source") != "native":
            reasons.append("缺少115原生ID")
        if not row.get("parent_id"):
            reasons.append("缺少来源父目录ID，请重新扫描")
        if row.get("confidence") == "low" and not include_low_confidence:
            reasons.append("低置信度未明确放行")
        if row.get("category") == "待识别" and not include_low_confidence:
            reasons.append("待识别项目未明确放行")
        if row.get("category") not in AUTO_ORGANIZE_CATEGORIES and not include_auxiliary:
            reasons.append("附件或其他类型未明确放行")
        if plan_id in duplicates and not include_duplicates:
            reasons.append("疑似重复文件未明确放行")
        suggested_name = str(row.get("suggested_name") or "")
        if not _valid_name(suggested_name):
            reasons.append("建议文件名无效或超过255字节")
        suggested_parts = [part for part in str(row.get("suggested_path") or "").split("/") if part]
        parent_parts = suggested_parts[:-1]
        if not parent_parts:
            parent_parts = [str(row.get("category") or "其他")]
        if any(not _valid_name(part) for part in parent_parts):
            reasons.append("建议目录名无效或超过255字节")
        target_parent_path = normalize_path("/".join([root_path, organize_dir, *parent_parts]))
        target_path = normalize_path("/".join([target_parent_path, suggested_name]))
        if not is_under_root(target_path, root_path):
            reasons.append("目标路径越过扫描根目录")
        collision_key = target_path.casefold()
        if collision_key in targets:
            reasons.append(f"与计划 {targets[collision_key]} 的目标路径冲突")
        else:
            targets[collision_key] = plan_id
        if reasons:
            blocked.append({"plan_id": plan_id, "original_path": row["original_path"], "reasons": reasons})
            continue
        operations.append(
            {
                "operation_id": str(uuid.uuid4()),
                "plan_id": plan_id,
                "file_id": str(row["file_id"]),
                "source_parent_id": str(row["parent_id"]),
                "original_path": str(row["original_path"]),
                "original_name": str(row["original_name"]),
                "target_parent_parts": [organize_dir, *parent_parts],
                "target_parent_path": target_parent_path,
                "target_path": target_path,
                "target_name": suggested_name,
                "size": int(row.get("size") or 0),
                "sha1": str(row.get("hash_sha1") or ""),
                "category": str(row.get("category") or ""),
                "confidence": str(row.get("confidence") or ""),
            }
        )
    manifest: dict[str, Any] = {
        "version": 1,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scan_root_id": str(scan_root_id),
        "scan_root_path": root_path,
        "organize_dir": organize_dir,
        "operation_count": len(operations),
        "blocked_count": len(blocked),
        "operations": operations,
        "blocked": blocked,
    }
    manifest["confirmation_code"] = confirmation_code(manifest)
    return manifest


def save_manifest(manifest: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.resolve()


class Open115Writer:
    def __init__(
        self,
        access_token: str,
        scan_root_id: str,
        *,
        session: requests.Session | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        request_interval: float = 1.0,
    ) -> None:
        self._access_token = access_token
        self.scan_root_id = str(scan_root_id)
        self._session = session or requests.Session()
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._request_interval = max(0.0, float(request_interval))
        self._last_request_at: float | None = None
        self._directory_cache: dict[tuple[str, ...], str] = {(): self.scan_root_id}

    def _wait_limit(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self._request_interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._monotonic()

    def _request(self, method: str, url: str, *, params=None, data=None) -> dict[str, Any]:
        self._wait_limit()
        try:
            response = self._session.request(
                method,
                url,
                params=params,
                data=data,
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise OperationError("无法连接115 Open官方接口。") from exc
        if response.status_code >= 400:
            raise OperationError(f"115 Open返回HTTP {response.status_code}。")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OperationError("115 Open返回了无法解析的内容。") from exc
        if not isinstance(payload, dict):
            raise OperationError("115 Open返回格式异常。")
        if payload.get("state") is False:
            code = payload.get("code") or payload.get("errno") or "unknown"
            message = payload.get("message") or payload.get("error") or "请求失败"
            raise OperationError(f"115 Open错误 {code}：{message}")
        return payload

    def list_folder(self, folder_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self._request(
                "GET",
                OPEN115_FILES_URL,
                params={"cid": folder_id, "limit": 200, "offset": offset, "show_dir": 1},
            )
            page = payload.get("data") if isinstance(payload.get("data"), list) else []
            result.extend(item for item in page if isinstance(item, dict))
            try:
                total = int(payload.get("count"))
            except (TypeError, ValueError):
                total = len(result)
            if len(result) >= total or len(page) < 200:
                return result
            offset += 200

    @staticmethod
    def _item_id(item: dict[str, Any]) -> str:
        return str(item.get("fid") or item.get("file_id") or "")

    @staticmethod
    def _item_name(item: dict[str, Any]) -> str:
        return str(item.get("fn") or item.get("file_name") or "")

    @staticmethod
    def _is_directory(item: dict[str, Any]) -> bool:
        return str(item.get("fc")) == "0" or str(item.get("file_category")) == "0"

    def find_child(self, parent_id: str, name: str) -> dict[str, Any] | None:
        wanted = name.casefold()
        for item in self.list_folder(parent_id):
            if self._item_name(item).casefold() == wanted:
                return item
        return None

    def mkdir(self, parent_id: str, name: str) -> str:
        payload = self._request(
            "POST", OPEN115_MKDIR_URL, data={"pid": parent_id, "file_name": name}
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        folder_id = str(data.get("file_id") or "")
        if not folder_id:
            raise OperationError("115已返回建目录成功，但没有提供新目录ID。")
        return folder_id

    def ensure_directory(self, parts: list[str]) -> str:
        key: tuple[str, ...] = ()
        parent_id = self.scan_root_id
        for name in parts:
            key = (*key, name)
            cached = self._directory_cache.get(key)
            if cached:
                parent_id = cached
                continue
            existing = self.find_child(parent_id, name)
            if existing:
                if not self._is_directory(existing):
                    raise OperationError(f"目标位置已有同名文件，不能建立目录：{name}")
                child_id = self._item_id(existing)
            else:
                child_id = self.mkdir(parent_id, name)
            if not child_id:
                raise OperationError(f"无法确认目标目录ID：{name}")
            self._directory_cache[key] = child_id
            parent_id = child_id
        return parent_id

    def rename(self, file_id: str, new_name: str) -> None:
        self._request(
            "POST", OPEN115_RENAME_URL, data={"file_id": file_id, "file_name": new_name}
        )

    def move(self, file_id: str, destination_id: str) -> None:
        self._request(
            "POST", OPEN115_MOVE_URL, data={"file_ids": file_id, "to_cid": destination_id}
        )

    def verify_item(self, parent_id: str, file_id: str, expected_name: str) -> bool:
        for item in self.list_folder(parent_id):
            if self._item_id(item) == file_id:
                return self._item_name(item) == expected_name
        return False


@dataclass
class ExecuteResult:
    total: int
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    stopped: bool = False
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "stopped": self.stopped,
            "errors": self.errors,
        }


def load_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise OperationError("操作清单格式或版本不受支持。")
    expected = confirmation_code(payload)
    if payload.get("confirmation_code") != expected:
        raise OperationError("操作清单已被修改，确认码失效。请重新生成。")
    return payload


def _validate_current_plan(conn, operation: dict[str, Any]) -> None:
    row = conn.execute(
        """
        SELECT p.approved, p.file_id, p.original_name, p.suggested_name,
               f.parent_id, f.file_id_source
        FROM organize_plans p JOIN files f ON f.id = p.file_row_id
        WHERE p.id = ?
        """,
        (int(operation["plan_id"]),),
    ).fetchone()
    if not row or not row["approved"]:
        raise OperationError("本地计划已不存在或已取消批准。")
    if (
        str(row["file_id"]) != str(operation["file_id"])
        or str(row["parent_id"]) != str(operation["source_parent_id"])
        or str(row["original_name"]) != str(operation["original_name"])
        or str(row["suggested_name"]) != str(operation["target_name"])
        or row["file_id_source"] != "native"
    ):
        raise OperationError("本地计划在生成清单后发生变化，请重新生成清单。")


def execute_manifest(
    settings: Settings,
    manifest: dict[str, Any],
    confirm: str,
    writer: Open115Writer,
    *,
    continue_on_error: bool = False,
) -> ExecuteResult:
    expected = confirmation_code(manifest)
    if manifest.get("confirmation_code") != expected or confirm != expected:
        raise OperationError("确认码不匹配，未执行任何115写入。")
    if writer.scan_root_id != str(manifest.get("scan_root_id")):
        raise OperationError("写入器根目录与操作清单不一致。")
    operations = manifest.get("operations") or []
    if not isinstance(operations, list):
        raise OperationError("操作清单内容无效。")
    result = ExecuteResult(total=len(operations))
    init_db(settings.db_path)
    with db_session(settings.db_path) as conn:
        for operation in operations:
            operation_id = str(operation.get("operation_id") or uuid.uuid4())
            status = "failed"
            error = ""
            try:
                _validate_current_plan(conn, operation)
                source_items = writer.list_folder(str(operation["source_parent_id"]))
                source = next(
                    (item for item in source_items if writer._item_id(item) == str(operation["file_id"])),
                    None,
                )
                if source is None:
                    raise OperationError("来源目录中找不到该115文件ID，可能已被改动。")
                if writer._item_name(source) != str(operation["original_name"]):
                    raise OperationError("来源文件名已变化，拒绝按旧清单执行。")

                target_parent_id = writer.ensure_directory(list(operation["target_parent_parts"]))
                collision = writer.find_child(target_parent_id, str(operation["target_name"]))
                if collision and writer._item_id(collision) != str(operation["file_id"]):
                    raise OperationError("目标目录已有同名文件，已跳过，未覆盖。")
                if collision and writer._item_id(collision) == str(operation["file_id"]):
                    status = "already_done"
                    result.skipped += 1
                else:
                    if str(operation["target_name"]) != str(operation["original_name"]):
                        writer.rename(str(operation["file_id"]), str(operation["target_name"]))
                    if target_parent_id != str(operation["source_parent_id"]):
                        writer.move(str(operation["file_id"]), target_parent_id)
                    if not writer.verify_item(target_parent_id, str(operation["file_id"]), str(operation["target_name"])):
                        raise OperationError("115返回成功，但最终位置核验失败，请停止并重新扫描。")
                    status = "success"
                    result.succeeded += 1
                set_plan_execute_status(conn, int(operation["plan_id"]), status)
            except Exception as exc:
                error = str(exc)
                result.failed += 1
                result.errors.append({"plan_id": operation.get("plan_id"), "error": error})
                set_plan_execute_status(conn, int(operation["plan_id"]), "failed")
            add_operation_log(
                conn,
                {
                    "operation_id": f"{operation_id}:{uuid.uuid4().hex[:8]}",
                    "file_id": operation.get("file_id"),
                    "operation": "rename_and_move",
                    "old_path": operation.get("original_path"),
                    "new_path": operation.get("target_path"),
                    "old_name": operation.get("original_name"),
                    "new_name": operation.get("target_name"),
                    "time": utc_now(),
                    "status": status,
                    "error": error,
                },
            )
            if error and not continue_on_error:
                result.stopped = True
                break
    return result
