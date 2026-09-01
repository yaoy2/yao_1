from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

from .config import Settings, normalize_path
from .safety import WriteDisabledError, assert_under_allowed_root, assert_write_blocked


NATIVE_ID_KEYS = ("id", "file_id", "fileId", "fid", "Fid", "FID")


class OpenListError(RuntimeError):
    pass


class OpenListClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.token = ""

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
        return token

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
            if not self.token:
                self.login()
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
        data = self._request(
            "POST",
            "/api/fs/list",
            {
                "path": safe_path,
                "page": page,
                "per_page": per_page,
                "refresh": refresh,
            },
        )
        return data.get("data") or {}

    def get_item(self, path: str) -> dict[str, Any]:
        safe_path = assert_under_allowed_root(path, self.settings)
        data = self._request("POST", "/api/fs/get", {"path": safe_path})
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
