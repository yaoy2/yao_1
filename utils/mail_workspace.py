"""Local, credential-free mail archive and dashboard snapshots.

Collection is intentionally separate: this module consumes verified browser
observations and files already downloaded by the operator. It never logs in.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from utils.mail_action_status import ACTIVE_STATUSES, ALL_STATUSES, STATUS_LABELS


SCHEMA_VERSION = 1
TIMEZONE = "Asia/Shanghai"
SHANGHAI = timezone(timedelta(hours=8), name=TIMEZONE)
ACTION_STATUSES = ALL_STATUSES
KINDS = {"daily", "morning", "weekly", "sample"}
MESSAGE_FIELDS = ("id", "received_at", "sender", "subject", "folder", "category",
                  "summary", "source_url", "archive_path")
MESSAGE_TRIAGE_FIELDS = ("triage_status", "triage_updated_at")
ACTION_FIELDS = ("id", "message_id", "title", "requirement", "owner", "due_at",
                 "due_text", "due_basis", "recipient", "submission_method", "status",
                 "completed_at", "updated_at")
ATTACHMENT_FIELDS = ("id", "name", "size", "sha256", "path", "status", "error")
RUN_FIELDS = ("id", "kind", "started_at", "finished_at", "status", "message_count",
              "attachment_count", "errors")
REPORT_FIELDS = ("id", "kind", "date", "period_start", "period_end", "generated_at",
                  "title", "markdown", "action_ids")
PUBLIC_ERROR_REASONS = frozenset({
    "未取得实际下载文件", "实际下载文件不存在或不可读取", "下载文件与声明的SHA-256不一致",
    "归档目标内容冲突，已保留原文件", "读取或写入附件失败", "此前归档的附件已缺失或内容校验失败",
    "采集窗口未确认完整", "采集窗口与成功游标之间有缺口，游标未推进",
    "部分附件未完成，见附件索引", "附件清单未确认完整", "实际附件清单数量与声明不符",
    "采集器报告错误，详细原因仅保存在本机运行记录",
})


def now_iso():
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string with timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO 8601 timestamp") from exc
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result.astimezone(SHANGHAI)


def normalize_time(value):
    return parse_time(value).isoformat(timespec="seconds")


def normalize_due(value):
    if value is None or value == "":
        return None
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value).isoformat()
    return normalize_time(value)


def sanitize_source_url(value):
    """Keep only this mailbox's HTTPS path; never retain query credentials."""
    try:
        parts = urlsplit(str(value or ""))
        path = unquote(parts.path)
        if (parts.scheme != "https" or parts.hostname != "mail.nsu.edu.cn"
                or parts.port not in (None, 443) or parts.username or parts.password
                or not path.startswith("/owa/") or "\\" in path
                or any(part == ".." for part in path.split("/"))):
            return ""
        return urlunsplit(("https", "mail.nsu.edu.cn", parts.path, "", ""))
    except (ValueError, TypeError):
        return ""


def safe_filename(value):
    name = unicodedata.normalize("NFC", str(value or "attachment"))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", name).strip(" .")
    if not name or name in {".", ".."}:
        name = "attachment"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", name, re.I):
        name = "_" + name
    return name[:150].rstrip(" .")


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _root_path(root):
    path = Path(root).expanduser()
    if not path.is_absolute():
        raise ValueError("root must be an explicit absolute path")
    return path.resolve()


def _inside(root, relative):
    raw = str(relative)
    if (not raw or "\\" in raw or ":" in raw or Path(raw).is_absolute()
            or ".." in raw.split("/")):
        raise ValueError("unsafe archive relative path")
    result = (root / raw).resolve()
    if not result.is_relative_to(root) or result == root:
        raise ValueError("archive path escapes root")
    return result


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".mail-write-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _locked(root):
    """An OS lock is released even if a worker crashes; no stale lock removal."""
    lock_path = _inside(root, ".workspace.lock")
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("workspace is busy; retry after the active operation") from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("workspace is busy; retry after the active operation") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def initialize(root, account):
    root = _root_path(root)
    account = str(account).strip()
    if not account or "@" not in account or any(c.isspace() for c in account):
        raise ValueError("account must be an email address")
    root.mkdir(parents=True, exist_ok=True)
    with _locked(root):
        path = _inside(root, "dashboard.json")
        if path.exists():
            data = load_dashboard(root)
            if data["account"] != account:
                raise ValueError("workspace belongs to a different account")
            return status(root)
        _inside(root, "archive").mkdir(exist_ok=True)
        _atomic_json(path, {
            "schema_version": SCHEMA_VERSION, "timezone": TIMEZONE, "account": account,
            "updated_at": now_iso(),
            "coverage": {"since": None, "through": None, "complete": False,
                         "note": "尚未完成首次完整采集"},
            "messages": [], "actions": [], "runs": [], "reports": [],
        })
    return status(root)


def load_dashboard(root):
    root = _root_path(root)
    with _inside(root, "dashboard.json").open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if data.get("schema_version") != SCHEMA_VERSION or data.get("timezone") != TIMEZONE:
        raise ValueError("unsupported workspace schema or timezone")
    for key in ("messages", "actions", "runs", "reports"):
        if not isinstance(data.get(key), list):
            raise ValueError("invalid workspace collection")
    return data


def status(root):
    data = load_dashboard(root)
    return {"schema_version": SCHEMA_VERSION, "account": data["account"],
            "updated_at": data["updated_at"], "coverage": data["coverage"],
            "message_count": len(data["messages"]), "action_count": len(data["actions"]),
            "attachment_count": sum(len(m.get("attachments", [])) for m in data["messages"]),
            "incomplete_attachments": sum(a.get("status") != "success"
                for m in data["messages"] for a in m.get("attachments", [])),
            "run_count": len(data["runs"]), "report_count": len(data["reports"])}


def _text(value):
    return str(value) if value is not None else ""


def _validate_batch(batch, data):
    if not isinstance(batch, dict) or batch.get("schema_version", 1) != SCHEMA_VERSION:
        raise ValueError("unsupported batch schema")
    if batch.get("account") != data["account"]:
        raise ValueError("batch account does not match workspace")
    if batch.get("kind") not in KINDS:
        raise ValueError("batch kind must be daily, morning, weekly or sample")
    window = batch.get("window", {})
    since, through = parse_time(window.get("since")), parse_time(window.get("through"))
    if since > through:
        raise ValueError("batch window is reversed")
    if not isinstance(window.get("complete"), bool):
        raise ValueError("window.complete must explicitly be true or false")
    for field in ("started_at", "finished_at"):
        if batch.get(field):
            parse_time(batch[field])
    if batch.get("started_at") and batch.get("finished_at"):
        if parse_time(batch["started_at"]) > parse_time(batch["finished_at"]):
            raise ValueError("batch runtime is reversed")
    messages, actions = batch.get("messages", []), batch.get("actions", [])
    if not isinstance(messages, list) or not isinstance(actions, list):
        raise ValueError("messages and actions must be arrays")
    if not isinstance(batch.get("errors", []), list):
        raise ValueError("errors must be an array")
    known_ids = {m["id"] for m in data["messages"]}
    incoming_ids = set()
    for message in messages:
        identifier = message.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in incoming_ids:
            raise ValueError("message id missing or duplicated in batch")
        incoming_ids.add(identifier)
        if "body_text" not in message and identifier not in known_ids:
            raise ValueError("a new message requires a verified body_text snapshot")
        if "body_text" in message and not isinstance(message["body_text"], str):
            raise ValueError("body_text must be a string")
        received = parse_time(message.get("received_at"))
        if not since <= received <= through:
            raise ValueError("message lies outside the declared collection window")
        attachments = message.get("attachments", [])
        if not isinstance(attachments, list):
            raise ValueError("attachments must be an array")
        ids = set()
        for attachment in attachments:
            identifier = attachment.get("id")
            if not isinstance(identifier, str) or not identifier or identifier in ids:
                raise ValueError("attachment id missing or duplicated within message")
            ids.add(identifier)
            source = attachment.get("download_path")
            if source and not Path(source).is_absolute():
                raise ValueError("download_path must be an absolute path")
    action_ids = set()
    for action in actions:
        identifier = action.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in action_ids:
            raise ValueError("action id missing or duplicated in batch")
        action_ids.add(identifier)
        if action.get("message_id") not in known_ids | incoming_ids:
            raise ValueError("action refers to an unknown message")
        if action.get("status", "pending") not in ACTION_STATUSES:
            raise ValueError("invalid action status")
        due = normalize_due(action.get("due_at"))
        if due and (not action.get("due_text") or not action.get("due_basis")):
            raise ValueError("a deadline requires original due_text and due_basis")
        if action.get("completed_at"):
            parse_time(action["completed_at"])
    return since, through


def _archive_attachment(root, directory, incoming, previous, hash_index):
    result = {"id": incoming["id"], "name": _text(incoming.get("name") or "attachment"),
              "size": None, "sha256": "", "path": "", "status": "missing", "error": ""}
    source = incoming.get("download_path")
    if not source:
        if previous and previous.get("status") == "success":
            archived = _inside(root, previous["path"])
            if archived.is_file() and _sha_file(archived) == previous.get("sha256"):
                return copy.deepcopy(previous)
        result["status"] = "error" if incoming.get("status") == "error" else "missing"
        result["error"] = _text(incoming.get("error")) or "未取得实际下载文件"
        return result
    source_path = Path(source)
    if not source_path.is_file():
        result.update(status="error", error="实际下载文件不存在或不可读取")
        return result
    temporary = None
    try:
        destination_dir = _inside(root, directory + "/attachments")
        destination_dir.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".mail-copy-", suffix=".tmp", dir=destination_dir)
        digest, size = hashlib.sha256(), 0
        with os.fdopen(fd, "wb") as target, source_path.open("rb") as original:
            for chunk in iter(lambda: original.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        sha = digest.hexdigest()
        expected = incoming.get("sha256")
        if expected and expected != sha:
            result.update(status="error", error="下载文件与声明的SHA-256不一致")
            return result
        relative = hash_index.get(sha)
        if relative:
            existing = _inside(root, relative)
            if not existing.is_file() or _sha_file(existing) != sha:
                relative = None
        if not relative:
            relative = directory + "/attachments/" + sha + "__" + safe_filename(result["name"])
            destination = _inside(root, relative)
            if destination.exists():
                if _sha_file(destination) != sha:
                    result.update(status="error", error="归档目标内容冲突，已保留原文件")
                    return result
            else:
                os.replace(temporary, destination)
                temporary = None
            hash_index[sha] = relative
        result.update(size=size, sha256=sha, path=relative, status="success")
    except OSError:
        result.update(status="error", error="读取或写入附件失败")
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return result


def ingest(root, batch):
    root = _root_path(root)
    with _locked(root):
        data = load_dashboard(root)
        since, through = _validate_batch(batch, data)
        finished = normalize_time(batch.get("finished_at") or now_iso())
        started = normalize_time(batch.get("started_at") or finished)
        batch_id = _text(batch.get("id")) or hashlib.sha256(_json_bytes(batch)).hexdigest()
        errors = [_text(error) for error in batch.get("errors", [])]
        message_map = {m["id"]: m for m in data["messages"]}
        hash_index = {a["sha256"]: a["path"] for m in data["messages"]
                      for a in m.get("attachments", []) if a.get("status") == "success"}
        incomplete, successful = 0, 0
        for incoming in batch.get("messages", []):
            identifier = incoming["id"]
            previous = message_map.get(identifier, {})
            stamp = parse_time(incoming["received_at"])
            directory = "archive/" + stamp.date().isoformat() + "/" + hashlib.sha256(identifier.encode()).hexdigest()[:24]
            message = {field: _text(incoming.get(field, previous.get(field))) for field in MESSAGE_FIELDS}
            # Collection refreshes evidence, never a user's mail-level decision.
            for field in MESSAGE_TRIAGE_FIELDS:
                if field in previous:
                    message[field] = copy.deepcopy(previous[field])
            message["received_at"] = stamp.isoformat(timespec="seconds")
            message["source_url"] = sanitize_source_url(incoming.get("source_url", previous.get("source_url")))
            if "body_text" not in incoming:
                message["archive_path"] = previous["archive_path"]
            else:
                snapshot = {"format": "browser_text_snapshot", "is_original_eml": False,
                            "id": identifier, "received_at": message["received_at"],
                            "sender": message["sender"], "subject": message["subject"],
                            "source_url": message["source_url"], "body_text": incoming["body_text"],
                            "observed_attachments": [{"id": a["id"], "name": _text(a.get("name"))}
                                                     for a in incoming.get("attachments", [])]}
                for local_field in ("headers_text", "internet_message_id"):
                    if incoming.get(local_field) is not None:
                        snapshot[local_field] = _text(incoming[local_field])
                snapshot_digest = hashlib.sha256(_json_bytes(snapshot)).hexdigest()
                snapshot_relative = directory + "/snapshot-" + snapshot_digest + ".json"
                snapshot_path = _inside(root, snapshot_relative)
                if snapshot_path.exists():
                    if _sha_file(snapshot_path) != snapshot_digest:
                        raise ValueError("existing message snapshot failed integrity verification")
                else:
                    _atomic_json(snapshot_path, snapshot)
                message["archive_path"] = snapshot_relative
            previous_attachments = {a["id"]: a for a in previous.get("attachments", [])}
            attachments = dict(previous_attachments)
            incoming_attachment_ids = {attachment["id"] for attachment in incoming.get("attachments", [])}
            for attachment in incoming.get("attachments", []):
                attachments[attachment["id"]] = _archive_attachment(
                    root, directory, attachment, previous_attachments.get(attachment["id"]), hash_index)
            # A metadata-only retry may omit previously known attachments. Such
            # retained indexes must still point to intact local files.
            for attachment_id, previous_attachment in list(attachments.items()):
                if attachment_id not in incoming_attachment_ids and previous_attachment.get("status") == "success":
                    retained = copy.deepcopy(previous_attachment)
                    try:
                        retained_path = _inside(root, retained["path"])
                        intact = retained_path.is_file() and _sha_file(retained_path) == retained.get("sha256")
                    except OSError:
                        intact = False
                    if not intact:
                        retained.update(status="error", error="此前归档的附件已缺失或内容校验失败")
                    attachments[attachment_id] = retained
            message["attachments"] = list(attachments.values())
            if incoming.get("attachments_complete") is False:
                errors.append("附件清单未确认完整: " + identifier)
            expected_count = incoming.get("expected_attachment_count")
            if expected_count is not None and expected_count != len(incoming.get("attachments", [])):
                errors.append("实际附件清单数量与声明不符: " + identifier)
            for attachment in message["attachments"]:
                if attachment["status"] == "success":
                    successful += 1
                else:
                    incomplete += 1
                    errors.append("附件未完成: " + identifier + "/" + attachment["id"])
            message_map[identifier] = message
        actions = {action["id"]: action for action in data["actions"]}
        previously_actioned = {action.get("message_id") for action in data["actions"]}
        for incoming in batch.get("actions", []):
            previous = actions.get(incoming["id"], {})
            action = {field: _text(incoming.get(field, previous.get(field))) for field in ACTION_FIELDS}
            action["due_at"] = normalize_due(incoming.get("due_at", previous.get("due_at")))
            if previous:
                # updated_at is the shared status version. Advancing it for a
                # metadata refresh could overwrite a concurrent web status edit.
                for field in ("status", "completed_at", "updated_at"):
                    action[field] = previous.get(field)
            else:
                action["status"] = incoming.get("status", "pending")
                message = message_map.get(action["message_id"], {})
                triage = message.get("triage_status")
                if action["message_id"] not in previously_actioned and triage in ACTION_STATUSES:
                    # A mail-level completion does not prove that a newly
                    # extracted task was completed. Only explicit exemptions
                    # carry into the first group of extracted tasks.
                    action["status"] = triage if triage in {"no_action", "out_of_scope"} else "needs_confirmation"
                action["completed_at"] = (
                    normalize_time(incoming["completed_at"]) if incoming.get("completed_at") else finished
                ) if action["status"] == "done" else None
                action["updated_at"] = finished
            actions[action["id"]] = action
        complete = batch["window"]["complete"] and not errors and incomplete == 0
        if not batch["window"]["complete"]:
            errors.append("采集窗口未确认完整")
        if batch["kind"] != "sample":
            coverage = data["coverage"]
            old_through = parse_time(coverage["through"]) if coverage.get("through") else None
            old_since = parse_time(coverage["since"]) if coverage.get("since") else None
            if complete and ((old_through and since > old_through) or (old_since and through < old_since)):
                complete = False
                errors.append("采集窗口与成功游标之间有缺口，游标未推进")
            if complete:
                coverage["since"] = min(since, old_since).isoformat(timespec="seconds") if old_since else since.isoformat(timespec="seconds")
                coverage["through"] = max(through, old_through).isoformat(timespec="seconds") if old_through else through.isoformat(timespec="seconds")
                coverage.update(complete=True, note=_text(batch["window"].get("note")) or "已核验连续窗口及附件")
            else:
                coverage.update(complete=False, note="本次采集未完成；成功游标保持不变")
        run = {"id": batch_id, "kind": batch["kind"], "started_at": started,
               "finished_at": finished, "status": "success" if complete else "partial",
               "message_count": len(batch.get("messages", [])),
               "attachment_count": successful, "errors": list(dict.fromkeys(errors))}
        run_map = {run["id"]: run for run in data["runs"]}
        run_map[batch_id] = run
        data.update(updated_at=now_iso(), messages=sorted(message_map.values(), key=lambda m: m["received_at"], reverse=True),
                    actions=list(actions.values()), runs=list(run_map.values()))
        _atomic_json(_inside(root, "dashboard.json"), data)
    return {"run_id": batch_id, "status": run["status"], "message_count": run["message_count"],
            "attachment_count": successful, "incomplete_attachments": incomplete,
            "error_count": len(run["errors"]), "coverage": data["coverage"]}


def _day_start(moment):
    return datetime.combine(moment.date(), time.min, SHANGHAI)


def generate_report(root, kind, at):
    if kind not in KINDS - {"sample"}:
        raise ValueError("report kind must be daily, morning or weekly")
    end = parse_time(at)
    root = _root_path(root)
    with _locked(root):
        data = load_dashboard(root)
        start = _day_start(end)
        if kind == "weekly":
            start -= timedelta(days=end.weekday())
        elif kind == "daily":
            prior = [parse_time(report["period_end"]) for report in data["reports"]
                     if report["kind"] == "daily" and parse_time(report["period_end"]) < end]
            if prior:
                start = max(prior)
        messages = [message for message in data["messages"]
                    if start <= parse_time(message["received_at"]) <= end]
        active = [action for action in data["actions"] if action["status"] in ACTIVE_STATUSES]
        active.sort(key=lambda action: (action.get("due_at") or "9999", action["id"]))
        if kind == "morning":
            horizon = (end.date() + timedelta(days=3)).isoformat()
            active = [action for action in active if not action.get("due_at") or action["due_at"][:10] <= horizon]
        coverage = data["coverage"]
        period_complete = bool(coverage.get("complete") and coverage.get("since") and coverage.get("through")
                               and parse_time(coverage["since"]) <= start and parse_time(coverage["through"]) >= end)
        labels = {"daily": "每日邮件简报", "morning": "工作日截止事项提醒", "weekly": "每周邮件工作汇总"}
        title = end.date().isoformat() + " " + labels[kind]
        lines = ["# " + title, "", "统计时间：" + start.isoformat(timespec="minutes") + " 至 " + end.isoformat(timespec="minutes"),
                 "", "覆盖状态：" + ("本统计窗口已核验完整。" if period_complete else "归档尚未覆盖完整统计窗口，以下仅为已读取内容。")]
        if kind != "morning":
            lines.extend(["", "## 邮件概览", ""])
            for message in messages:
                lines.append("- [" + (message["category"] or "未分类") + "] " + message["subject"] + "：" + (message["summary"] or "摘要待整理"))
            if not messages:
                lines.append("本统计区间内没有已归档邮件记录；这不代表邮箱没有新邮件。")
        lines.extend(["", "## 待处理与时间节点", ""])
        for action in active:
            due = action.get("due_at")
            overdue = bool(due and (due < end.date().isoformat() if len(due) == 10 else parse_time(due) < end))
            state_label = STATUS_LABELS[action["status"]]
            deadline_label = "时间待确认" if not due else ("已逾期" if overdue else ("今日到期" if due[:10] == end.date().isoformat() else ""))
            label = state_label + (" · " + deadline_label if deadline_label else "")
            lines.append("- **" + label + " · " + action["title"] + "**｜截止：" + (action.get("due_text") or "未明确")
                         + ("（" + due + "）" if due else "") + "｜责任：" + (action.get("owner") or "待确认")
                         + "｜要求：" + action.get("requirement", "") + "｜提交至：" + (action.get("recipient") or "待确认"))
        if not active:
            lines.append("暂无已提取的未完成事项。")
        completed = []
        if kind == "weekly":
            completed = [action for action in data["actions"]
                         if action["status"] == "done" and action.get("completed_at")
                         and start <= parse_time(action["completed_at"]) <= end]
            completed.sort(key=lambda action: (parse_time(action["completed_at"]), action["id"]))
            lines.extend(["", "## 本周已完成事项", "", "本周已完成：" + str(len(completed)) + " 项。"])
            for action in completed:
                lines.append("- " + action["title"] + "｜完成时间："
                             + parse_time(action["completed_at"]).strftime("%Y-%m-%d %H:%M")
                             + "｜责任：" + (action.get("owner") or "待确认"))
        incomplete = [a for m in data["messages"] for a in m.get("attachments", []) if a["status"] != "success"]
        lines.extend(["", "## 采集核对", "", "未完成附件：" + str(len(incomplete)) + "；最近成功游标：" + (data["coverage"].get("through") or "尚无") + "。"])
        report = {"id": kind + "-" + end.isoformat(timespec="seconds"), "kind": kind,
                  "date": end.date().isoformat(), "period_start": start.isoformat(timespec="seconds"),
                  "period_end": end.isoformat(timespec="seconds"), "generated_at": now_iso(),
                  "title": title, "markdown": "\n".join(lines) + "\n",
                  "action_ids": [action["id"] for action in active]}
        reports = {report["id"]: report for report in data["reports"]}
        reports[report["id"]] = report
        data.update(reports=list(reports.values()), updated_at=report["generated_at"])
        _atomic_json(_inside(root, "dashboard.json"), data)
    result = {"report_id": report["id"], "kind": kind, "date": report["date"],
              "message_count": len(messages), "active_action_count": len(active),
              "coverage_complete": period_complete}
    if kind == "weekly":
        result["completed_action_count"] = len(completed)
    return result


def cloud_snapshot(root):
    """Explicit allowlist excludes message bodies, source files and arbitrary keys."""
    return public_snapshot(load_dashboard(root), root)


def _public_diagnostic(value):
    """Only fixed internal reasons may leave the machine; tool errors may contain credentials."""
    if not value:
        return ""
    text = _text(value)
    if text in PUBLIC_ERROR_REASONS:
        return text
    for prefix, reason in (("附件未完成: ", "部分附件未完成，见附件索引"),
                           ("附件清单未确认完整: ", "附件清单未确认完整"),
                           ("实际附件清单数量与声明不符: ", "实际附件清单数量与声明不符")):
        if text.startswith(prefix):
            return reason
    return "采集器报告错误，详细原因仅保存在本机运行记录"


def public_snapshot(data, root):
    """Sanitize an in-memory dashboard without writing it or reading credentials."""
    if data.get("schema_version") != SCHEMA_VERSION or data.get("timezone") != TIMEZONE:
        raise ValueError("unsupported workspace schema or timezone")
    snapshot = {key: copy.deepcopy(data[key]) for key in ("schema_version", "timezone", "account", "updated_at")}
    snapshot["coverage"] = {key: data["coverage"].get(key) for key in ("since", "through", "complete", "note")}
    snapshot["messages"] = []
    root_path = _root_path(root)
    for incoming in data["messages"]:
        message = {key: incoming.get(key, "") for key in MESSAGE_FIELDS}
        for key in MESSAGE_TRIAGE_FIELDS:
            if key in incoming:
                message[key] = copy.deepcopy(incoming[key])
        message["source_url"] = sanitize_source_url(message["source_url"])
        if message["archive_path"]:
            _inside(root_path, message["archive_path"])
        message["attachments"] = []
        for attachment in incoming.get("attachments", []):
            item = {key: attachment.get(key) for key in ATTACHMENT_FIELDS}
            item["error"] = _public_diagnostic(item.get("error"))
            if item.get("path"):
                _inside(root_path, item["path"])
            message["attachments"].append(item)
        snapshot["messages"].append(message)
    for collection, fields in (("actions", ACTION_FIELDS), ("runs", RUN_FIELDS), ("reports", REPORT_FIELDS)):
        snapshot[collection] = [{key: copy.deepcopy(item.get(key)) for key in fields
                                 if key != "action_ids" or key in item}
                                for item in data[collection]]
    for run in snapshot["runs"]:
        run["errors"] = [_public_diagnostic(error) for error in (run.get("errors") or [])]
    return snapshot


def export_snapshot(root, output):
    output = Path(output)
    if not output.is_absolute():
        raise ValueError("output must be an explicit absolute path")
    root_path = _root_path(root)
    if output.resolve().is_relative_to(root_path / "archive") or output.resolve() == root_path / "dashboard.json":
        raise ValueError("snapshot output must not overwrite the archive or local dashboard")
    snapshot = cloud_snapshot(root)
    _atomic_json(output, snapshot)
    return {"status": "exported", "schema_version": SCHEMA_VERSION,
            "message_count": len(snapshot["messages"]), "action_count": len(snapshot["actions"])}
