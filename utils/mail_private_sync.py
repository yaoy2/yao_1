"""Read private mail snapshots and save user decisions with optimistic locking.

This module never downloads original mail or attachments. ``dashboard.json`` is
an index in a separately verified private repository, not the app's public repo.
``MAIL_WORKBENCH_SNAPSHOT`` enables an explicit local, read-only preview.
"""

import base64
import copy
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from utils import github_backup_sync
from utils.mail_action_status import ALL_STATUSES, STATUS_LABELS


DEFAULT_REPO = "yaoy2/mail-workbench-data"
DEFAULT_BRANCH = "main"
SNAPSHOT_PATH = "dashboard.json"
API_ROOT = "https://api.github.com"
ALLOWED_STATUSES = ALL_STATUSES
_PUBLIC_APP_REPO = "yaoy2/yao_1"


class MailSyncError(RuntimeError):
    """A safe, user-facing error; ``code`` is stable for page handling."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _value(mapping, key):
    try:
        return mapping[key] if mapping is not None else None
    except Exception:
        return None


def _text(mapping, key):
    value = _value(mapping, key)
    return value.strip() or None if isinstance(value, str) else None


def _config(secrets, environ):
    section = _value(secrets, "mail_workbench")
    token = _text(section, "token") or _text(environ, "MAIL_WORKBENCH_TOKEN")
    if not token:
        # Reuse only the credential. The legacy repo/branch defaults are never
        # used here. Read its nested token directly for compatibility with the
        # old helper's handling of mappings.
        token = _text(_value(secrets, "github_backup"), "token")
        if not token:
            try:
                token = github_backup_sync.get_backup_sync_config(secrets, environ).get("token")
            except Exception:
                raise MailSyncError("invalid_config", "邮件工作台凭据配置无法读取。") from None
    repo = _text(section, "repo") or _text(environ, "MAIL_WORKBENCH_REPO") or DEFAULT_REPO
    branch = _text(section, "branch") or _text(environ, "MAIL_WORKBENCH_BRANCH") or DEFAULT_BRANCH
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise MailSyncError("invalid_config", "邮件工作台仓库须采用 owner/repository 格式。")
    if repo.casefold() == _PUBLIC_APP_REPO.casefold():
        raise MailSyncError("public_repo", "邮件数据不得使用应用的公开代码仓库，请配置独立私有仓库。")
    if not isinstance(token, str) or not token.strip():
        raise MailSyncError("missing_token", "尚未配置邮件工作台的私有仓库访问凭据。")
    if any(ord(char) < 32 or ord(char) == 127 for char in token + branch):
        raise MailSyncError("invalid_config", "邮件工作台配置包含无效字符。")
    return {"repo": repo, "branch": branch, "token": token.strip()}


def _headers(config):
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {config['token']}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request(session, method, url, config, **kwargs):
    try:
        # A redirect must not turn the verified repository into another target.
        return getattr(session, method)(
            url, headers=_headers(config), timeout=20, allow_redirects=False, **kwargs
        )
    except Exception:
        # Request errors may contain credentials, URLs or response text. Never
        # attach the original exception to a message displayed by Streamlit.
        raise MailSyncError("network_error", "连接私有邮件仓库失败，请稍后重试。") from None


def _check_status(response, accepted, stage):
    status = response.status_code
    if status in accepted:
        return
    if status == 401:
        raise MailSyncError("unauthorized", "邮件仓库鉴权失败，请检查访问凭据是否有效。")
    if status == 403:
        raise MailSyncError("forbidden", "当前凭据无权完成邮件仓库操作，或访问受到限制。")
    if status == 404:
        if stage == "repository":
            raise MailSyncError("repo_not_found", "邮件私有仓库不存在，或当前凭据没有访问权限。")
        raise MailSyncError("snapshot_not_found", "私有仓库中尚无邮件工作台快照，或分支不可访问。")
    if status == 409:
        raise MailSyncError("conflict", "邮件数据已更新，未覆盖远端；请刷新后核对并重新保存。")
    raise MailSyncError("remote_error", "邮件仓库请求未成功，当前操作未获确认，请刷新检查。")


def _response_json(response):
    try:
        value = response.json()
    except Exception:
        raise MailSyncError("invalid_response", "邮件仓库返回了无法识别的数据。") from None
    if not isinstance(value, dict):
        raise MailSyncError("invalid_response", "邮件仓库返回的数据结构不正确。")
    return value


def _verify_private(config, session):
    response = _request(session, "get", f"{API_ROOT}/repos/{config['repo']}", config)
    _check_status(response, {200}, "repository")
    if _response_json(response).get("private") is not True:
        raise MailSyncError("public_repo", "无法确认目标仓库为私有仓库，已停止读取和写入邮件数据。")


def _snapshot_timezone(snapshot):
    name = snapshot.get("timezone")
    if not isinstance(name, str) or not name or name != name.strip():
        raise MailSyncError("invalid_snapshot", "快照必须指定有效的 IANA 时区，例如 Asia/Shanghai。")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise MailSyncError("invalid_snapshot", "快照时区无法识别，请使用 IANA 时区名称。") from None


def _check_timestamp(value, allow_date=False):
    if value in (None, ""):
        return
    if not isinstance(value, str):
        raise MailSyncError("invalid_snapshot", "快照时间必须为 ISO 8601 文本。")
    try:
        if allow_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date.fromisoformat(value)
            return
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (ValueError, OverflowError):
        raise MailSyncError("invalid_snapshot", "快照中的具体时刻必须包含时区；截止日期可仅保留日期。") from None


def _validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 1:
        raise MailSyncError("invalid_snapshot", "邮件快照版本不受支持，需要 schema_version=1。")
    if not isinstance(snapshot.get("account"), str) or not snapshot["account"].strip():
        raise MailSyncError("invalid_snapshot", "邮件快照缺少所属账号。")
    _snapshot_timezone(snapshot)
    if not snapshot.get("updated_at"):
        raise MailSyncError("invalid_snapshot", "邮件快照缺少更新时间。")
    _check_timestamp(snapshot["updated_at"])
    coverage = snapshot.get("coverage")
    if not isinstance(coverage, dict):
        raise MailSyncError("invalid_snapshot", "邮件快照缺少覆盖范围说明。")
    for key in ("since", "through"):
        _check_timestamp(coverage.get(key), allow_date=True)
    for name in ("messages", "actions", "runs", "reports"):
        if not isinstance(snapshot.get(name), list) or any(not isinstance(item, dict) for item in snapshot[name]):
            raise MailSyncError("invalid_snapshot", "邮件快照的邮件、待办、运行及报告必须为记录列表。")
    message_ids = set()
    for message in snapshot["messages"]:
        message_id = message.get("id")
        if not isinstance(message_id, str) or not message_id.strip() or message_id in message_ids:
            raise MailSyncError("invalid_snapshot", "邮件缺少唯一标识，或存在重复标识。")
        message_ids.add(message_id)
        _check_timestamp(message.get("received_at"))
        if "triage_status" in message or "triage_updated_at" in message:
            if (not isinstance(message.get("triage_status"), str)
                    or message["triage_status"] not in ALLOWED_STATUSES
                    or not message.get("triage_updated_at")):
                raise MailSyncError("invalid_snapshot", "邮件判断须包含有效状态及判断时间。")
            _check_timestamp(message["triage_updated_at"])
    seen_ids = set()
    for action in snapshot["actions"]:
        action_id = action.get("id")
        if not isinstance(action_id, str) or not action_id.strip() or action_id in seen_ids:
            raise MailSyncError("invalid_snapshot", "邮件待办缺少唯一标识，或存在重复标识。")
        seen_ids.add(action_id)
        if not isinstance(action.get("status"), str) or action["status"] not in ALLOWED_STATUSES:
            raise MailSyncError("invalid_snapshot", "邮件待办含有不支持的状态。")
        _check_timestamp(action.get("due_at"), allow_date=True)
        _check_timestamp(action.get("updated_at"))
        _check_timestamp(action.get("completed_at"))
    for report in snapshot["reports"]:
        if "action_ids" not in report:
            continue
        identifiers = report["action_ids"]
        if (not isinstance(identifiers, list)
                or any(not isinstance(identifier, str) or not identifier.strip() for identifier in identifiers)
                or len(set(identifiers)) != len(identifiers)):
            raise MailSyncError("invalid_snapshot", "邮件报告中的待办标识必须为不重复的标识列表。")
    return snapshot


def _decode_snapshot(raw):
    try:
        snapshot = json.loads(raw)
    except (ValueError, UnicodeError, TypeError):
        raise MailSyncError("invalid_snapshot", "邮件快照不是有效的 JSON 文件。") from None
    return _validate_snapshot(snapshot)


def _read_remote(config, session):
    _verify_private(config, session)
    response = _request(
        session, "get", f"{API_ROOT}/repos/{config['repo']}/contents/{SNAPSHOT_PATH}",
        config, params={"ref": config["branch"]},
    )
    _check_status(response, {200}, "snapshot")
    data = _response_json(response)
    sha = data.get("sha")
    if not isinstance(sha, str) or not sha or data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        raise MailSyncError("invalid_response", "邮件仓库未返回有效的快照内容及版本。")
    try:
        raw = base64.b64decode("".join(data["content"].split()), validate=True).decode("utf-8-sig")
    except (ValueError, UnicodeError):
        raise MailSyncError("invalid_response", "邮件仓库中的快照编码无法读取。") from None
    return {"snapshot": _decode_snapshot(raw), "version": sha, "source": "github"}


def load_snapshot(secrets=None, environ=None, session=None):
    """Return ``{snapshot, version, source}``, or raise a safe MailSyncError.

    Pass ``st.secrets`` explicitly from the page. Configuration precedence is
    ``mail_workbench`` secrets, then ``MAIL_WORKBENCH_*`` environment variables.
    Only a nonempty, explicit ``MAIL_WORKBENCH_SNAPSHOT`` path enables local
    mode; that mode neither contacts GitHub nor writes the selected file.
    """
    environ = os.environ if environ is None else environ
    local_path = _text(environ, "MAIL_WORKBENCH_SNAPSHOT")
    if local_path:
        try:
            raw = Path(local_path).read_text(encoding="utf-8-sig")
        except (OSError, ValueError, UnicodeError):
            raise MailSyncError("local_read_error", "无法读取指定的本地邮件快照。") from None
        return {"snapshot": _decode_snapshot(raw), "version": None, "source": "local_readonly"}
    config = _config(secrets, environ)
    return _read_remote(config, requests if session is None else session)


def _normalize_updates(updates):
    if isinstance(updates, dict):
        entries = [{"id": key, "status": value} for key, value in updates.items()]
    elif isinstance(updates, list):
        entries = updates
    else:
        raise MailSyncError("invalid_update", "只能提交待办标识和状态。")
    normalized = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "status"}:
            raise MailSyncError("invalid_update", "网页只能修改待办状态，不能修改邮件内容或其他字段。")
        action_id, status = entry["id"], entry["status"]
        if not isinstance(action_id, str) or not action_id.strip() or action_id in normalized:
            raise MailSyncError("invalid_update", "待办更新缺少唯一标识，或包含重复标识。")
        if not isinstance(status, str) or status not in ALLOWED_STATUSES:
            raise MailSyncError("invalid_update", "待办状态只能为" + "、".join(STATUS_LABELS.values()) + "。")
        normalized[action_id] = status
    return normalized


def save_action_updates(updates, expected_version, secrets=None, environ=None, session=None):
    """Save only existing actions' statuses, protecting all other source data.

    ``updates`` is ``{action_id: status}`` or ``[{"id": ..., "status": ...}]``.
    The caller must pass the SHA from its previous ``load_snapshot`` result.
    Conflicts raise ``MailSyncError(code="conflict")``; no automatic retries or
    merges are performed. Completion/update timestamps are server-side values
    generated here in the snapshot's named timezone, never supplied by the UI.
    """
    environ = os.environ if environ is None else environ
    if _text(environ, "MAIL_WORKBENCH_SNAPSHOT"):
        raise MailSyncError("readonly", "本地快照为只读预览，不能保存待办状态。")
    changes = _normalize_updates(updates)
    if not isinstance(expected_version, str) or not expected_version:
        raise MailSyncError("conflict", "保存需要已读取的远端版本，请先刷新邮件工作台。")
    config = _config(secrets, environ)
    session = requests if session is None else session
    current = _read_remote(config, session)
    if current["version"] != expected_version:
        raise MailSyncError("conflict", "邮件数据已更新，未覆盖远端；请刷新后核对并重新保存。")
    snapshot = copy.deepcopy(current["snapshot"])
    actions = {action["id"]: action for action in snapshot["actions"]}
    if any(action_id not in actions for action_id in changes):
        raise MailSyncError("invalid_update", "待办已不存在或标识不正确，请刷新后核对。")
    now = datetime.now(_snapshot_timezone(snapshot)).isoformat(timespec="seconds")
    changed = False
    for action_id, status in changes.items():
        action = actions[action_id]
        if action["status"] == status:
            continue
        action["status"] = status
        action["updated_at"] = now
        action["completed_at"] = now if status == "done" else None
        changed = True
    if not changed:
        return current
    snapshot["updated_at"] = now
    encoded = base64.b64encode(json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
    response = _request(
        session, "put", f"{API_ROOT}/repos/{config['repo']}/contents/{SNAPSHOT_PATH}", config,
        json={"message": "mail: update action statuses", "branch": config["branch"],
              "sha": expected_version, "content": encoded},
    )
    _check_status(response, {200}, "snapshot")
    data = _response_json(response)
    content = data.get("content")
    new_sha = content.get("sha") if isinstance(content, dict) else None
    if not isinstance(new_sha, str) or not new_sha:
        raise MailSyncError("invalid_response", "仓库未返回新版本，保存结果尚未确认，请刷新核对。")
    return {"snapshot": snapshot, "version": new_sha, "source": "github"}


def save_message_updates(updates, expected_version, secrets=None, environ=None, session=None):
    """Save triage only for existing mail that has no extracted actions.

    The update shape and SHA guard match ``save_action_updates``. A mail-level
    ``done`` decision never creates an action or a task completion timestamp.
    Existing action statuses and every source field remain untouched.
    """
    environ = os.environ if environ is None else environ
    if _text(environ, "MAIL_WORKBENCH_SNAPSHOT"):
        raise MailSyncError("readonly", "本地快照为只读预览，不能保存邮件判断。")
    try:
        changes = _normalize_updates(updates)
    except MailSyncError:
        raise MailSyncError("invalid_update", "只能提交邮件标识和有效判断状态，不能修改邮件内容或其他字段。") from None
    if not isinstance(expected_version, str) or not expected_version:
        raise MailSyncError("conflict", "保存需要已读取的远端版本，请先刷新邮件工作台。")
    config = _config(secrets, environ)
    session = requests if session is None else session
    current = _read_remote(config, session)
    if current["version"] != expected_version:
        raise MailSyncError("conflict", "邮件数据已更新，未覆盖远端；请刷新后核对并重新保存。")
    snapshot = copy.deepcopy(current["snapshot"])
    messages = {message["id"]: message for message in snapshot["messages"]}
    with_actions = {action.get("message_id") for action in snapshot["actions"]}
    if any(message_id not in messages or message_id in with_actions for message_id in changes):
        raise MailSyncError("invalid_update", "邮件已不存在或已有处理事项，请刷新后逐项判断。")
    now = datetime.now(_snapshot_timezone(snapshot)).isoformat(timespec="seconds")
    changed = False
    for message_id, status in changes.items():
        message = messages[message_id]
        if message.get("triage_status") == status:
            continue
        message["triage_status"] = status
        message["triage_updated_at"] = now
        changed = True
    if not changed:
        return current
    snapshot["updated_at"] = now
    encoded = base64.b64encode(json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
    response = _request(
        session, "put", f"{API_ROOT}/repos/{config['repo']}/contents/{SNAPSHOT_PATH}", config,
        json={"message": "mail: update message decisions", "branch": config["branch"],
              "sha": expected_version, "content": encoded},
    )
    _check_status(response, {200}, "snapshot")
    data = _response_json(response)
    content = data.get("content")
    new_sha = content.get("sha") if isinstance(content, dict) else None
    if not isinstance(new_sha, str) or not new_sha:
        raise MailSyncError("invalid_response", "仓库未返回新版本，保存结果尚未确认，请刷新核对。")
    return {"snapshot": snapshot, "version": new_sha, "source": "github"}
