from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

import requests


OPEN115_FILES_URL = "https://proapi.115.com/open/ufile/files"
OPEN115_SEARCH_URL = "https://proapi.115.com/open/ufile/search"
DEFAULT_OPENLIST_DATA_DIR = Path("E:/OpenList/data")


class ListingDiagnosticError(RuntimeError):
    pass


def _openlist_db_uri(db_path: Path) -> str:
    try:
        return db_path.resolve(strict=True).as_uri() + "?mode=ro"
    except FileNotFoundError as exc:
        raise ListingDiagnosticError(f"找不到 OpenList 数据库：{db_path}") from exc


def load_open115_storage(
    data_dir: Path,
    mount_path: str,
) -> tuple[str, str]:
    """Read the current 115 Open token and root ID without exposing either."""
    db_path = data_dir / "data.db"
    try:
        with closing(sqlite3.connect(_openlist_db_uri(db_path), uri=True)) as conn:
            row = conn.execute(
                "SELECT addition FROM x_storages WHERE mount_path = ? AND driver = ?",
                (mount_path, "115 Open"),
            ).fetchone()
    except sqlite3.Error as exc:
        raise ListingDiagnosticError("无法只读打开 OpenList 存储配置。") from exc
    if not row:
        raise ListingDiagnosticError(f"OpenList 中没有找到挂载点：{mount_path}")
    try:
        addition = json.loads(row[0])
    except (TypeError, json.JSONDecodeError) as exc:
        raise ListingDiagnosticError("OpenList 的 115 Open 配置无法解析。") from exc
    access_token = str(addition.get("access_token") or "").strip()
    root_folder_id = str(addition.get("root_folder_id") or "").strip()
    if not access_token:
        raise ListingDiagnosticError("115 Open 当前没有可用的 access token。")
    if not root_folder_id:
        raise ListingDiagnosticError("115 Open 当前没有根文件夹 ID。")
    return access_token, root_folder_id


class Open115ListingInspector:
    def __init__(
        self,
        access_token: str,
        session: requests.Session | None = None,
    ) -> None:
        self._access_token = access_token
        self._session = session or requests.Session()

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ListingDiagnosticError("无法连接 115 Open 官方接口。") from exc
        if response.status_code >= 400:
            raise ListingDiagnosticError(f"115 Open 返回 HTTP {response.status_code}。")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ListingDiagnosticError("115 Open 返回了无法解析的内容。") from exc
        if not isinstance(payload, dict):
            raise ListingDiagnosticError("115 Open 返回格式异常。")
        if payload.get("state") is False:
            code = payload.get("code") or payload.get("errno") or "unknown"
            message = payload.get("message") or payload.get("error") or "请求失败"
            raise ListingDiagnosticError(f"115 Open 错误 {code}：{message}")
        return payload

    def list_summary(self, folder_id: str, limit: int = 20) -> dict[str, Any]:
        payload = self._get(
            OPEN115_FILES_URL,
            {
                "cid": folder_id,
                "limit": limit,
                "offset": 0,
                "show_dir": 1,
            },
        )
        items = payload.get("data") if isinstance(payload.get("data"), list) else []
        return {
            "state": payload.get("state"),
            "count": payload.get("count"),
            "sample_count": len(items),
            "empty": len(items) == 0,
        }

    def hidden_sample_summary(
        self,
        folder_id: str,
        search_value: str = ".",
        limit: int = 50,
    ) -> dict[str, Any]:
        payload = self._get(
            OPEN115_SEARCH_URL,
            {
                "search_value": search_value,
                "cid": folder_id,
                "limit": limit,
                "offset": 0,
                "fc": 1,
            },
        )
        items = payload.get("data") if isinstance(payload.get("data"), list) else []
        private_count = sum(1 for item in items if item.get("is_private") == 1)
        normal_count = sum(1 for item in items if item.get("is_private") == 0)
        return {
            "search_value": search_value,
            "matching_folder_count": payload.get("count"),
            "sample_count": len(items),
            "private_count": private_count,
            "normal_count": normal_count,
        }


def diagnose_open115_listing(
    data_dir: Path,
    mount_path: str,
    *,
    session: requests.Session | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    access_token, root_folder_id = load_open115_storage(data_dir, mount_path)
    inspector = Open115ListingInspector(access_token, session=session)
    listing = inspector.list_summary(root_folder_id)
    hidden_sample: dict[str, Any] | None = None
    diagnosis = "listing_available"
    if listing["empty"]:
        # The official API is rate limited. Keep the diagnostic calls serialized.
        sleep_fn(1.1)
        hidden_sample = inspector.hidden_sample_summary(root_folder_id)
        if hidden_sample["private_count"] > 0:
            diagnosis = "hidden_items_excluded_from_listing"
        else:
            diagnosis = "empty_listing_without_hidden_sample"
    return {
        "mount_path": mount_path,
        "root_folder_id": root_folder_id,
        "listing": listing,
        "hidden_folder_sample": hidden_sample,
        "diagnosis": diagnosis,
        "read_only": True,
        "sensitive_values_redacted": True,
    }
