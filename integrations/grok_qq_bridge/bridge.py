"""Short-lived QQ -> original Grok Bot routine -> QQ verification bridge.

No model API is used. Credentials and QQ identities remain in local files.
Run with the existing companion Python environment; it already has aiohttp.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import socket
import time
from urllib.parse import urlencode, urlsplit


PREFIX = re.compile(r"^/grok-test(?:\s+(.*))?$", re.DOTALL)


class Rejected(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(code)


def emit(event: str, **safe_fields):
    # Callers must only supply status codes, counters and random request IDs.
    print(json.dumps({"event": event, **safe_fields}, ensure_ascii=False), flush=True)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def https_endpoint(value: str, *, callback: bool = False) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment
            or (callback and (parsed.path != "/callback" or parsed.query))):
        raise Rejected("invalid_https_endpoint")
    return value


@dataclass(repr=False)
class Config:
    whale_runtime_root: Path
    grok_webhook_url: str
    grok_webhook_token: str
    public_callback_url: str
    listen_port: int = 6209
    request_timeout_seconds: int = 180
    max_text_chars: int = 1000
    max_messages: int = 3
    run_seconds: int = 900
    astrbot_guard_confirmed: bool = False

    @classmethod
    def load(cls, path: Path):
        raw = read_json(path)
        if raw.get("subscription_preflight_confirmed") is not True:
            raise Rejected("operator_subscription_check_required")
        try:
            checked = datetime.fromisoformat(raw["subscription_preflight_at"])
            if checked.tzinfo is None:
                raise ValueError("timezone required")
            age = (datetime.now(timezone.utc) - checked).total_seconds()
        except (KeyError, TypeError, ValueError):
            raise Rejected("invalid_subscription_check_time") from None
        if not -60 <= age <= 3600:
            raise Rejected("operator_subscription_check_expired")
        config = cls(
            whale_runtime_root=Path(raw["whale_runtime_root"]).resolve(),
            grok_webhook_url=https_endpoint(raw["grok_webhook_url"]),
            grok_webhook_token=raw["grok_webhook_token"],
            public_callback_url=https_endpoint(raw["public_callback_url"], callback=True),
            astrbot_guard_confirmed=raw.get("astrbot_guard_confirmed") is True,
            **{key: raw[key] for key in (
                "listen_port", "request_timeout_seconds", "max_text_chars",
                "max_messages", "run_seconds") if key in raw},
        )
        bounds = {
            "listen_port": (1024, 65535), "request_timeout_seconds": (15, 300),
            "max_text_chars": (1, 2000), "max_messages": (1, 3),
            "run_seconds": (30, 900),
        }
        for key, (minimum, maximum) in bounds.items():
            value = getattr(config, key)
            if type(value) is not int or not minimum <= value <= maximum:
                raise Rejected("invalid_config_limit")
        if not isinstance(config.grok_webhook_token, str) or not config.grok_webhook_token:
            raise Rejected("missing_webhook_token")
        return config


@dataclass(repr=False)
class Pending:
    request_id: str
    callback_token: str
    text: str
    deadline: float
    claimed: bool = False


@dataclass(repr=False)
class Gate:
    bot_id: str
    owner_id: str
    start_epoch: float
    timeout: int = 180
    max_chars: int = 1000
    max_messages: int = 3
    pending: Pending | None = None
    accepted: int = 0
    sent: int = 0
    seen_message_ids: set[str] = field(default_factory=set)
    completed_ids: set[str] = field(default_factory=set)
    closed: bool = False

    def accept(self, event: dict, now: float) -> Pending | None:
        if self.closed or not isinstance(event, dict):
            return None
        if (event.get("post_type") != "message" or event.get("message_type") != "private"
                or str(event.get("self_id", "")) != self.bot_id
                or str(event.get("user_id", "")) != self.owner_id
                or self.bot_id == self.owner_id):
            return None
        event_time = event.get("time")
        if not isinstance(event_time, (int, float)) or event_time < self.start_epoch - 2:
            return None
        parts = event.get("message")
        if not isinstance(parts, list) or not parts:
            return None
        if any(not isinstance(part, dict) or part.get("type") != "text"
               or not isinstance(part.get("data"), dict)
               or not isinstance(part["data"].get("text"), str) for part in parts):
            return None
        match = PREFIX.fullmatch("".join(part["data"]["text"] for part in parts))
        if not match:
            return None
        message_id = str(event.get("message_id", ""))
        if not message_id or message_id in self.seen_message_ids:
            return None
        text = (match.group(1) or "").strip()
        if not text or len(text) > self.max_chars:
            raise Rejected("input_length")
        if self.pending is not None:
            raise Rejected("one_request_already_pending", 409)
        if self.accepted >= self.max_messages:
            raise Rejected("test_message_limit", 429)
        pending = Pending(secrets.token_urlsafe(18), secrets.token_urlsafe(32),
                          text, now + self.timeout)
        self.pending = pending
        self.seen_message_ids.add(message_id)
        self.accepted += 1
        return pending

    def claim(self, payload: dict, now: float) -> Pending:
        if self.closed:
            raise Rejected("bridge_closed", 410)
        if not isinstance(payload, dict) or set(payload) != {"request_id", "callback_token", "text"}:
            raise Rejected("invalid_callback_shape")
        if not all(isinstance(payload[key], str) for key in payload):
            raise Rejected("invalid_callback_types")
        if payload["request_id"] in self.completed_ids:
            raise Rejected("callback_already_consumed", 409)
        pending = self.pending
        if pending is None or not hmac.compare_digest(payload["request_id"].encode(), pending.request_id.encode()):
            raise Rejected("unknown_request", 404)
        if not hmac.compare_digest(payload["callback_token"].encode(), pending.callback_token.encode()):
            raise Rejected("invalid_callback_token", 403)
        if pending.claimed:
            raise Rejected("callback_already_consumed", 409)
        if now >= pending.deadline:
            self.finish(pending.request_id)
            raise Rejected("callback_expired", 410)
        if not payload["text"].strip() or len(payload["text"]) > self.max_chars:
            raise Rejected("reply_length")
        pending.claimed = True  # Consume before any network send; never retry an uncertain send.
        return pending

    def finish(self, request_id: str, *, sent: bool = False):
        if self.pending and self.pending.request_id == request_id:
            self.completed_ids.add(request_id)
            self.pending = None
            self.sent += int(sent)

    def expire(self, now: float) -> str | None:
        if self.pending and not self.pending.claimed and now >= self.pending.deadline:
            request_id = self.pending.request_id
            self.finish(request_id)
            return request_id
        return None


class NapCat:
    base = "http://127.0.0.1:6099/api"

    def __init__(self, session, runtime: Path):
        self.session, self.runtime = session, runtime
        self.headers = {}

    async def post(self, route: str, body: dict):
        async with self.session.post(self.base + route, json=body, headers=self.headers,
                                     allow_redirects=False) as response:
            if response.status != 200:
                raise Rejected("napcat_http_error", 502)
            result = await response.json()
        if result.get("code") != 0:
            raise Rejected("napcat_operation_failed", 502)
        return result.get("data")

    async def preflight(self):
        receipt = read_json(self.runtime / "installation.json")
        if str(receipt.get("expected_host", "")).lower() != socket.gethostname().lower():
            raise Rejected("wrong_runtime_computer")
        bot, owner = str(receipt.get("bot_qq", "")), str(receipt.get("owner_qq", ""))
        if not re.fullmatch(r"\d{5,12}", bot) or not re.fullmatch(r"\d{5,12}", owner) or bot == owner:
            raise Rejected("invalid_local_account_binding")
        access = read_json(self.runtime / "local-access.json")
        digest = hashlib.sha256((access["napcat_token"] + ".napcat").encode()).hexdigest()
        login = await self.post("/auth/login", {"hash": digest})
        if not isinstance(login, dict) or not login.get("Credential"):
            raise Rejected("napcat_authentication_failed")
        self.headers = {"Authorization": "Bearer " + login["Credential"]}
        status = await self.post("/QQLogin/CheckLoginStatus", {})
        info = await self.post("/QQLogin/GetQQLoginInfo", {})
        if (status.get("isLogin") is not True or status.get("coreReady") is not True
                or info.get("online") is not True or str(info.get("uin")) != bot):
            raise Rejected("dedicated_qq_not_online")
        # Bind to the same explicit private whitelist already approved for the companion.
        config = read_json(self.runtime / "state/data/cmd_config.json")
        settings = config.get("platform_settings", {})
        expected_umo = f"whale-qq:FriendMessage:{owner}"
        if settings.get("enable_id_white_list") is not True or expected_umo not in settings.get("id_whitelist", []):
            raise Rejected("owner_private_whitelist_missing")
        return bot, owner

    async def action(self, action: str, params: dict):
        result = await self.post("/Debug/call", {"action": action, "params": params})
        if not isinstance(result, dict) or result.get("status") != "ok" or result.get("retcode") != 0:
            raise Rejected("onebot_action_failed", 502)
        return result.get("data")


async def run(config: Config, *, preflight_only: bool = False):
    import aiohttp
    from aiohttp import web

    if not preflight_only and not config.astrbot_guard_confirmed:
        raise Rejected("active_astrbot_guard_confirmation_required")
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as local:
        napcat = NapCat(local, config.whale_runtime_root)
        bot, owner = await napcat.preflight()
        emit("preflight_ok", qq_online=True, operator_subscription_check_recent=True)
        if preflight_only:
            return
        gate = Gate(bot, owner, time.time(), config.request_timeout_seconds,
                    config.max_text_chars, config.max_messages)
        tasks: set[asyncio.Task] = set()

        async def callback(request):
            try:
                if request.content_type != "application/json":
                    raise Rejected("json_required", 415)
                payload = await request.json()
                pending = gate.claim(payload, time.monotonic())
            except Rejected as exc:
                return web.json_response({"ok": False, "error": exc.code}, status=exc.status)
            except (ValueError, web.HTTPRequestEntityTooLarge):
                return web.json_response({"ok": False, "error": "invalid_json_body"}, status=400)
            sent = False
            try:
                result = await napcat.action("send_private_msg", {
                    "user_id": owner,
                    "message": [{"type": "text", "data": {"text": "[Grok QQ 测试] " + payload["text"]}}],
                })
                sent = isinstance(result, dict) and result.get("message_id") is not None
                emit("qq_reply_sent" if sent else "qq_send_unconfirmed", request_id=pending.request_id)
                return web.json_response({"ok": sent}, status=200 if sent else 502)
            except Exception:
                emit("qq_send_unconfirmed", request_id=pending.request_id)
                return web.json_response({"ok": False, "error": "qq_send_unconfirmed"}, status=502)
            finally:
                gate.finish(pending.request_id, sent=sent)

        app = web.Application(client_max_size=16384)
        app.router.add_post("/callback", callback)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", config.listen_port).start()
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45), trust_env=True) as remote:
                async def submit(pending: Pending):
                    payload = {"request_id": pending.request_id, "text": pending.text,
                               "callback_url": config.public_callback_url,
                               "callback_token": pending.callback_token}
                    try:
                        async with remote.post(config.grok_webhook_url, json=payload,
                                               headers={"Authorization": "Bearer " + config.grok_webhook_token},
                                               allow_redirects=False) as response:
                            emit("webhook_accepted" if response.status in (200, 202) else "webhook_rejected",
                                 request_id=pending.request_id, http_status=response.status)
                    except Exception:
                        emit("webhook_delivery_uncertain", request_id=pending.request_id)
                    # No automatic retry: an uncertain delivery may still have started a paid turn.

                debug = await napcat.post("/Debug/create", {})
                ws_url = "http://127.0.0.1:6099/api/Debug/ws?" + urlencode({
                    "adapterName": debug["adapterName"], "token": debug["token"]})
                async with local.ws_connect(ws_url, max_msg_size=1048576) as websocket:
                    emit("bridge_ready", max_messages=config.max_messages, run_seconds=config.run_seconds)
                    end = time.monotonic() + config.run_seconds
                    while time.monotonic() < end:
                        if expired := gate.expire(time.monotonic()):
                            emit("callback_timeout", request_id=expired)
                        if gate.accepted >= gate.max_messages and gate.pending is None:
                            break
                        try:
                            message = await websocket.receive(timeout=0.5)
                        except asyncio.TimeoutError:
                            continue
                        if message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            emit("qq_event_connection_closed")
                            break
                        if message.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            event = json.loads(message.data)
                            pending = gate.accept(event, time.monotonic())
                        except Rejected as exc:
                            emit("test_message_rejected", reason=exc.code)
                            continue
                        except (ValueError, TypeError):
                            continue
                        if pending:
                            emit("test_message_accepted", request_id=pending.request_id, accepted=gate.accepted)
                            task = asyncio.create_task(submit(pending))
                            tasks.add(task)
                            task.add_done_callback(tasks.discard)
        finally:
            gate.closed = True
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await runner.cleanup()
            # The primary debug adapter can be shared with the user's console.
            # Only close our websocket; NapCat expires an unused adapter itself.
            emit("bridge_stopped", accepted=gate.accepted, replies_sent=gate.sent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--preflight", action="store_true", help="Read account bindings and online state, then exit.")
    args = parser.parse_args()
    try:
        asyncio.run(run(Config.load(args.config), preflight_only=args.preflight))
    except KeyboardInterrupt:
        pass
    except Rejected as exc:
        emit("bridge_failed", reason=exc.code)
        raise SystemExit(1) from None
    except Exception as exc:
        # Exception messages may contain a credential-bearing URL. Log only its class.
        emit("bridge_failed", reason=type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
