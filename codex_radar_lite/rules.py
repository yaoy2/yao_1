from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .models import RadarState, Signal, isoformat, parse_time


def contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def latest_closed_at(history: list[dict[str, Any]]) -> datetime | None:
    candidates = []
    for item in history:
        if item.get("status") == "closed":
            parsed = parse_time(str(item.get("closed_at", item.get("checked_at", ""))))
            if parsed:
                candidates.append(parsed)
    return max(candidates) if candidates else None


def evaluate(signals: list[Signal], rules: dict[str, Any], history: list[dict[str, Any]] | None = None) -> RadarState:
    history = history or []
    keywords = rules.get("keywords", {})
    open_words = list(keywords.get("open", []))
    closed_words = list(keywords.get("closed", []))
    codex_words = list(keywords.get("codex", []))
    limit_words = list(keywords.get("limit", []))
    incident_words = list(keywords.get("incident", []))

    status = "normal"
    reason = "没有发现足够强的 Codex 重置窗口信号。"
    score = 0
    evidence: list[Signal] = []

    for signal in signals:
        text = f"{signal.title} {signal.summary}"
        is_codex = contains_any(text, codex_words)
        is_limit = contains_any(text, limit_words)
        is_incident = contains_any(text, incident_words)
        if contains_any(text, open_words) and (is_codex or is_limit):
            score += 80 + signal.weight
            evidence.append(signal)
        elif contains_any(text, closed_words) and (is_codex or is_limit):
            score += 65 + signal.weight
            evidence.append(signal)
        elif is_codex and is_limit:
            score += 35 + signal.weight
            evidence.append(signal)
        elif is_codex and is_incident:
            score += 22 + signal.weight
            evidence.append(signal)

    closed_at = latest_closed_at(history)
    if closed_at and datetime.now(timezone.utc) - closed_at < timedelta(hours=int(rules.get("cooldown_hours_after_closed", 24))):
        score = max(0, score - 20)

    if evidence and any(contains_any(f"{item.title} {item.summary}", open_words) for item in evidence):
        status = "open"
        reason = "发现疑似官方重置窗口开启信号。"
    elif evidence and any(contains_any(f"{item.title} {item.summary}", closed_words) for item in evidence):
        status = "closed"
        reason = "发现疑似额度已恢复或窗口关闭信号。"
    elif score >= int(rules.get("high_probability_threshold", 60)):
        status = "high_probability"
        reason = "多个 Codex 限额或事故信号叠加，进入高概率关注。"
    elif score >= int(rules.get("watch_threshold", 25)):
        status = "watch"
        reason = "发现 Codex 相关限额或事故信号，建议保持观察。"

    probability_24h = min(95, max(5, score))
    probability_48h = min(98, max(probability_24h + 8, int(score * 1.25)))
    alert_level = "push" if status in {"high_probability", "open", "closed"} else "silent"
    return RadarState(
        status=status,
        probability_24h=probability_24h,
        probability_48h=probability_48h,
        reason=reason,
        checked_at=isoformat(),
        signals=evidence[:10] if evidence else signals[:5],
        alert_level=alert_level,
    )
