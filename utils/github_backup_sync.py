import base64
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import requests


DEFAULT_REPO = "yaoy2/yao_1-data"
DEFAULT_BRANCH = "main"
# The app code repo is public; dynamic data must never be read from or written to it.
PUBLIC_APP_REPO = "yaoy2/yao_1"
API_ROOT = "https://api.github.com"
_ANY_VERSION = object()
_GH_CLI_TOKEN = "handled-by-gh-cli"


def _normalized_path(repo_path):
    value = str(repo_path).replace("\\", "/")
    if not value.startswith("data/") or any(part in {"", ".", ".."} for part in value.split("/")) or ":" in value:
        raise ValueError("数据路径必须位于 data/ 内，不能使用绝对路径或上级目录。")
    return value


def _content_hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _same_text_content(left, right):
    # read_text uses universal newlines; the remote baseline retains its bytes.
    def normalized(value):
        return value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized(left) == normalized(right)


def _atomic_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                     suffix=".tmp", delete=False) as target:
        target.write(content)
        temporary = Path(target.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _baseline_path(local_path, repo_path, config):
    source = f"{config['repo'].casefold()}\n{config['branch']}\n{_normalized_path(repo_path)}"
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return Path(local_path).parent / ".sync-state" / f"{key}.json"


def get_local_sync_baseline(local_path, repo_path, secrets=None, environ=None):
    config = get_backup_sync_config(secrets, environ)
    path = _baseline_path(local_path, repo_path, config)
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    if (state.get("repo", "").casefold() != config["repo"].casefold()
            or state.get("branch") != config["branch"] or state.get("path") != _normalized_path(repo_path)
            or not state.get("sha") or not isinstance(state.get("content"), str)
            or state.get("content_sha256") != _content_hash(state["content"])):
        raise RuntimeError("本机同步基线损坏，已停止覆盖；请保留本机数据并重新核对云端版本。")
    return state


def remember_local_sync_baseline(local_path, repo_path, content, sha, secrets=None, environ=None):
    if not sha or not isinstance(content, str):
        raise RuntimeError("缺少有效版本或正文，无法记录同步基线。")
    config = get_backup_sync_config(secrets, environ)
    _require_private_repo(config)
    state = {"repo": config["repo"], "branch": config["branch"], "path": _normalized_path(repo_path),
             "sha": sha, "content": content, "content_sha256": _content_hash(content)}
    _atomic_text(_baseline_path(local_path, repo_path, config), json.dumps(state, ensure_ascii=False, indent=2))
    return state


def _session(config, session):
    if session is not None:
        return session
    if config["token"] == _GH_CLI_TOKEN:
        from utils.github_cli import GitHubCliSession
        executable = shutil.which("gh")
        if not executable:
            raise RuntimeError("本机 GitHub CLI 不可用，已停止同步。")
        return GitHubCliSession(executable)
    return requests


def _read_mapping_item(mapping, key):
    if mapping is None:
        return None
    try:
        return mapping[key]
    except Exception:
        return None


def _read_mapping_value(mapping, key):
    value = _read_mapping_item(mapping, key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def get_backup_sync_config(secrets=None, environ=None):
    local_environment = environ is None or environ is os.environ
    environ = os.environ if environ is None else environ
    section = _read_mapping_item(secrets, "github_backup")
    token = (
        _read_mapping_value(section, "token")
        or _read_mapping_value(secrets, "github_backup_token")
        or _read_mapping_value(secrets, "GITHUB_BACKUP_TOKEN")
        or _read_mapping_value(environ, "GITHUB_BACKUP_TOKEN")
    )
    repo = (
        _read_mapping_value(section, "repo")
        or _read_mapping_value(secrets, "github_backup_repo")
        or _read_mapping_value(environ, "GITHUB_BACKUP_REPO")
        or DEFAULT_REPO
    )
    branch = (
        _read_mapping_value(section, "branch")
        or _read_mapping_value(secrets, "github_backup_branch")
        or _read_mapping_value(environ, "GITHUB_BACKUP_BRANCH")
        or DEFAULT_BRANCH
    )
    if not token and local_environment and shutil.which("gh"):
        token = _GH_CLI_TOKEN
    return {"enabled": bool(token), "token": token, "repo": repo, "branch": branch}


def _require_private_repo(config):
    if config["repo"].casefold() == PUBLIC_APP_REPO.casefold():
        raise RuntimeError(f"数据仓库仍指向公开代码仓库 {PUBLIC_APP_REPO}，已停止读写；请把 github_backup_repo 改为私有数据仓库。")


def sync_file_to_github(local_path, repo_path, message, secrets=None, environ=None, session=None,
                        expected_sha=_ANY_VERSION):
    config = get_backup_sync_config(secrets, environ)
    if not config["enabled"]:
        return {"ok": False, "skipped": True, "reason": "missing_token"}
    _require_private_repo(config)

    local_path = Path(local_path)
    if not local_path.exists():
        return {"ok": False, "skipped": True, "reason": "missing_file"}

    session = _session(config, session)
    repo_path = _normalized_path(repo_path)
    content = local_path.read_text(encoding="utf-8")
    from utils.data_sync_validation import MANAGED_FILES, validate_backup
    if repo_path in MANAGED_FILES:
        validate_backup(repo_path, content)
    if expected_sha is _ANY_VERSION:
        baseline = get_local_sync_baseline(local_path, repo_path, secrets, environ)
        if baseline is None:
            raise RuntimeError("本机文件没有同步基线，未上传；请先拉取并核对云端数据。")
        expected_sha = baseline["sha"]
    url = f"{API_ROOT}/repos/{config['repo']}/contents/{repo_path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {config['token']}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    get_response = session.get(url, headers=headers, params={"ref": config["branch"]}, timeout=20)
    sha = None
    if get_response.status_code == 200:
        sha = get_response.json().get("sha")
    elif get_response.status_code != 404:
        raise RuntimeError(f"GitHub 读取备份文件失败：HTTP {get_response.status_code}")

    if expected_sha is not _ANY_VERSION and sha != expected_sha:
        raise RuntimeError("远端数据已更新，本次未覆盖；请刷新最新数据后核对并重新保存。")
    if get_response.status_code == 200 and expected_sha is not _ANY_VERSION and not sha:
        raise RuntimeError("远端未返回有效版本，本次未保存；请刷新后重试。")

    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": config["branch"],
    }
    if sha:
        payload["sha"] = sha

    put_response = session.put(url, headers=headers, json=payload, timeout=20)
    if put_response.status_code == 409:
        raise RuntimeError("远端数据已更新（HTTP 409），本次未覆盖；请刷新最新数据后核对并重新保存。")
    if put_response.status_code not in (200, 201):
        raise RuntimeError(f"GitHub 写入备份文件失败：HTTP {put_response.status_code}")
    new_sha = put_response.json().get("content", {}).get("sha")
    if not new_sha:
        raise RuntimeError("远端写入已响应，但版本尚未确认；本机数据已保留，请刷新核对后重试。")
    remember_local_sync_baseline(local_path, repo_path, content, new_sha, secrets, environ)
    return {"ok": True, "skipped": False, "path": repo_path, "sha": new_sha}


def read_file_from_github(repo_path, secrets=None, environ=None, session=None):
    config = get_backup_sync_config(secrets, environ)
    if not config["enabled"]:
        return {"ok": False, "skipped": True, "reason": "missing_token"}
    _require_private_repo(config)

    session = _session(config, session)
    repo_path = _normalized_path(repo_path)
    url = f"{API_ROOT}/repos/{config['repo']}/contents/{repo_path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {config['token']}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = session.get(url, headers=headers, params={"ref": config["branch"]}, timeout=20)
    if response.status_code == 404:
        return {"ok": False, "skipped": True, "reason": "missing_remote_file"}
    if response.status_code != 200:
        raise RuntimeError(f"GitHub 读取备份文件失败：HTTP {response.status_code}")

    payload = response.json()
    if not payload.get("sha") or payload.get("encoding", "base64") != "base64" or "content" not in payload:
        raise RuntimeError("远端备份没有有效版本或正文，已停止同步。")
    encoded_content = str(payload["content"])
    content = base64.b64decode("".join(encoded_content.split()), validate=True).decode("utf-8")
    return {"ok": True, "skipped": False, "path": repo_path, "content": content,
            "sha": payload.get("sha")}


def download_file_from_github(local_path, repo_path, secrets=None, environ=None, session=None):
    repo_path = _normalized_path(repo_path)
    result = read_file_from_github(repo_path, secrets=secrets, environ=environ, session=session)
    if not result.get("ok"):
        return result

    local_path = Path(local_path)
    content = result["content"]
    from utils.data_sync_validation import MANAGED_FILES, validate_backup
    if repo_path in MANAGED_FILES:
        validate_backup(repo_path, content)
    local_content = local_path.read_text(encoding="utf-8") if local_path.exists() else None
    if local_content is not None and not _same_text_content(local_content, content):
        baseline = get_local_sync_baseline(local_path, repo_path, secrets, environ)
        if baseline is None or not _same_text_content(local_content, baseline["content"]):
            raise RuntimeError("本机文件有未核对的修改，未被拉取覆盖；请先保留并合并本机数据。")
    _atomic_text(local_path, content)
    remember_local_sync_baseline(local_path, repo_path, content, result["sha"], secrets, environ)
    return {"ok": True, "skipped": False, "path": repo_path, "sha": result["sha"]}


def ensure_local_file(local_path, repo_path, secrets=None, environ=None, session=None, refresh=False):
    """Data files are not deployed with the code; fetch one when missing or on explicit refresh."""
    if Path(local_path).exists() and not refresh:
        return {"ok": True, "skipped": True, "reason": "local_exists"}
    return download_file_from_github(local_path, repo_path, secrets=secrets, environ=environ, session=session)


def sync_many_to_github(files, message, secrets=None, environ=None, session=None):
    results = []
    for local_path, repo_path in files:
        results.append(
            sync_file_to_github(
                local_path,
                repo_path,
                message,
                secrets=secrets,
                environ=environ,
                session=session,
            )
        )
    return results
