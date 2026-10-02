from __future__ import annotations

import json
import time
from typing import Any, Callable

import requests

from .config import normalize_path
from .openlist_client import join_child_path


OPEN115_FOLDER_INFO_URL = "https://proapi.115.com/open/folder/get_info"
OPEN115_FILES_URL = "https://proapi.115.com/open/ufile/files"


class Open115ReadOnlyError(RuntimeError):
    pass


class Open115ReadOnlyProvider:
    """Expose the official 115 Open list API in the scanner's read-only shape."""

    def __init__(
        self,
        access_token: str,
        mounted_root_id: str,
        scan_root_id: str,
        logical_root: str,
        *,
        session: requests.Session | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        request_interval: float = 1.0,
        page_size: int = 200,
        max_directory_entries: int = 10_000,
    ) -> None:
        self._access_token = access_token
        self.mounted_root_id = str(mounted_root_id)
        self.scan_root_id = str(scan_root_id)
        self.logical_root = normalize_path(logical_root)
        self._session = session or requests.Session()
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._request_interval = max(0.0, float(request_interval))
        self._last_request_at: float | None = None
        self.page_size = min(max(1, int(page_size)), 1150)
        self.max_directory_entries = max(1, int(max_directory_entries))
        self._path_to_id = {self.logical_root: self.scan_root_id}

    def _wait_limit(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self._request_interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._monotonic()

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        self._wait_limit()
        try:
            response = self._session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise Open115ReadOnlyError("无法连接 115 Open 官方接口。") from exc
        if response.status_code >= 400:
            raise Open115ReadOnlyError(f"115 Open 返回 HTTP {response.status_code}。")
        try:
            payload = response.json()
        except ValueError as exc:
            raise Open115ReadOnlyError("115 Open 返回了无法解析的内容。") from exc
        if not isinstance(payload, dict):
            raise Open115ReadOnlyError("115 Open 返回格式异常。")
        if payload.get("state") is False:
            code = payload.get("code") or payload.get("errno") or "unknown"
            message = payload.get("message") or payload.get("error") or "请求失败"
            raise Open115ReadOnlyError(f"115 Open 错误 {code}：{message}")
        return payload

    def validate_scan_root(self) -> None:
        if self.scan_root_id == self.mounted_root_id:
            return
        payload = self._get(OPEN115_FOLDER_INFO_URL, {"file_id": self.scan_root_id})
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        ancestor_ids = {
            str(item.get("file_id") or "")
            for item in (data.get("paths") or [])
            if isinstance(item, dict)
        }
        if self.mounted_root_id not in ancestor_ids:
            raise Open115ReadOnlyError(
                "指定的扫描根目录不在 OpenList 当前挂载的允许范围内。"
            )

    @staticmethod
    def _count(payload: dict[str, Any]) -> int | None:
        value = payload.get("count")
        if value in (None, ""):
            return None
        try:
            count = int(value)
        except (TypeError, ValueError):
            return None
        return count if count >= 0 else None

    @staticmethod
    def _convert_item(item: dict[str, Any]) -> dict[str, Any]:
        is_directory = str(item.get("fc")) == "0"
        return {
            "name": str(item.get("fn") or ""),
            "file_id": str(item.get("fid") or ""),
            "parent_id": str(item.get("pid") or ""),
            "is_dir": is_directory,
            "size": int(item.get("fs") or 0),
            "created": item.get("uppt"),
            "modified": item.get("upt"),
            "hash_info": {"sha1": str(item.get("sha1") or "")},
            "play_long": item.get("play_long"),
            "media_type": item.get("ico"),
        }

    def list_dir(self, logical_path: str) -> dict[str, Any]:
        current = normalize_path(logical_path)
        folder_id = self._path_to_id.get(current)
        if not folder_id:
            raise Open115ReadOnlyError(f"扫描路径没有可信目录 ID：{current}")

        raw_items: list[dict[str, Any]] = []
        offset = 0
        expected_count: int | None = None
        seen_pages: set[str] = set()
        seen_ids: set[str] = set()
        while True:
            payload = self._get(
                OPEN115_FILES_URL,
                {
                    "cid": folder_id,
                    "limit": self.page_size,
                    "offset": offset,
                    "show_dir": 1,
                },
            )
            page = payload.get("data")
            if page is None and "data" in payload and payload.get("count") in (0, "0"):
                page = []
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise Open115ReadOnlyError("115 Open目录列表格式异常，拒绝保存不完整扫描。")
            count = self._count(payload)
            if count is not None:
                if expected_count is not None and count != expected_count:
                    raise Open115ReadOnlyError("分页期间目录数量发生变化，请重新扫描。")
                expected_count = count
            if page:
                page_ids = {str(item["fid"]) for item in page if item.get("fid")}
                if seen_ids.intersection(page_ids):
                    raise Open115ReadOnlyError("115 Open分页出现重复文件ID，请重新扫描。")
                seen_ids.update(page_ids)
                page_key = json.dumps(page, sort_keys=True, ensure_ascii=False)
                if page_key in seen_pages:
                    raise Open115ReadOnlyError("115 Open重复返回同一页，拒绝保存不完整扫描。")
                seen_pages.add(page_key)
            raw_items.extend(page)
            if len(raw_items) > self.max_directory_entries:
                raise Open115ReadOnlyError(
                    f"单层目录超过安全上限 {self.max_directory_entries}，请改用更小的扫描根目录。"
                )
            if expected_count is not None:
                if len(raw_items) > expected_count:
                    raise Open115ReadOnlyError("目录列表与返回总数不一致，请重新扫描。")
                if len(raw_items) == expected_count:
                    break
            if len(page) < self.page_size:
                if expected_count is not None:
                    raise Open115ReadOnlyError("目录分页提前结束，拒绝保存不完整扫描。")
                break
            offset += self.page_size

        content = [self._convert_item(item) for item in raw_items]
        for item in content:
            if item["is_dir"] and item["file_id"]:
                self._path_to_id[join_child_path(current, item["name"])] = item["file_id"]
        return {
            "content": content,
            "total": expected_count if expected_count is not None else len(content),
            "source": "115_open_official",
        }
