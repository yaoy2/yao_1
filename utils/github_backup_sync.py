import base64
import os
from pathlib import Path

import requests


DEFAULT_REPO = "yaoy2/yao_1"
DEFAULT_BRANCH = "main"
API_ROOT = "https://api.github.com"


def _read_mapping_value(mapping, key):
    if mapping is None:
        return None
    try:
        value = mapping[key]
    except Exception:
        return None
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def get_backup_sync_config(secrets=None, environ=None):
    environ = os.environ if environ is None else environ
    section = _read_mapping_value(secrets, "github_backup")
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
    return {"enabled": bool(token), "token": token, "repo": repo, "branch": branch}


def sync_file_to_github(local_path, repo_path, message, secrets=None, environ=None, session=None):
    config = get_backup_sync_config(secrets, environ)
    if not config["enabled"]:
        return {"ok": False, "skipped": True, "reason": "missing_token"}

    local_path = Path(local_path)
    if not local_path.exists():
        return {"ok": False, "skipped": True, "reason": "missing_file"}

    session = requests if session is None else session
    repo_path = str(repo_path).replace("\\", "/")
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

    payload = {
        "message": message,
        "content": base64.b64encode(local_path.read_bytes()).decode("ascii"),
        "branch": config["branch"],
    }
    if sha:
        payload["sha"] = sha

    put_response = session.put(url, headers=headers, json=payload, timeout=20)
    if put_response.status_code not in (200, 201):
        raise RuntimeError(f"GitHub 写入备份文件失败：HTTP {put_response.status_code}")
    return {"ok": True, "skipped": False, "path": repo_path}


def download_file_from_github(local_path, repo_path, secrets=None, environ=None, session=None):
    config = get_backup_sync_config(secrets, environ)
    if not config["enabled"]:
        return {"ok": False, "skipped": True, "reason": "missing_token"}

    session = requests if session is None else session
    repo_path = str(repo_path).replace("\\", "/")
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
        raise RuntimeError(f"GitHub 璇诲彇澶囦唤鏂囦欢澶辫触锛欻TTP {response.status_code}")

    encoded_content = str(response.json().get("content", ""))
    content = base64.b64decode("".join(encoded_content.split()))
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content)
    return {"ok": True, "skipped": False, "path": repo_path}


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
