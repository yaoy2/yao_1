"""Independent, parallel model conversations on loopback, Python 3.11+."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit
import uuid
import webbrowser

from adapters import Cancelled, NAMES, provider_status, run_cli, safe_error

ROOT = Path(__file__).resolve().parent
MAX_BODY = 750_000
MAX_CONTEXT = 60_000
TOKEN = secrets.token_urlsafe(32)


def validate_request(data):
    if not isinstance(data, dict):
        raise ValueError("请求格式错误")
    request_id = data.get("request_id", "")
    try:
        uuid.UUID(request_id)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("请求标识无效") from None
    participants = data.get("participants")
    if not isinstance(participants, list) or not participants or len(participants) > len(NAMES):
        raise ValueError(f"请选择 1–{len(NAMES)} 位参与者")
    if any(not isinstance(p, str) or p not in NAMES for p in participants) or len(set(participants)) != len(participants):
        raise ValueError("参与者列表无效")
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("请先输入内容")
    histories = data.get("histories", {})
    if not isinstance(histories, dict) or any(p not in NAMES for p in histories):
        raise ValueError("对话记录格式错误")
    cleaned = {}
    for provider in participants:
        messages = histories.get(provider, [])
        if not isinstance(messages, list) or len(messages) > 200:
            raise ValueError(f"{NAMES[provider]} 对话最多保留 200 条上下文消息，请新建会话")
        lane = []
        for message in messages:
            if not isinstance(message, dict):
                raise ValueError("消息格式错误")
            role, text = (message.get(k) for k in ("role", "text"))
            if role not in ("user", "assistant") or not isinstance(text, str) or not text.strip():
                raise ValueError("消息内容无效")
            lane.append({"role": role, "text": text})
        if len(prompt) + sum(len(m["text"]) for m in lane) > MAX_CONTEXT:
            raise ValueError(f"{NAMES[provider]} 对话已超过 6 万字，请导出并新建会话；系统不会悄悄截断历史")
        cleaned[provider] = lane
    return request_id, prompt, participants, cleaned


def make_prompt(provider, messages, prompt):
    transcript = json.dumps([*messages, {"role": "user", "text": prompt}], ensure_ascii=False)
    if provider == "gemini":
        # Gemini expands @paths before inference, independently of tool permissions.
        # JSON escapes preserve the message while preventing that CLI preprocessing.
        transcript = transcript.replace("@", r"\u0040")
    return (f"你是 {NAMES[provider]}，正在与用户 Sir 进行独立对话。"
            "下面 JSON 仅包含你与用户的对话；assistant 是你此前的回复，user 是用户输入。"
            "结合自己的历史回答最后一条 user 消息，直接给出有用、完整的内容。默认简体中文；用户指定语言或格式时遵从。"
            "这是纯文字对话，不执行命令，不读写文件，不调用工具，不搜索网络。不要声称已完成未执行的操作。"
            "代码、方案和文稿可以直接在回答中给出；长度随任务需要，不强行省略必要内容。\n"
            f"对话记录：\n{transcript}")


class RoomState:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_id = None
        self.cancel = threading.Event()
        self.early_cancels = {}
        self.status_lock = threading.Lock()
        self.cached_status = None
        self.status_time = 0

    def statuses(self, refresh=False):
        with self.status_lock:
            if refresh or self.cached_status is None or time.monotonic() - self.status_time > 30:
                with ThreadPoolExecutor(max_workers=len(NAMES)) as pool:
                    self.cached_status = list(pool.map(provider_status, NAMES))
                self.status_time = time.monotonic()
            return self.cached_status

    def begin(self, request_id):
        with self.lock:
            if self.active_id is not None:
                return False
            self.active_id = request_id
            self.cancel = threading.Event()
            self.early_cancels = {key: value for key, value in self.early_cancels.items() if value > time.monotonic()}
            if request_id in self.early_cancels:
                self.cancel.set()
                del self.early_cancels[request_id]
            return True

    def cancel_request(self, request_id):
        with self.lock:
            if self.active_id == request_id:
                self.cancel.set()
            else:
                self.early_cancels = {key: value for key, value in self.early_cancels.items() if value > time.monotonic()}
                if len(self.early_cancels) >= 100:
                    self.early_cancels.pop(next(iter(self.early_cancels)))
                self.early_cancels[request_id] = time.monotonic() + 60

    def finish(self):
        with self.lock:
            self.active_id = None


STATE = RoomState()


def compare(prompt, participants, histories, emit, cancel, runner=run_cli):
    # Each worker owns a snapshot of one lane. No response enters another lane.
    write_lock = threading.Lock()

    def one(provider):
        started = time.monotonic()

        def send(event):
            with write_lock:
                if cancel.is_set():
                    raise Cancelled()
                emit({**event, "provider": provider, "name": NAMES[provider]})

        try:
            send({"type": "start"})
            text = runner(provider, make_prompt(provider, histories[provider], prompt), send, cancel)
            send({"type": "message", "text": text, "elapsed_ms": round((time.monotonic() - started) * 1000)})
        except Cancelled:
            return
        except Exception as error:
            try:
                detail = safe_error(str(error)) if isinstance(error, (RuntimeError, OSError)) else "本次调用异常，请重试"
                send({"type": "error", "message": detail})
            except Cancelled:
                return

    with ThreadPoolExecutor(max_workers=len(participants)) as pool:
        list(pool.map(one, participants))


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalDiscussionRoom/2.0"

    def log_message(self, *_):
        pass  # Do not put prompts or chat contents in access logs.

    def trusted_host(self):
        return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_port}"

    def send_headers(self, code, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()

    def reply(self, code, value):
        self.send_headers(code, "application/json; charset=utf-8")
        self.wfile.write(json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        if not self.trusted_host():
            return self.reply(403, {"error": "仅允许本机访问"})
        path = urlsplit(self.path).path
        if path == "/":
            page = (ROOT / "index.html").read_text(encoding="utf-8").replace("__ROOM_TOKEN__", TOKEN)
            self.send_headers(200, "text/html; charset=utf-8")
            self.wfile.write(page.encode("utf-8"))
        elif path == "/api/status":
            self.reply(200, {"providers": STATE.statuses("refresh=1" in self.path), "busy": STATE.active_id is not None})
        elif path == "/api/health":
            self.reply(200, {"app": "local-discussion-room", "version": 2})
        else:
            self.reply(404, {"error": "页面不存在"})

    def do_POST(self):
        origin = self.headers.get("Origin")
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"
        if not self.trusted_host() or (origin and origin != expected_origin) or not secrets.compare_digest(self.headers.get("X-Room-Token", ""), TOKEN):
            return self.reply(403, {"error": "会话校验失败，请刷新页面"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError("请求过大或为空")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("请求格式错误")
        except (ValueError, UnicodeError) as error:
            return self.reply(400, {"error": str(error)})
        path = urlsplit(self.path).path
        if path == "/api/cancel":
            try:
                uuid.UUID(data.get("request_id", ""))
            except (ValueError, TypeError, AttributeError):
                return self.reply(400, {"error": "请求标识无效"})
            STATE.cancel_request(data["request_id"])
            return self.reply(200, {"cancelled": True})
        if path != "/api/compare":
            return self.reply(404, {"error": "接口不存在"})
        try:
            request_id, prompt, participants, histories = validate_request(data)
        except ValueError as error:
            return self.reply(400, {"error": str(error)})
        statuses = {item["id"]: item for item in STATE.statuses()}
        unavailable = {p: statuses.get(p, {}).get("detail", "连接状态尚未就绪")
                       for p in participants if not statuses.get(p, {}).get("available")}
        available = [p for p in participants if p not in unavailable]
        if not STATE.begin(request_id):
            return self.reply(409, {"error": "已有回复正在生成，请先停止或等待完成"})
        def emit(event):
            try:
                self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionError, OSError):
                STATE.cancel.set()
                raise Cancelled()

        try:
            self.send_headers(200, "application/x-ndjson; charset=utf-8")
            for provider, detail in unavailable.items():
                emit({"type": "error", "provider": provider, "name": NAMES[provider], "message": detail})
            if available:
                compare(prompt, available, histories, emit, STATE.cancel)
            emit({"type": "done", "cancelled": STATE.cancel.is_set()})
        except Cancelled:
            pass
        except (BrokenPipeError, ConnectionError, OSError):
            STATE.cancel.set()
        finally:
            STATE.finish()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Local discussion room: http://127.0.0.1:{server.server_port}", flush=True)
    if args.open:
        webbrowser.open(f"http://127.0.0.1:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        STATE.cancel.set()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
