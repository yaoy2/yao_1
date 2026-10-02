from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

import requests

from .config import Settings, normalize_path
from .safety import WriteDisabledError, assert_under_allowed_root, assert_write_blocked


NATIVE_ID_KEYS = ("id", "file_id", "fileId", "fid", "Fid", "FID")


class OpenListError(RuntimeError):
    pass


def to_api_path(logical_path: str, user_base_path: str) -> str:
    logical = normalize_path(logical_path)
    base = normalize_path(user_base_path or "")
    if not base or base == "/":
        return logical
    if logical == base:
        return "/"
    if logical.startswith(base + "/"):
        return normalize_path(logical[len(base):] or "/")
    return logical


class OpenListClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.token = ""
        self.user_base_path = ""
        self._user_loaded = False

    def _url(self, path: str) -> str:
        return urljoin(self.settings.openlist_base_url.rstrip("/") + "/", path.lstrip("/"))

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = self.token
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                self._url(path),
                json=payload,
                headers=self._headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise OpenListError(f"无法连接 OpenList：{exc}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise OpenListError(f"OpenList 返回了无法解析的内容，HTTP {response.status_code}") from exc
        if response.status_code >= 400:
            raise OpenListError(f"OpenList HTTP {response.status_code}：{data}")
        if isinstance(data, dict) and data.get("code") not in (None, 200):
            raise OpenListError(data.get("message") or f"OpenList 错误：{data}")
        return data

    def login(self) -> str:
        data = self._request(
            "POST",
            "/api/auth/login",
            {
                "username": self.settings.openlist_username,
                "password": self.settings.openlist_password,
            },
        )
        token = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}) .get("token")
        if not token:
            raise OpenListError("OpenList 登录成功但没有返回 token。")
        self.token = token
        self._user_loaded = False
        return token

    def ensure_user_context(self) -> None:
        if self._user_loaded:
            return
        if not self.token:
            self.login()
        me_resp = self._request("GET", "/api/me")
        me = me_resp.get("data") or {}
        self.user_base_path = me.get("base_path") or ""
        self._user_loaded = True

    def ping(self) -> dict[str, Any]:
        reachable = False
        try:
            response = self.session.get(self._url("/ping"), timeout=10)
            reachable = response.status_code < 500
        except requests.RequestException as exc:
            return {
                "reachable": False,
                "logged_in": False,
                "base_url": self.settings.openlist_base_url,
                "username": self.settings.openlist_username,
                "base_path": "",
                "permission": None,
                "error": f"无法连接 OpenList：{exc}",
            }
        me: dict[str, Any] = {}
        error = ""
        logged_in = False
        try:
            self.ensure_user_context()
            me_resp = self._request("GET", "/api/me")
            me = me_resp.get("data") or {}
            logged_in = True
        except OpenListError as exc:
            error = str(exc)
        return {
            "reachable": reachable,
            "base_url": self.settings.openlist_base_url,
            "logged_in": logged_in,
            "username": me.get("username") or self.settings.openlist_username,
            "base_path": me.get("base_path") or "",
            "permission": me.get("permission"),
            "error": error,
        }

    def list_dir(self, path: str, page: int = 1, per_page: int = 200, refresh: bool = False) -> dict[str, Any]:
        safe_path = assert_under_allowed_root(path, self.settings)
        self.ensure_user_context()
        data = self._request(
            "POST",
            "/api/fs/list",
            {
                "path": to_api_path(safe_path, self.user_base_path),
                "page": page,
                "per_page": per_page,
                "refresh": refresh,
            },
        )
        return data.get("data") or {}

    def list_all(
        self,
        path: str,
        per_page: int = 200,
        refresh: bool = False,
        max_directory_entries: int = 10_000,
    ) -> dict[str, Any]:
        page_size = max(1, int(per_page))
        entry_limit = max(1, int(max_directory_entries))
        content: list[dict[str, Any]] = []
        expected_total: int | None = None
        seen_pages: set[str] = set()
        seen_native_ids: set[str] = set()
        first_listing: dict[str, Any] = {}
        page_number = 1
        while True:
            listing = self.list_dir(path, page=page_number, per_page=page_size, refresh=refresh)
            if not isinstance(listing, dict):
                raise OpenListError("OpenList 目录列表格式异常，拒绝保存不完整扫描。")
            page = listing.get("content")
            if "content" in listing and page is None and listing.get("total") in (0, "0"):
                page = []
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise OpenListError("OpenList 目录列表格式异常，拒绝保存不完整扫描。")
            if page_number == 1:
                first_listing = listing
            total = listing.get("total")
            if total is not None:
                if isinstance(total, bool) or not (
                    isinstance(total, int)
                    or isinstance(total, str) and total.strip().isdigit()
                ):
                    raise OpenListError("OpenList 目录总数格式异常，请重新扫描。")
                count = int(total)
                if count < 0:
                    raise OpenListError("OpenList 目录总数格式异常，请重新扫描。")
                if expected_total is not None and count != expected_total:
                    raise OpenListError("分页期间目录数量发生变化，请重新扫描。")
                expected_total = count
            if page:
                page_key = json.dumps(page, sort_keys=True, ensure_ascii=False)
                if page_key in seen_pages:
                    raise OpenListError("OpenList 重复返回同一页，拒绝保存不完整扫描。")
                seen_pages.add(page_key)
                page_native_ids = {extract_native_id(item) for item in page} - {""}
                if seen_native_ids & page_native_ids:
                    raise OpenListError("OpenList 分页之间返回重复文件 ID，拒绝保存不完整扫描。")
                seen_native_ids.update(page_native_ids)
            content.extend(page)
            if len(content) > entry_limit:
                raise OpenListError(
                    f"单层目录超过安全上限 {entry_limit}，请改用更小的扫描根目录。"
                )
            if expected_total is not None:
                if len(content) > expected_total:
                    raise OpenListError("目录列表与返回总数不一致，请重新扫描。")
                if len(content) == expected_total:
                    break
            if len(page) < page_size:
                if expected_total is not None:
                    raise OpenListError("目录分页提前结束，拒绝保存不完整扫描。")
                break
            page_number += 1
        return {**first_listing, "content": content, "total": len(content)}

    def get_item(self, path: str) -> dict[str, Any]:
        safe_path = assert_under_allowed_root(path, self.settings)
        self.ensure_user_context()
        data = self._request(
            "POST",
            "/api/fs/get",
            {"path": to_api_path(safe_path, self.user_base_path)},
        )
        return data.get("data") or {}

    def mkdir(self, *args: Any, **kwargs: Any) -> None:
        assert_write_blocked("mkdir", self.settings)

    def move(self, *args: Any, **kwargs: Any) -> None:
        assert_write_blocked("move", self.settings)

    def rename(self, *args: Any, **kwargs: Any) -> None:
        assert_write_blocked("rename", self.settings)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise WriteDisabledError("禁止删除 115 文件。即使以后需要删除，也必须单独设计。")


def join_child_path(parent: str, name: str) -> str:
    parent = normalize_path(parent)
    if parent == "/":
        return normalize_path("/" + name)
    return normalize_path(parent + "/" + name)


def extract_native_id(item: dict[str, Any]) -> str:
    for key in NATIVE_ID_KEYS:
        value = item.get(key)
        if value not in (None, "", 0, "0"):
            text = str(value).strip()
            if text:
                return text
    extra = item.get("hash_info") if isinstance(item.get("hash_info"), dict) else {}
    for key in NATIVE_ID_KEYS:
        value = extra.get(key)
        if value not in (None, "", 0, "0"):
            text = str(value).strip()
            if text:
                return text
    return ""


def extract_sha1(item: dict[str, Any]) -> str:
    hash_info = item.get("hash_info")
    if isinstance(hash_info, dict):
        for key in ("sha1", "SHA1", "sha-1"):
            if hash_info.get(key):
                return str(hash_info.get(key))
    hashinfo = str(item.get("hashinfo") or item.get("hash_info") or "")
    if "sha1" in hashinfo.lower():
        return hashinfo
    return ""


def extract_media_fields(item: dict[str, Any]) -> dict[str, Any]:
    extra = item if isinstance(item, dict) else {}
    duration = extra.get("duration") or extra.get("play_long") or extra.get("video_duration")
    width = extra.get("width") or extra.get("video_width")
    height = extra.get("height") or extra.get("video_height")
    media_type = extra.get("media_type") or extra.get("type")
    try:
        duration_value = float(duration) if duration not in (None, "") else None
    except (TypeError, ValueError):
        duration_value = None
    try:
        width_value = int(width) if width not in (None, "") else None
    except (TypeError, ValueError):
        width_value = None
    try:
        height_value = int(height) if height not in (None, "") else None
    except (TypeError, ValueError):
        height_value = None
    return {
        "duration": duration_value,
        "width": width_value,
        "height": height_value,
        "media_type": str(media_type) if media_type not in (None, "") else None,
    }
