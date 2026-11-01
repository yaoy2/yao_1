"""AstrBot adapter: private chats remain on the existing owner-only profile."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .engine import (
    DISABLE_COMMANDS, ENABLE_COMMANDS, GROUP_SYSTEM_PROMPT, HELP_COMMANDS,
    STATUS_COMMANDS, GroupStore, analysis_prompt, command_text, message_text,
    query_window, valid_id,
)

_active = None


def read_message(event) -> dict:
    raw = event.message_obj.raw_message
    if not isinstance(raw, dict) or raw.get("post_type") != "message":
        raise ValueError("A OneBot message event is required")
    segments = raw.get("message")
    if not isinstance(segments, list):
        raise ValueError("OneBot array messages are required")
    text = "".join(str((p.get("data") or {}).get("text", "")) for p in segments if p.get("type") == "text")
    query, prefixed = command_text(text)
    mentioned = any(p.get("type") == "at" and str((p.get("data") or {}).get("qq")) == event.get_self_id() for p in segments)
    sender = raw.get("sender") or {}
    return {"group_id": valid_id(event.get_group_id()), "sender_id": valid_id(event.get_sender_id()),
            "message_id": str(raw.get("message_id", "")), "time": int(raw.get("time") or time.time()),
            "name": str(sender.get("card") or sender.get("nickname") or event.get_sender_id()),
            "content": message_text(segments), "query": query, "addressed": mentioned or prefixed}


class GroupScope(filter.CustomFilter):
    """Reject unenabled groups before preprocessing can download their media."""
    def filter(self, event, cfg):
        if event.get_platform_id() != "gpt-qq" or event.is_private_chat():
            return False
        if _active is None or event.get_self_id() != _active.bot:
            event.stop_event()
            return False
        try:
            data = read_message(event)
            owner_request = data["sender_id"] == _active.owner and data["addressed"]
            if not _active.store.enabled(data["group_id"]) and not owner_request:
                event.stop_event()
                return False
            event.set_extra("cyber_g_message", data)
            # Keep original text/markers above; only explicitly requested current
            # images need preprocessing. Ordinary record collection does no download.
            keep = {"Plain", "At"}
            if owner_request:
                keep.add("Image")
            event.message_obj.message = [p for p in event.get_messages() if p.type in keep]
            return True
        except Exception as exc:
            logger.error("小屁群助手准入检查失败：%s", type(exc).__name__)
            event.stop_event()
            return False


@register("cyber_g_assistant", "Codex", "按群记录，只响应主人整理与分析", "1.0.0")
class CyberGAssistant(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        runtime = Path(os.environ["ASTRBOT_ROOT"]).resolve().parent
        receipt = json.loads((runtime / "installation.json").read_text(encoding="utf-8-sig"))
        if receipt.get("expected_host", "").lower() != socket.gethostname().lower():
            raise RuntimeError("This GPT QQ installation belongs to another computer")
        self.owner, self.bot = valid_id(receipt["owner_qq"]), valid_id(receipt["bot_qq"])
        if self.owner == self.bot:
            raise ValueError("Owner and bot must be different accounts")
        self.store = GroupStore(runtime / "group_assistant/records.sqlite3")
        self.locks: dict[str, asyncio.Lock] = {}
        global _active
        _active = self

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=10000)
    @filter.custom_filter(GroupScope)
    async def on_group_message(self, event: AstrMessageEvent):
        event.stop_event()  # This profile never falls through to a generic group LLM.
        data = event.get_extra("cyber_g_message")
        if not data:
            return
        group = data["group_id"]
        owner_request = data["sender_id"] == self.owner and data["addressed"]
        query = data["query"]
        if owner_request and query in ENABLE_COMMANDS:
            changed = await asyncio.to_thread(self.store.set_enabled, group, True)
            await event.send(event.plain_result(
                ("本群记录已开启。" if changed else "本群已在记录中。")
                + "从启用后收到的消息开始，保存文字和图片/文件等标记；仅响应主人的整理、分析指令。"
                  "@我说“整理今天的讨论”“提取待办”即可使用；说“停止记录”可停用。"))
            return
        if owner_request and query in DISABLE_COMMANDS:
            await asyncio.to_thread(self.store.set_enabled, group, False)
            await event.send(event.plain_result("本群记录已停止，历史记录保留；重新开启前不再记录或分析本群消息。"))
            return
        enabled = await asyncio.to_thread(self.store.enabled, group)
        if owner_request and query in STATUS_COMMANDS | HELP_COMMANDS:
            await event.send(event.plain_result(
                f"本群记录：{'开启' if enabled else '关闭'}；只响应主人，其他成员消息仅作记录。\n"
                "@我：开始记录 / 停止记录 / 整理今天的讨论 / 提取昨天的待办 / 分析最近7天的进展。\n"
                "也支持 YYYY-MM-DD 日期或日期范围、最近100条。仅整理已收到的本群消息；附件标记不等于已读取正文。"))
            return
        if not enabled:
            if owner_request:
                await event.send(event.plain_result("本群尚未开启记录。请先 @我说“开始记录”；我会从那时起记录本群消息。"))
            return
        try:
            inserted = await asyncio.to_thread(
                self.store.record, group, data["message_id"], data["time"], data["sender_id"],
                data["name"], data["content"], is_request=owner_request)
        except Exception as exc:
            logger.error("小屁群记录写入失败：%s", type(exc).__name__)
            if owner_request:
                await event.send(event.plain_result("这条消息暂未成功写入记录，请稍后重试。"))
            return
        if not owner_request or not inserted:
            return
        request_id = f"{group}:{data['message_id']}"
        if await asyncio.to_thread(self.store.already_handled, request_id):
            return
        lock = self.locks.setdefault(group, asyncio.Lock())
        if lock.locked():
            await event.send(event.plain_result("上一条整理还在进行中，请等我回复后再发新的分析要求。"))
            return
        async with lock:
            try:
                window = query_window(query)
                snapshot = await asyncio.to_thread(self.store.snapshot, group, window)
                images = [p.file or p.url for p in event.get_messages() if p.type == "Image" and (p.file or p.url)]
                snapshot["current_request_images"] = len(images)
                response = await self.context.llm_generate(
                    chat_provider_id="gpt-qq-model", prompt=analysis_prompt(query, snapshot),
                    system_prompt=GROUP_SYSTEM_PROMPT + "\n若另有当前请求的图片输入，可以分析实际可见的当前图片。",
                    contexts=[], tools=None, image_urls=images or None, request_max_retries=1)
                answer = (response.completion_text or "").strip()
                if not answer:
                    raise ValueError("Empty analysis result")
                prefix = f"记录范围：{snapshot['requested_range']}；本次使用{snapshot['included_count']}/{snapshot['matching_count']}条。"
                if snapshot["partial"]:
                    prefix += "记录较多或单条过长，本次仅分析所提供的部分；可缩小日期范围。"
                result = prefix + "\n\n" + answer
                await asyncio.to_thread(self.store.save_analysis, group, request_id, query, snapshot, result)
                if not await asyncio.to_thread(self.store.enabled, group):
                    return  # Stop commands take effect even while the model is running.
                await event.send(event.plain_result(result))
                await asyncio.to_thread(self.store.mark_sent, request_id)
            except ValueError as exc:
                if await asyncio.to_thread(self.store.enabled, group):
                    await event.send(event.plain_result(str(exc) if "日期" in str(exc) or "90天" in str(exc) else "这次未得到有效整理结果，请稍后重试。"))
            except Exception as exc:
                logger.error("小屁群分析失败：%s", type(exc).__name__)
                if await asyncio.to_thread(self.store.enabled, group):
                    await event.send(event.plain_result("消息记录已保留，但这次分析暂未完成，请稍后重试。"))

    async def terminate(self):
        global _active
        if _active is self:
            _active = None
