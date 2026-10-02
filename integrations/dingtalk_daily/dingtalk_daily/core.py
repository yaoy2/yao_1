"""Filter a desktop capture and render an evidence-based daily report.

This module performs no I/O. Only accepted messages are returned; callers must
persist the returned report, never the unfiltered capture. Capture ``issues``
must be collector-generated diagnostics, not copied chat text.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import html
import re
from typing import Any


# Contemporary Asia/Shanghai time is UTC+08:00. A fixed zone keeps this small
# Windows utility independent of the optional system/IANA timezone database.
SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
_KINDS = {"text", "attachment", "image", "unknown"}
_CLUE_WORDS = ("请", "麻烦", "劳烦", "需要", "记得", "提醒", "待办", "截止", "报送", "提交", "确认", "反馈", "回复")


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _diagnostics(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _unique([item.strip() for item in value if isinstance(item, str) and item.strip()])


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(SHANGHAI)
    except (ValueError, TypeError, OverflowError):
        return None


def _window(capture: dict, run_at: datetime) -> tuple[str, datetime | None, datetime | None, list[str]]:
    issues: list[str] = []
    raw_date = capture.get("date")
    try:
        if not isinstance(raw_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
            raise ValueError
        selected = date.fromisoformat(raw_date)
        start = datetime.combine(selected, time.min, SHANGHAI)
        end = start + timedelta(days=1) - timedelta(microseconds=1)
    except (ValueError, OverflowError):
        return "", None, None, ["整理日期无效；未纳入任何消息。"]
    cutoff = _aware(capture.get("cutoff"))
    if cutoff is None:
        return selected.isoformat(), start, None, ["采集截止时间缺少可靠的日期或时区；未纳入任何消息。"]
    if run_at < start:
        return selected.isoformat(), start, None, ["整理日期晚于本次运行开始日期；未纳入未来消息。"]
    if cutoff > run_at:
        issues.append("采集截止时间超过本次运行开始，已限制到运行开始时刻。")
    if cutoff > end:
        issues.append("采集截止时间超过整理日期，已限制到该日结束。")
    cutoff = min(cutoff, run_at, end)
    if cutoff < start:
        return selected.isoformat(), start, None, ["采集截止时间早于整理日期；未纳入任何消息。"]
    return selected.isoformat(), start, cutoff, issues


def _self_state(message: dict, self_names: set[str]) -> tuple[bool | None, bool]:
    """Return identity and whether available identity evidence conflicts."""
    sender = _text(message.get("sender"))
    explicit = message.get("is_self")
    named_self = bool(sender) and sender in self_names
    if explicit is True:
        if sender and self_names and not named_self:
            return None, True
        return True, False
    if explicit is False:
        return (None, True) if named_self else (False, False)
    if named_self:
        return True, False
    if sender and self_names:
        return False, False
    return None, False


def _merge_conversations(rows: list[dict], issues: list[str]) -> list[dict]:
    grouped: dict[tuple[str, Any], list[dict]] = {}
    for index, row in enumerate(rows):
        identifier = _text(row.get("id"))
        key = ("id", identifier) if identifier else ("row", index)
        grouped.setdefault(key, []).append(row)
    result = []
    for parts in grouped.values():
        identities = {(_text(part.get("title")), _text(part.get("kind"))) for part in parts}
        if len(identities) != 1:
            issues.append("有会话编号对应的名称或类型不一致；相关记录已排除。")
            continue
        title, kind = next(iter(identities))
        row_issues = []
        messages = []
        for part in parts:
            row_issues.extend(_diagnostics(part.get("issues")))
            if isinstance(part.get("messages"), list):
                messages.extend(part["messages"])
            else:
                row_issues.append("未取得可核对的消息列表。")
        if not _text(parts[0].get("id")):
            row_issues.append("会话缺少稳定编号，无法确认重名会话身份。")
        result.append({
            "id": _text(parts[0].get("id")), "title": title, "kind": kind,
            "complete": all(part.get("complete") is True for part in parts),
            "issues": _unique(row_issues), "messages": messages,
        })
    return result


def _deduplicate(messages: list, problems: Counter) -> list[dict]:
    """Only stable message IDs justify de-duplication, never text/time."""
    by_id: dict[str, tuple] = {}
    conflicts: set[str] = set()
    unique = []
    for message in messages:
        if not isinstance(message, dict):
            problems["invalid_record"] += 1
            continue
        identifier = _text(message.get("id"))
        if not identifier:
            unique.append(message)
            continue
        fingerprint = tuple((type(message.get(key)).__name__, repr(message.get(key))) for key in (
            "timestamp", "sender", "is_self", "text", "kind"
        ))
        if identifier in by_id:
            if by_id[identifier] != fingerprint:
                conflicts.add(identifier)
            continue
        by_id[identifier] = fingerprint
        unique.append(message)
    if conflicts:
        problems["conflicting_id"] += len(conflicts)
    return [message for message in unique if _text(message.get("id")) not in conflicts]


def _clues(messages: list[dict]) -> list[dict]:
    result = []
    for index, message in enumerate(messages, 1):
        words = [word for word in _CLUE_WORDS if word in message["text"]]
        if "?" in message["text"] or "？" in message["text"]:
            words.append("问句")
        if words:
            result.append({
                "message_index": index, "message_id": message["id"],
                "timestamp": message["timestamp"], "sender": message["sender"],
                "is_self": message["is_self"], "text": message["text"],
                "reason": "含提示词：" + "、".join(words),
            })
    return result


def _extract(conversation: dict, start: datetime, cutoff: datetime, self_names: set[str], self_only: bool) -> dict:
    issues = list(conversation["issues"])
    if not conversation["complete"]:
        issues.append("该会话采集不完整，不能据此确认当天全部消息。")
    problems: Counter = Counter()
    result = []
    for message in _deduplicate(conversation["messages"], problems):
        is_self, conflicting = _self_state(message, self_names)
        # Other members' messages are outside the group scope even when their
        # timestamps are unreadable. Their unreadable dates do not imply that
        # the requested own-message capture is incomplete.
        if self_only and is_self is False:
            continue
        stamp = _aware(message.get("timestamp"))
        if stamp is None:
            problems["invalid_time"] += 1
            continue
        if not start <= stamp <= cutoff:
            continue
        if conflicting:
            problems["conflicting_sender"] += 1
            continue
        if self_only and is_self is not True:
            if is_self is None:
                problems["unknown_self"] += 1
            continue
        sender = _text(message.get("sender"))
        if not sender and is_self is not True:
            problems["unknown_sender"] += 1
        identifier = _text(message.get("id"))
        if not identifier:
            problems["missing_id"] += 1
        content = _text(message.get("text"))
        kind = _text(message.get("kind"))
        if kind not in _KINDS:
            kind = "unknown"
        if kind != "text":
            problems["unread_content"] += 1
        elif not content.strip():
            problems["empty_text"] += 1
        result.append({
            "id": identifier, "timestamp": stamp.isoformat(), "sender": sender,
            "is_self": is_self, "text": content, "kind": kind,
            "source": _text(message.get("source")),
        })
    notices = {
        "invalid_record": "条记录格式无法识别，已排除。",
        "invalid_time": "条消息缺少可靠的日期或时区，已排除。",
        "conflicting_id": "个消息编号对应冲突内容，相关消息已排除。",
        "conflicting_sender": "条消息的发送人与本人标记冲突，已排除。",
        "unknown_self": "条群消息无法确认是否由本人发送，已排除。",
        "unknown_sender": "条消息未识别发送人，原文按未知发送人保留。",
        "missing_id": "条消息缺少稳定编号，未按文本或时间猜测去重。",
        "unread_content": "条非文字或类型未明消息仅保留界面可见文字，内容未完整解析。",
        "empty_text": "条文字消息未取得正文。",
    }
    issues.extend(f"有 {count} {notices[key]}" for key, count in problems.items() if count)
    result.sort(key=lambda message: message["timestamp"])
    issues = _unique(issues)
    return {
        "id": conversation["id"], "title": conversation["title"], "kind": conversation["kind"],
        "status": "partial" if issues else ("complete" if result else "empty"),
        "complete": not issues, "issues": issues, "messages": result,
        "message_count": len(result), "follow_up_clues": _clues(result),
    }


def _escape(value: str) -> str:
    # Escape both HTML and Markdown, including image/link syntax. Evidence is
    # displayed, never evaluated as report structure or an active image.
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~>\-])", r"\\\1", value)


def _quote(value: str) -> list[str]:
    return ["> " + _escape(line) for line in value.split("\n")]


def _sender(message: dict) -> str:
    if message["sender"]:
        return message["sender"] + ("（本人）" if message["is_self"] is True else "")
    return "本人（界面标记）" if message["is_self"] is True else "发送人未识别"


def _render(report: dict) -> str:
    date_label = report["date"] or "日期无效"
    lines = [f"# 钉钉当日记录整理 · {_escape(date_label)}", ""]
    if report["cutoff"]:
        lines.append(f"范围：北京时间 00:00 至 {_escape(report['cutoff'][11:19])}（含截止时刻）。")
    else:
        lines.append("范围：未取得有效时间窗口，未纳入消息。")
    status = "完整" if report["status"] == "complete" else "部分完成（存在未确认或遗漏）"
    lines.extend([f"采集状态：{status}。", "", "## 一、概览", ""])
    state_labels = {"complete": "已核对", "empty": "已核对，范围内无符合条件的消息", "partial": "采集不完整或有排除项"}
    for section in report["sections"]:
        lines.append(f"- {_escape(section['title'])}：{section['message_count']} 条；{state_labels[section['status']]}。")
        for issue in section["issues"]:
            lines.append(f"  - {_escape(issue)}")
        for conversation in section["conversations"]:
            if section["key"] == "other_direct":
                lines.append(f"  - {_escape(conversation['title'])}：{conversation['message_count']} 条。")
            for issue in conversation["issues"]:
                lines.append(f"  - {_escape(conversation['title'])}：{_escape(issue)}")
    for issue in report["issues"]:
        lines.append(f"- {_escape(issue)}")
    lines.extend(["", "## 二、需跟进线索", "", "以下仅按原文提示词定位，需人工核实是否需要跟进；不代表任务尚未完成，也不推断责任人或期限。", ""])
    clue_count = 0
    for section in report["sections"]:
        for conversation in section["conversations"]:
            for clue in conversation["follow_up_clues"]:
                clue_count += 1
                lines.extend([
                    f"- {_escape(conversation['title'])} · {clue['timestamp'][11:19]} · {_escape(_sender(clue))} · 原文 #{clue['message_index']}；{_escape(clue['reason'])}",
                    "", *_quote(clue["text"]), "",
                ])
    if not clue_count:
        lines.extend(["未从已采集消息中提取到提示词线索；这不表示当天没有待办。", ""])
    lines.extend(["## 三、原文依据", ""])
    kind_labels = {"text": "文字", "attachment": "附件", "image": "图片", "unknown": "类型未明"}
    for section in report["sections"]:
        lines.extend([f"### {_escape(section['title'])}", ""])
        if not section["message_count"]:
            lines.extend(["已核对，范围内无符合条件的消息。" if section["status"] == "empty" else "没有可纳入的消息；采集尚不完整，不能确认当天无消息。", ""])
        for conversation in section["conversations"]:
            if not conversation["messages"]:
                continue
            lines.extend([f"#### {_escape(conversation['title'])}", ""])
            for index, message in enumerate(conversation["messages"], 1):
                lines.extend([
                    f"**#{index} · {message['timestamp'][11:19]} · {_escape(_sender(message))} · {kind_labels[message['kind']]}**",
                    "", *_quote(message["text"] or "（未取得可见正文）"), "",
                ])
                if message["source"]:
                    lines.extend([f"来源：{_escape(message['source'])}", ""])
    return "\n".join(lines).rstrip() + "\n"


def build_report(capture: dict, config: dict, run_at: datetime) -> tuple[dict, str]:
    """Return filtered JSON-ready evidence plus a Chinese Markdown report.

    ``run_at`` is the fixed, timezone-aware run start, not the completion time.
    Invalid configuration raises ValueError. Invalid capture/time evidence is
    excluded and reported as partial. Messages sharing text/time but having
    different IDs remain separate. Inputs are never modified.
    """
    if not isinstance(capture, dict) or not isinstance(config, dict):
        raise ValueError("capture 和 config 必须为字典。")
    if not isinstance(run_at, datetime) or run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ValueError("run_at 必须是包含时区的固定运行开始时间。")
    run_at = run_at.astimezone(SHANGHAI)
    for key in ("priority_contact", "self_group"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"配置 {key} 必须为非空字符串。")
    names = config.get("self_names")
    if not isinstance(names, list) or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("配置 self_names 必须为姓名字符串列表，可为空以使用明确的本人标记。")
    self_names = set(names)
    priority, group = config["priority_contact"], config["self_group"]
    selected, start, cutoff, issues = _window(capture, run_at)
    issues.extend(_diagnostics(capture.get("issues")))
    discovery_complete = capture.get("discovery_complete") is True
    if not discovery_complete:
        issues.append("会话列表扫描不完整，可能遗漏当天有消息的单聊。")
    sections = [
        {"key": "priority_contact", "title": f"重点联系人：{priority}"},
        {"key": "self_group", "title": f"指定群本人发言：{group}"},
        {"key": "other_direct", "title": "其他当天有消息的单聊"},
    ]
    for section in sections:
        section.update({"status": "empty", "message_count": 0, "conversations": [], "issues": []})
    if start is None or cutoff is None:
        for section in sections:
            section["status"] = "partial"
    else:
        raw_rows = capture.get("conversations")
        if not isinstance(raw_rows, list):
            raw_rows = []
            issues.append("未取得可核对的会话列表。")
        rows = []
        for row in raw_rows:
            if not isinstance(row, dict):
                issues.append("有会话记录格式无法识别，已排除。")
                continue
            title, kind = _text(row.get("title")), _text(row.get("kind"))
            if kind == "group" and title != group:
                continue
            if kind not in {"direct", "group"}:
                issues.append("有会话未能确认是否为单聊或指定群，已排除。")
                continue
            if not title:
                issues.append("有会话未识别名称，无法确认范围，已排除。")
                continue
            rows.append(row)
        rows = _merge_conversations(rows, issues)
        targets = [(sections[0], priority, "direct", False), (sections[1], group, "group", True)]
        for section, title, kind, self_only in targets:
            matches = [row for row in rows if row["title"] == title and row["kind"] == kind]
            if len(matches) != 1:
                section["status"] = "partial"
                section["issues"].append("发现多个同名会话，无法确认目标，未纳入消息。" if matches else "未找到或未采集目标会话，不能确认当天无消息。")
                continue
            extracted = _extract(matches[0], start, cutoff, self_names, self_only)
            section["conversations"] = [extracted]
            section["message_count"] = extracted["message_count"]
            section["status"] = extracted["status"]
        other = sections[2]
        if not discovery_complete or issues:
            other["status"] = "partial"
        for row in rows:
            if row["kind"] != "direct" or row["title"] == priority:
                continue
            extracted = _extract(row, start, cutoff, self_names, False)
            if extracted["messages"]:
                other["conversations"].append(extracted)
                other["message_count"] += extracted["message_count"]
                if extracted["status"] == "partial":
                    other["status"] = "partial"
            elif extracted["status"] == "partial":
                other["status"] = "partial"
                other["issues"].append("另有单聊未能确认当天消息完整性；未保留未经确认的会话内容。")
        other["conversations"].sort(key=lambda conversation: (conversation["messages"][0]["timestamp"], conversation["title"], conversation["id"]))
        other["issues"] = _unique(other["issues"])
        if other["message_count"] and other["status"] != "partial":
            other["status"] = "complete"
    issues = _unique(issues)
    report = {
        "schema_version": 1, "date": selected, "timezone": "Asia/Shanghai",
        "window_start": start.isoformat() if start else None,
        "cutoff": cutoff.isoformat() if cutoff else None, "run_at": run_at.isoformat(),
        "status": "partial" if issues or any(section["status"] == "partial" for section in sections) else "complete",
        "discovery_complete": discovery_complete, "issues": issues, "sections": sections,
        "counts": {
            "messages": sum(section["message_count"] for section in sections),
            "priority_contact_messages": sections[0]["message_count"],
            "self_group_messages": sections[1]["message_count"],
            "other_direct_messages": sections[2]["message_count"],
            "other_direct_conversations": len(sections[2]["conversations"]),
            "follow_up_clues": sum(len(conversation["follow_up_clues"]) for section in sections for conversation in section["conversations"]),
        },
    }
    return report, _render(report)
