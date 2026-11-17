"""M34 private cloud snapshots with compare-and-swap and verified read-back."""

import base64
import json
import re

from utils import github_backup_sync as sync
from utils import work_guides as guides


PRIVATE_REPO = "yaoy2/yao_1-data"
BRANCH = "main"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _connection(secrets, environ, session):
    config = sync.get_backup_sync_config(secrets, environ)
    _require(config["enabled"] and config["repo"].casefold() == PRIVATE_REPO.casefold()
             and config["branch"] == BRANCH, "私有同步配置不可用。")
    transport = sync._session(config, session)
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {config['token']}",
               "X-GitHub-Api-Version": "2022-11-28", "Cache-Control": "no-cache, no-store"}
    response = transport.get(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}", headers=headers,
                             timeout=20, allow_redirects=False)
    _require(response.status_code == 200, "私有仓库不可用。")
    metadata = response.json()
    _require(type(metadata) is dict and metadata.get("private") is True
             and str(metadata.get("full_name", "")).casefold() == PRIVATE_REPO.casefold(), "私有仓库未确认。")
    return transport, headers


def _current(transport, headers):
    response = transport.get(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}/contents/{guides.REPO_PATH}",
                             headers=headers, params={"ref": BRANCH}, timeout=20, allow_redirects=False)
    if response.status_code == 404:
        return None, None
    _require(response.status_code == 200, "远端内容不可用。")
    payload = response.json()
    _require(type(payload) is dict and payload.get("encoding") == "base64", "远端格式无效。")
    sha = payload.get("sha")
    _require(type(sha) is str and re.fullmatch(r"[a-f0-9]{40,64}", sha), "远端版本无效。")
    content = payload.get("content")
    _require(type(content) is str and len(content) <= guides.MAX_DOCUMENT_BYTES * 2, "内容超出容量。")
    decoded = base64.b64decode("".join(content.split()), validate=True)
    _require(len(decoded) <= guides.MAX_DOCUMENT_BYTES, "内容超出容量。")
    return guides.validate_document(json.loads(decoded)), sha


def load_document(secrets=None, environ=None, session=None):
    try:
        transport, headers = _connection(secrets, environ, session)
        document, sha = _current(transport, headers)
        return {"ok": True, "document": document if document is not None else guides.empty_document(), "sha": sha}
    except Exception:
        return {"ok": False, "message": "工作指南暂时未读到，请检查私有数据连接后重试。"}


def save_document(document, expected_sha, secrets=None, environ=None, session=None):
    started = False
    try:
        guides.validate_document(document)
        _require(expected_sha is None or type(expected_sha) is str and re.fullmatch(r"[a-f0-9]{40,64}", expected_sha),
                 "缺少有效版本。")
        transport, headers = _connection(secrets, environ, session)
        current, sha = _current(transport, headers)
        if sha != expected_sha:
            return {"ok": False, "conflict": True, "message": "其他设备已更新指南，本次未覆盖。请下载草稿，再刷新核对合并。"}
        guides.check_transition(current, document)
        encoded = guides.serialize(document).encode("utf-8")
        payload = {"message": "data: update work guides", "branch": BRANCH,
                   "content": base64.b64encode(encoded).decode("ascii")}
        if sha is not None:
            payload["sha"] = sha
        started = True
        response = transport.put(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}/contents/{guides.REPO_PATH}",
                                 headers=headers, json=payload, timeout=20, allow_redirects=False)
        if response.status_code in (409, 422):
            return {"ok": False, "conflict": True, "message": "云端版本冲突，保存未确认。请下载草稿，再刷新核对合并。"}
        _require(response.status_code in (200, 201), "保存响应无效。")
        new_sha = response.json().get("content", {}).get("sha")
        verified, verified_sha = _current(transport, headers)
        _require(new_sha and new_sha == verified_sha and verified == document, "保存读回核验失败。")
        return {"ok": True, "document": verified, "sha": verified_sha}
    except Exception:
        message = ("保存结果尚未确认。当前草稿已保留，请先下载，再刷新核对。" if started else
                   "未保存。请核对指南内容和私有数据连接；当前草稿已保留，可下载备份。")
        return {"ok": False, "message": message}
