"""Private M30 snapshots with version checks and verified read-back."""

import base64
import json
import re

from utils import github_backup_sync as sync
from utils.title_review import CASES_PATH, RULES_PATH, MAX_DOCUMENT_BYTES, validate_document


PRIVATE_REPO = "yaoy2/yao_1-data"
BRANCH = "main"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _connection(secrets, environ, session):
    config = sync.get_backup_sync_config(secrets, environ)
    _require(config["enabled"], "尚未配置私有数据同步，评审资料未读取。")
    _require(config["repo"].casefold() == PRIVATE_REPO.casefold() and config["branch"] == BRANCH,
             "评审资料必须使用工具箱指定的私有数据仓库，已停止读写。")
    transport = sync._session(config, session)
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {config['token']}",
               "X-GitHub-Api-Version": "2022-11-28", "Cache-Control": "no-cache, no-store"}
    response = transport.get(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}", headers=headers, timeout=20, allow_redirects=False)
    _require(response.status_code == 200, "暂时无法核对私有数据仓库，已停止读写。")
    metadata = response.json()
    _require(type(metadata) is dict and metadata.get("private") is True
             and str(metadata.get("full_name", "")).casefold() == PRIVATE_REPO.casefold(),
             "未能确认数据仓库为私有，已停止读写。")
    return transport, headers


def _current(path, transport, headers):
    _require(path in {RULES_PATH, CASES_PATH}, "不支持的评审资料路径。")
    response = transport.get(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}/contents/{path}",
                             headers=headers, params={"ref": BRANCH}, timeout=20, allow_redirects=False)
    if response.status_code == 404:
        return None, None
    _require(response.status_code == 200, "暂时无法读取评审资料，当前编辑内容保留。")
    payload = response.json()
    _require(type(payload) is dict and payload.get("encoding") == "base64", "远端评审资料格式无效，未覆盖。")
    sha = payload.get("sha")
    _require(type(sha) is str and bool(re.fullmatch(r"[a-f0-9]{40,64}", sha)), "远端未返回有效版本，未覆盖。")
    content = payload.get("content")
    _require(type(content) is str and len(content) <= MAX_DOCUMENT_BYTES * 2, "远端评审资料超出读取容量。")
    decoded = base64.b64decode("".join(content.split()), validate=True)
    _require(len(decoded) <= MAX_DOCUMENT_BYTES, "远端评审资料超出读取容量。")
    document = json.loads(decoded)
    return validate_document(document, path), sha


def load_document(path, secrets=None, environ=None, session=None):
    try:
        transport, headers = _connection(secrets, environ, session)
        document, sha = _current(path, transport, headers)
        return {"ok": True, "document": document, "sha": sha}
    except Exception:
        # Do not expose transport errors, credentials, or private bodies in UI.
        return {"ok": False, "message": "评审资料未成功读取，请检查私有数据同步后重试；当前编辑内容保留。"}


def save_document(path, document, expected_sha, secrets=None, environ=None, session=None):
    started = False
    try:
        validate_document(document, path)
        _require(expected_sha is None or type(expected_sha) is str and bool(re.fullmatch(r"[a-f0-9]{40,64}", expected_sha)),
                 "保存缺少有效版本。")
        transport, headers = _connection(secrets, environ, session)
        current, sha = _current(path, transport, headers)
        if sha != expected_sha:
            return {"ok": False, "conflict": True, "message": "其他设备已更新记录，本次未覆盖。请下载当前草稿，再刷新合并。"}
        if path == CASES_PATH and current is not None:
            old_ids = {case["id"] for case in current["cases"]}
            _require(old_ids <= {case["id"] for case in document["cases"]}, "本次保存不能移除已有收件记录。")
            _require(document["revision"] > current["revision"], "记录版本未递增，未覆盖。")
        encoded = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
        _require(len(encoded) <= MAX_DOCUMENT_BYTES, "资料超过账本容量，请下载草稿并分批整理。")
        payload = {"message": "data: update title review " + ("rules" if path == RULES_PATH else "records"),
                   "branch": BRANCH, "content": base64.b64encode(encoded).decode("ascii")}
        if sha is not None:
            payload["sha"] = sha
        started = True
        response = transport.put(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}/contents/{path}",
                                 headers=headers, json=payload, timeout=20, allow_redirects=False)
        if response.status_code in {409, 422}:
            return {"ok": False, "conflict": True, "message": "云端版本冲突，本次保存未确认。请下载草稿，再刷新合并。"}
        _require(response.status_code in {200, 201}, "保存尚未确认。")
        new_sha = response.json().get("content", {}).get("sha")
        verified, verified_sha = _current(path, transport, headers)
        _require(new_sha and verified_sha == new_sha and verified == document, "保存后的读回核验未通过。")
        return {"ok": True, "document": verified, "sha": verified_sha}
    except Exception:
        message = ("保存结果尚未确认；当前草稿保留，请下载后刷新核对，勿重复覆盖。" if started
                   else "未保存：请核对资料结构、记录版本及私有同步配置。当前草稿保留，可下载备份。")
        return {"ok": False, "message": message}
