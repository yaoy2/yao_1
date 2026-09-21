"""Native-share upload API with bounded, temporary transit storage.

HTTPS protects this route; this native path is not end-to-end encrypted. The
multipart parser's owned temporary file is retained only until L acknowledges
its exact size/hash or the queue expires. No payload is persisted in the repo,
sent to GitHub, or logged. Deploy as part of the official Streamlit ASGI app.
"""

import asyncio
from contextlib import asynccontextmanager, suppress
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
import secrets
import threading
import time

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.routing import Route


PREFIX = "/phone-transfer-api/v1"
MIB = 1024 * 1024
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")


def _hex(value, pattern=_HEX64):
    return type(value) is str and bool(pattern.fullmatch(value))


def _error(code, status=400):
    return JSONResponse({"ok": False, "error": code}, status_code=status,
                        headers={"Cache-Control": "no-store"})


class _BodyTooLarge(MultiPartException):
    pass


class _OwnedMultipartParser(MultiPartParser):
    """Close parser-owned handles on disconnect/cancellation as well as errors.

    Starlette closes this list for MultiPartException only. Keeping cleanup here
    also covers a client disconnect while a partly received file is on disk.
    """

    def close_except(self, keep=None):
        for handle in self._files_to_close_on_error:
            if handle is not keep:
                handle.close()

    async def parse(self):
        try:
            return await super().parse()
        except BaseException:
            self.close_except()
            raise


@dataclass(slots=True, repr=False)
class _File:
    id: str
    name: str
    size: int
    sha256: str
    stream: object
    created: float
    result: Future = field(default_factory=Future)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def public(self):
        return {"id": self.id, "name": self.name, "size": self.size, "sha256": self.sha256}


@dataclass(slots=True, repr=False)
class _Receiver:
    receiver_hash: str
    upload_hash: str
    seen: float
    files: OrderedDict = field(default_factory=OrderedDict)
    receipts: OrderedDict = field(default_factory=OrderedDict)
    reserved: int = 0
    uploading: bool = False


class PhoneTransferRegistry:
    def __init__(
        self, *, clock=time.monotonic, ack_timeout=20, heartbeat_ttl=30,
        file_ttl=600, receiver_ttl=86400, max_file_bytes=200 * MIB,
        max_body_bytes=201 * MIB, max_global_bytes=512 * MIB,
        max_room_bytes=256 * MIB, max_rooms=128, max_room_files=128,
        max_global_files=1024,
        upload_idle_timeout=120,
    ):
        self.clock = clock
        self.ack_timeout = ack_timeout
        self.heartbeat_ttl = heartbeat_ttl
        self.file_ttl = file_ttl
        self.receiver_ttl = receiver_ttl
        self.max_file_bytes = max_file_bytes
        self.max_body_bytes = max_body_bytes
        self.max_global_bytes = max_global_bytes
        self.max_room_bytes = max_room_bytes
        self.max_rooms = max_rooms
        self.max_room_files = max_room_files
        self.max_global_files = max_global_files
        self.upload_idle_timeout = upload_idle_timeout
        self._receivers = {}
        self._reserved = 0
        self._lock = threading.RLock()
        self.routes = [
            Route(PREFIX + "/health", self.health, methods=["GET"]),
            Route(PREFIX + "/receivers/{room}", self.register, methods=["POST"]),
            Route(PREFIX + "/receivers/{room}/pending", self.pending, methods=["GET"]),
            Route(PREFIX + "/receivers/{room}/files/{file_id}", self.download, methods=["GET"]),
            Route(PREFIX + "/receivers/{room}/files/{file_id}/ack", self.acknowledge, methods=["POST"]),
            Route(PREFIX + "/upload/{room}", self.upload, methods=["POST"]),
        ]

    def _discard(self, receiver, item):
        receiver.files.pop(item.id, None)
        receiver.reserved -= item.size
        self._reserved -= item.size
        with item.lock:
            item.stream.close()
        if not item.result.done():
            item.result.set_result(None)

    def _expire(self):
        now = self.clock()
        with self._lock:
            for room, receiver in list(self._receivers.items()):
                for item in list(receiver.files.values()):
                    if now - item.created >= self.file_ttl:
                        self._discard(receiver, item)
                for file_id, receipt in list(receiver.receipts.items()):
                    if now - receipt["created"] >= self.file_ttl:
                        del receiver.receipts[file_id]
                if not receiver.files and not receiver.uploading and now - receiver.seen >= self.receiver_ttl:
                    del self._receivers[room]

    def expire(self):
        """Dispose expired staging; callers may also schedule this in lifespan."""
        self._expire()

    def close(self):
        """Dispose remaining staging when the serving process shuts down."""
        with self._lock:
            for receiver in self._receivers.values():
                for item in list(receiver.files.values()):
                    self._discard(receiver, item)
            self._receivers.clear()
            self._reserved = 0

    @staticmethod
    def _token_hash(request):
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not _hex(token):
            return None
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def _receiver(self, request):
        self._expire()
        room = request.path_params["room"]
        token_hash = self._token_hash(request)
        if not _hex(room) or token_hash is None:
            return None
        with self._lock:
            receiver = self._receivers.get(room)
            if receiver is None or not hmac.compare_digest(receiver.receiver_hash, token_hash):
                return None
            receiver.seen = self.clock()
            return receiver

    @staticmethod
    async def _small_json(request):
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 4096:
                raise ValueError("invalid_json")
            data.extend(chunk)
        value = json.loads(data)
        if type(value) is not dict:
            raise ValueError("invalid_json")
        return value

    async def health(self, request):
        self._expire()
        return JSONResponse({"ok": True, "version": 1})

    async def register(self, request):
        self._expire()
        room = request.path_params["room"]
        token_hash = self._token_hash(request)
        # The public room is a commitment to L's private receiver token. A
        # sender cannot claim the same room after restart or expiry.
        if not _hex(room) or token_hash is None or not hmac.compare_digest(room, token_hash):
            return _error("unauthorized", 401)
        with self._lock:
            existing = self._receivers.get(room)
            if existing and not hmac.compare_digest(existing.receiver_hash, token_hash):
                return _error("unauthorized", 401)
        try:
            body = await self._small_json(request)
        except (ValueError, ClientDisconnect):
            return _error("invalid_request")
        upload_hash = body.get("upload_token_hash")
        if set(body) != {"upload_token_hash"} or not _hex(upload_hash) or hmac.compare_digest(upload_hash, token_hash):
            return _error("invalid_request")
        with self._lock:
            existing = self._receivers.get(room)
            if existing:
                if not hmac.compare_digest(existing.receiver_hash, token_hash):
                    return _error("unauthorized", 401)
                if not hmac.compare_digest(existing.upload_hash, upload_hash):
                    return _error("token_conflict", 409)
                existing.seen = self.clock()
            else:
                if len(self._receivers) >= self.max_rooms:
                    return _error("capacity", 503)
                self._receivers[room] = _Receiver(token_hash, upload_hash, self.clock())
        return JSONResponse({"ok": True})

    async def pending(self, request):
        receiver = self._receiver(request)
        if receiver is None:
            return _error("unauthorized", 401)
        with self._lock:
            files = [item.public() for item in receiver.files.values()]
        return JSONResponse({"ok": True, "files": files}, headers={"Cache-Control": "no-store"})

    async def download(self, request):
        receiver = self._receiver(request)
        if receiver is None:
            return _error("unauthorized", 401)
        file_id = request.path_params["file_id"]
        with self._lock:
            item = receiver.files.get(file_id) if _hex(file_id, _HEX32) else None
        if item is None:
            return _error("not_found", 404)

        def read_at(offset):
            with item.lock:
                if item.stream.closed:
                    return b""
                item.stream.seek(offset)
                return item.stream.read(MIB)

        async def content():
            offset = 0
            while offset < item.size:
                chunk = await run_in_threadpool(read_at, offset)
                if not chunk:
                    break
                offset += len(chunk)
                yield chunk

        return StreamingResponse(content(), media_type="application/octet-stream",
                                 headers={"Content-Length": str(item.size), "Cache-Control": "no-store"})

    async def acknowledge(self, request):
        receiver = self._receiver(request)
        if receiver is None:
            return _error("unauthorized", 401)
        try:
            body = await self._small_json(request)
        except (ValueError, ClientDisconnect):
            return _error("invalid_request")
        if (set(body) != {"sha256", "size", "name", "folder"} or not _hex(body["sha256"])
                or type(body["size"]) is not int or body["size"] < 0
                or any(type(body[key]) is not str or not 0 < len(body[key]) <= 1024 for key in ("name", "folder"))):
            return _error("invalid_request")
        file_id = request.path_params["file_id"]
        with self._lock:
            item = receiver.files.get(file_id)
            previous = receiver.receipts.get(file_id)
            expected = item.public() if item else previous
            if expected is None:
                return _error("not_found", 404)
            if body["size"] != expected["size"] or not hmac.compare_digest(body["sha256"], expected["sha256"]):
                return _error("content_mismatch", 409)
            if item:
                receipt = {**body, "created": self.clock()}
                receiver.receipts[file_id] = receipt
                while len(receiver.receipts) > 128:
                    receiver.receipts.popitem(last=False)
                item.result.set_result(receipt)
                self._discard(receiver, item)
        return JSONResponse({"ok": True})

    async def upload(self, request):
        self._expire()
        room = request.path_params["room"]
        token_hash = self._token_hash(request)
        with self._lock:
            receiver = self._receivers.get(room) if _hex(room) else None
            if receiver is None or token_hash is None or not hmac.compare_digest(receiver.upload_hash, token_hash):
                return _error("unauthorized", 401)
            if self.clock() - receiver.seen >= self.heartbeat_ttl:
                return _error("receiver_offline", 409)
            if receiver.uploading:
                return _error("upload_busy", 429)
            if (receiver.reserved + self.max_file_bytes > self.max_room_bytes
                    or self._reserved + self.max_file_bytes > self.max_global_bytes
                    or len(receiver.files) >= self.max_room_files
                    or sum(len(r.files) + int(r.uploading) for r in self._receivers.values()) >= self.max_global_files):
                return _error("capacity", 503)
            receiver.uploading = True
            receiver.reserved += self.max_file_bytes
            self._reserved += self.max_file_bytes
        committed = False
        parser = None
        kept_stream = None
        try:
            content_length = request.headers.get("content-length")
            if content_length is not None and (not content_length.isdigit() or int(content_length) > self.max_body_bytes):
                return _error("too_large", 413)
            if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
                return _error("multipart_required", 415)

            async def bounded_body():
                received = 0
                stream = request.stream().__aiter__()
                while True:
                    try:
                        chunk = await asyncio.wait_for(anext(stream), self.upload_idle_timeout)
                    except StopAsyncIteration:
                        break
                    received += len(chunk)
                    if received > self.max_body_bytes:
                        raise _BodyTooLarge("too_large")
                    yield chunk

            parser = _OwnedMultipartParser(request.headers, bounded_body(), max_files=1, max_fields=1, max_part_size=4096)
            form = await parser.parse()
            parts = list(form.multi_items())
            uploaded = form.get("file")
            if (not isinstance(uploaded, UploadFile) or len(parts) not in (1, 2)
                    or any(key not in {"file", "name"} for key, _ in parts)
                    or sum(key == "file" for key, _ in parts) != 1
                    or "name" in form and type(form["name"]) is not str):
                return _error("invalid_multipart")
            name = form.get("name", uploaded.filename)
            if type(name) is not str or not 0 < len(name) <= 1024:
                return _error("invalid_name")
            if uploaded.size is None or uploaded.size > self.max_file_bytes:
                return _error("too_large", 413)
            # The parser uses SpooledTemporaryFile. Roll it into its anonymous
            # TemporaryFile before ownership passes to the staging queue.
            await run_in_threadpool(uploaded.file.rollover)
            digest = hashlib.sha256()
            size = 0
            while chunk := await uploaded.read(MIB):
                size += len(chunk)
                if size > self.max_file_bytes:
                    return _error("too_large", 413)
                digest.update(chunk)
            await uploaded.seek(0)
            item = _File(secrets.token_hex(16), name, size, digest.hexdigest(), uploaded.file, self.clock())
            with self._lock:
                receiver.files[item.id] = item
                receiver.reserved += size - self.max_file_bytes
                self._reserved += size - self.max_file_bytes
                receiver.uploading = False
                committed = True
                kept_stream = item.stream
        except _BodyTooLarge:
            return _error("too_large", 413)
        except (MultiPartException, ValueError):
            return _error("invalid_multipart")
        except ClientDisconnect:
            return _error("upload_interrupted", 400)
        except TimeoutError:
            return _error("upload_idle_timeout", 408)
        except OSError:
            return _error("temporary_storage_unavailable", 503)
        finally:
            if parser is not None:
                parser.close_except(kept_stream)
            if not committed:
                with self._lock:
                    receiver.uploading = False
                    receiver.reserved -= self.max_file_bytes
                    self._reserved -= self.max_file_bytes
        try:
            receipt = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(item.result)), timeout=self.ack_timeout)
        except TimeoutError:
            return PlainTextResponse("已上传，等待办公电脑 L 保存；请查看接收页确认", status_code=202,
                                     headers={"Cache-Control": "no-store"})
        if receipt is None:
            return _error("upload_expired", 410)
        return PlainTextResponse(f"已保存到办公电脑 L：{receipt['folder']}/{receipt['name']}",
                                 headers={"Cache-Control": "no-store"})


registry = PhoneTransferRegistry()
routes = registry.routes


@asynccontextmanager
async def lifespan(app):
    async def cleanup():
        while True:
            await asyncio.sleep(15)
            await run_in_threadpool(registry.expire)

    task = asyncio.create_task(cleanup())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await run_in_threadpool(registry.close)
