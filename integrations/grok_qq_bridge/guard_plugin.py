"""Optional AstrBot plugin SOURCE ONLY; do not copy/load without test approval.

An observer on NapCat cannot stop AstrBot's normal response. This short-lived
guard consumes only the owner's /grok-test prefix before companion listeners.
"""
import json
import os
from pathlib import Path
import re
import socket
import time

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@register("grok_qq_test_guard", "Codex", "限时拦截主人 QQ 测试前缀", "0.1.0")
class GrokQQTestGuard(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        runtime = Path(os.environ["ASTRBOT_ROOT"]).resolve().parent
        receipt = json.loads((runtime / "installation.json").read_text(encoding="utf-8-sig"))
        if str(receipt.get("expected_host", "")).lower() != socket.gethostname().lower():
            raise RuntimeError("QQ test guard runtime computer mismatch")
        owner = str(receipt.get("owner_qq", ""))
        if not re.fullmatch(r"\d{5,12}", owner):
            raise RuntimeError("QQ test guard requires an existing owner binding")
        self.owner_umo = f"whale-qq:FriendMessage:{owner}"
        # Allow setup time before the bridge's maximum fifteen-minute run.
        self.active_until = time.monotonic() + 1800

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE, priority=1000000)
    async def guard(self, event: AstrMessageEvent):
        if time.monotonic() >= self.active_until or event.unified_msg_origin != self.owner_umo:
            return
        # WakingCheckStage may strip '/' from message_str. Components retain the original text.
        text = "".join(str(getattr(part, "text", "")) for part in event.get_messages())
        if re.match(r"^/grok-test(?:\s|$)", text):
            event.stop_event()
