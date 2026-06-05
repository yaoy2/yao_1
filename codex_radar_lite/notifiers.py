from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.parse import quote_plus

import requests

from .models import RadarState


def should_push(previous: RadarState | None, current: RadarState) -> bool:
    if current.alert_level != "push":
        return False
    if previous is None:
        return True
    return previous.status != current.status or previous.reason != current.reason


def signed_webhook(webhook: str, secret: str | None) -> str:
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(digest).decode("utf-8"))
    joiner = "&" if "?" in webhook else "?"
    return f"{webhook}{joiner}timestamp={timestamp}&sign={sign}"


def build_dingtalk_markdown(state: RadarState) -> dict[str, Any]:
    lines = [
        f"### Codex Radar Lite: {state.status}",
        "",
        f"- 24小时概率：{state.probability_24h}%",
        f"- 48小时概率：{state.probability_48h}%",
        f"- 判断时间：{state.checked_at}",
        f"- 原因：{state.reason}",
    ]
    for signal in state.signals[:3]:
        lines.append(f"- 证据：[{signal.title}]({signal.url})")
    return {
        "msgtype": "markdown",
        "markdown": {"title": f"Codex Radar Lite: {state.status}", "text": "\n".join(lines)},
    }


def send_dingtalk(state: RadarState) -> str:
    webhook = os.getenv("DINGTALK_WEBHOOK", "").strip()
    secret = os.getenv("DINGTALK_SECRET", "").strip() or None
    if not webhook:
        return "skipped:no_webhook"
    response = requests.post(
        signed_webhook(webhook, secret),
        data=json.dumps(build_dingtalk_markdown(state), ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("errcode") != 0:
        raise RuntimeError(f"DingTalk rejected message: {result}")
    return "sent"
