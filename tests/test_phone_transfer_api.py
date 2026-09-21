"""Native upload API checks use in-process ASGI only, never a live server."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.testclient import TestClient

from utils.phone_transfer_api import DEFAULT_PUBLIC_BASE, PREFIX, SHORTCUT_FILE, PhoneTransferRegistry, server_error


RECEIVER_TOKEN = "2" * 64
ROOM = hashlib.sha256(RECEIVER_TOKEN.encode()).hexdigest()
UPLOAD_TOKEN = "3" * 64
UPLOAD_HASH = hashlib.sha256(UPLOAD_TOKEN.encode()).hexdigest()


def auth(token):
    return {"authorization": "Bearer " + token}


class Clock:
    now = 0

    def __call__(self):
        return self.now


def multipart(payload, name="picture.HEIC", boundary="test-boundary"):
    return (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode() + payload + f"\r\n--{boundary}--\r\n".encode()


class PhoneTransferApiTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.registry = PhoneTransferRegistry(clock=self.clock, ack_timeout=0.001,
                                             max_file_bytes=1024, max_body_bytes=4096,
                                             max_room_bytes=4096, max_global_bytes=8192,
                                             public_base="https://fixture.invalid" + PREFIX)
        self.app = Starlette(routes=self.registry.routes)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.cleanup_staged)
        self.base = PREFIX + "/receivers/" + ROOM
        self.assertEqual(self.register().status_code, 200)

    def cleanup_staged(self):
        self.clock.now += 100000
        self.registry._expire()

    def register(self, token=RECEIVER_TOKEN, upload_hash=UPLOAD_HASH, room=ROOM):
        return self.client.post(PREFIX + "/receivers/" + room,
                                json={**auth(token), "upload_token_hash": upload_hash})

    def test_public_install_delivers_the_signed_generic_package(self):
        response = self.client.get(PREFIX + "/install/office-L.shortcut")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, SHORTCUT_FILE.read_bytes())
        self.assertTrue(response.content.startswith(b"AEA1"))
        self.assertEqual(response.headers["content-type"], "application/x-apple-shortcut")
        self.assertIn("filename*=utf-8''", response.headers["content-disposition"])
        self.assertNotIn(UPLOAD_TOKEN.encode(), response.content)
        self.assertEqual(self.client.head(PREFIX + "/install/office-L.shortcut").content, b"")

    def authorize(self, token=UPLOAD_TOKEN, room=ROOM):
        return self.client.post(PREFIX + "/upload/" + room + "/authorize", json=auth(token))

    def ticket(self):
        response = self.authorize()
        self.assertEqual(response.status_code, 200)
        return response.text.rsplit("/", 1)[-1]

    def upload(self, payload=b"original\x00\xff", name="相册照片.HEIC", token=UPLOAD_TOKEN, **kwargs):
        authorized = self.authorize(token)
        if authorized.status_code != 200:
            return authorized
        return self.client.post(authorized.text,
                                files={"file": (name, payload, "application/octet-stream")}, **kwargs)

    def pending(self):
        return self.client.post(self.base + "/pending", json=auth(RECEIVER_TOKEN)).json()["files"]

    def test_shutdown_closes_remaining_temporary_files(self):
        self.upload()
        staged = next(iter(self.registry._receivers[ROOM].files.values()))
        self.registry.close()
        self.assertTrue(staged.stream.closed)
        self.assertEqual(self.registry._reserved, 0)
        self.assertEqual(self.registry._receivers, {})

    def ack(self, item, **changes):
        body = {**auth(RECEIVER_TOKEN), "sha256": item["sha256"], "size": item["size"],
                "name": "001_" + item["name"], "folder": "2026-09-21/batch"}
        body.update(changes)
        return self.client.post(self.base + "/files/" + item["id"] + "/ack",
                                json=body)

    async def raw_upload(self, receive, ticket=None, room=ROOM, content_length=None):
        if ticket is None:
            ticket = self.ticket()
        headers = [(b"content-type", b"multipart/form-data; boundary=test-boundary")]
        if content_length is not None:
            headers.append((b"content-length", str(content_length).encode()))
        path = PREFIX + "/upload/" + room + "/" + ticket
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
                 "http_version": "1.1", "method": "POST", "scheme": "https", "path": path,
                 "raw_path": path.encode(), "query_string": b"", "root_path": "", "headers": headers,
                 "client": ("test", 1234), "server": ("test", 443)}
        messages = []

        async def send(message):
            messages.append(message)

        await self.app(scope, receive, send)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, body

    def test_health_and_immutable_distinct_credentials(self):
        self.assertEqual(self.client.get(PREFIX + "/health").json(), {"ok": True, "version": 2})
        self.assertEqual(self.register().status_code, 200)
        self.assertEqual(self.register(token=UPLOAD_TOKEN).status_code, 403)
        self.assertEqual(self.register(upload_hash="f" * 64).status_code, 409)
        receiver_hash = hashlib.sha256(RECEIVER_TOKEN.encode()).hexdigest()
        self.assertEqual(self.register(upload_hash=receiver_hash).status_code, 400)
        # A fresh registry must reject a known room claimed with a send token.
        fresh = TestClient(Starlette(routes=PhoneTransferRegistry().routes))
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.post(self.base,
                                    json={**auth(UPLOAD_TOKEN), "upload_token_hash": "f" * 64}).status_code, 403)

    def test_send_token_cannot_claim_list_download_or_ack(self):
        self.assertEqual(self.upload(token=RECEIVER_TOKEN).status_code, 403)
        self.assertEqual(self.upload().status_code, 202)
        item = self.pending()[0]
        for suffix in ("/pending", "/files/" + item["id"]):
            self.assertEqual(self.client.post(self.base + suffix, json=auth(UPLOAD_TOKEN)).status_code, 403)
        self.assertEqual(self.client.post(self.base + "/files/" + item["id"] + "/ack",
                                         json=auth(UPLOAD_TOKEN)).status_code, 403)
        self.assertEqual(len(self.pending()), 1)

    def test_body_authorization_is_required_and_headers_are_not_a_fallback(self):
        self.assertEqual(self.client.post(self.base + "/pending", json={},
                                         headers={"Authorization": "Bearer " + RECEIVER_TOKEN}).status_code, 403)
        self.assertEqual(self.client.get(self.base + "/pending").status_code, 405)
        self.assertEqual(self.client.post(PREFIX + "/upload/" + ROOM + "/authorize", json={},
                                         headers={"Authorization": "Bearer " + UPLOAD_TOKEN}).status_code, 403)
        self.assertEqual(self.client.post(self.base + "/pending", json={"authorization": 123}).status_code, 403)

    def test_ticket_urls_use_fixed_configured_origin_and_never_long_term_tokens(self):
        self.registry.public_base = DEFAULT_PUBLIC_BASE
        response = self.client.post(PREFIX + "/upload/" + ROOM + "/authorize", json=auth(UPLOAD_TOKEN),
                                    headers={"Host": "attacker.invalid", "X-Forwarded-Host": "attacker.invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertTrue(response.text.startswith(DEFAULT_PUBLIC_BASE + "/upload/" + ROOM + "/"))
        ticket = response.text.rsplit("/", 1)[-1]
        self.assertRegex(ticket, r"^[0-9a-f]{64}$")
        self.assertNotIn(UPLOAD_TOKEN, response.text)
        self.assertNotIn(RECEIVER_TOKEN, response.text)
        self.assertEqual(urlsplit(response.text).query, "")
        self.assertEqual(self.registry._reserved, 0)

    def test_replacement_expiration_and_reuse_reject_before_multipart_body(self):
        first = self.ticket()
        replacement = self.ticket()
        self.assertNotEqual(first, replacement)

        async def no_read():
            raise AssertionError("Rejected tickets must not read multipart bodies")

        self.assertEqual(asyncio.run(self.raw_upload(no_read, ticket=first))[0], 403)
        response = self.client.post(PREFIX + "/upload/" + ROOM + "/" + replacement,
                                    files={"file": ("a.HEIC", b"untouched")})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(asyncio.run(self.raw_upload(no_read, ticket=replacement))[0], 403)
        expiring = self.ticket()
        self.clock.now += 90
        self.registry.expire()
        self.assertIsNone(self.registry._receivers[ROOM].ticket)
        self.assertEqual(asyncio.run(self.raw_upload(no_read, ticket=expiring))[0], 403)
        self.register()
        self.assertEqual(len(self.pending()), 1)

    def test_ticket_is_room_bound_and_bad_cross_room_attempt_does_not_consume_it(self):
        token = "a" * 64
        other_room = hashlib.sha256(token.encode()).hexdigest()
        self.assertEqual(self.register(token=token, room=other_room).status_code, 200)
        ticket = self.ticket()

        async def no_read():
            raise AssertionError("Cross-room tickets must not read multipart bodies")

        self.assertEqual(asyncio.run(self.raw_upload(no_read, room=other_room, ticket=ticket))[0], 403)
        response = self.client.post(PREFIX + "/upload/" + ROOM + "/" + ticket,
                                    files={"file": ("a.HEIC", b"original")})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(self.pending()), 1)

    def test_debug_probes_and_exception_details_are_not_exposed(self):
        response = self.client.get(PREFIX + "/health?probe=headers", headers={"Authorization": "anything"})
        self.assertEqual(response.json(), {"ok": True, "version": 2})
        response = asyncio.run(server_error(None, ValueError(UPLOAD_TOKEN)))
        self.assertEqual(json.loads(response.body), {"ok": False, "error": "internal_error"})

    def test_unauthorized_offline_and_capacity_stop_before_body_reads(self):
        async def no_read():
            raise AssertionError("Unauthorized/offline/full uploads must not consume body")

        self.assertEqual(asyncio.run(self.raw_upload(no_read, ticket="f" * 64))[0], 403)
        ticket = self.ticket()
        self.clock.now = 31
        self.assertEqual(asyncio.run(self.raw_upload(no_read, ticket=ticket))[0], 409)
        self.register()
        ticket = self.ticket()
        self.registry.max_global_bytes = 100
        self.assertEqual(asyncio.run(self.raw_upload(no_read, ticket=ticket))[0], 503)
        self.assertEqual(self.registry._reserved, 0)

    def test_original_bytes_names_order_hash_and_explicit_name_are_preserved(self):
        payloads = [b"\x00\xffHEIC\x00", b"different JPEG bytes", b""]
        names = ["照片.HEIC", "照片.HEIC", "空文件.txt"]
        for name, data in zip(names, payloads):
            response = self.upload(data, name)
            self.assertEqual(response.status_code, 202)
            self.assertNotIn("已保存到", response.text)
        files = self.pending()
        self.assertEqual([f["name"] for f in files], names)
        self.assertEqual(len({f["id"] for f in files}), 3)
        for item, data in zip(files, payloads):
            self.assertEqual(item["size"], len(data))
            self.assertEqual(item["sha256"], hashlib.sha256(data).hexdigest())
            response = self.client.post(self.base + "/files/" + item["id"], json=auth(RECEIVER_TOKEN))
            self.assertEqual(response.content, data)
            self.assertEqual(response.headers["cache-control"], "no-store")
        self.upload(b"named", "blob", data={"name": "真实原名.PNG"})
        self.assertEqual(self.pending()[-1]["name"], "真实原名.PNG")

    def test_wrong_ack_keeps_file_correct_ack_closes_it_and_retries_are_safe(self):
        self.upload()
        item = self.pending()[0]
        staged = self.registry._receivers[ROOM].files[item["id"]]
        self.assertFalse(staged.stream.closed)
        self.assertEqual(self.ack(item, sha256="0" * 64).status_code, 409)
        self.assertEqual(self.ack(item, size=item["size"] + 1).status_code, 409)
        self.assertFalse(staged.stream.closed)
        self.assertEqual(len(self.pending()), 1)
        self.assertEqual(self.ack(item).status_code, 200)
        self.assertNotIn("authorization", self.registry._receivers[ROOM].receipts[item["id"]])
        self.assertNotIn(RECEIVER_TOKEN, json.dumps(self.registry._receivers[ROOM].receipts))
        self.assertTrue(staged.stream.closed)
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.registry._reserved, 0)
        self.assertEqual(self.ack(item).status_code, 200)
        self.assertEqual(self.ack(item, sha256="0" * 64).status_code, 409)

    def test_success_text_requires_verified_ack_while_upload_waits(self):
        self.registry.ack_timeout = 2
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(self.upload)
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                files = self.pending()
                if files:
                    break
                time.sleep(0.005)
            self.assertTrue(files)
            self.assertFalse(result.done())
            self.assertEqual(self.ack(files[0]).status_code, 200)
            response = result.result(timeout=2)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.startswith("已保存到办公电脑 L"))

    def test_file_ttl_closes_only_staging_and_empty_receiver_expires(self):
        self.upload()
        item = self.pending()[0]
        staged = self.registry._receivers[ROOM].files[item["id"]]
        self.clock.now = 601
        self.client.get(PREFIX + "/health")
        self.assertTrue(staged.stream.closed)
        self.assertEqual(self.registry._reserved, 0)
        self.assertEqual(self.pending(), [])
        self.clock.now = 90000
        self.client.get(PREFIX + "/health")
        self.assertNotIn(ROOM, self.registry._receivers)

    def test_file_size_limit_is_inclusive_and_oversize_releases_reservation(self):
        self.registry.max_file_bytes = 32
        self.assertEqual(self.upload(b"A" * 32).status_code, 202)
        self.assertEqual(self.upload(b"B" * 33).status_code, 413)
        self.assertEqual(self.registry._reserved, 32)
        self.assertEqual(len(self.pending()), 1)

    def test_actual_body_limit_is_checked_without_trusting_content_length(self):
        self.registry.max_body_bytes = 200
        data = multipart(b"A" * 200)
        chunks = iter((data[:150], data[150:]))

        async def receive():
            chunk = next(chunks)
            return {"type": "http.request", "body": chunk, "more_body": len(chunk) == 150}

        status, _ = asyncio.run(self.raw_upload(receive, content_length=100))
        self.assertEqual(status, 413)
        self.assertEqual(self.registry._reserved, 0)
        self.assertEqual(self.pending(), [])

    def test_interrupted_multipart_closes_all_temporary_handles(self):
        opened = []
        real_spool = tempfile.SpooledTemporaryFile

        def spool(*args, **kwargs):
            result = real_spool(*args, **kwargs)
            opened.append(result)
            return result

        calls = 0
        unfinished = multipart(b"partial").split(b"\r\n--test-boundary--")[0]

        async def receive():
            nonlocal calls
            calls += 1
            return {"type": "http.request", "body": unfinished, "more_body": True} if calls == 1 else {"type": "http.disconnect"}

        with patch("starlette.formparsers.SpooledTemporaryFile", side_effect=spool):
            self.assertEqual(asyncio.run(self.raw_upload(receive))[0], 400)
        self.assertTrue(opened)
        self.assertTrue(all(f.closed for f in opened))
        self.assertEqual(self.registry._reserved, 0)
        self.assertFalse(self.registry._receivers[ROOM].uploading)

    def test_stalled_body_times_out_and_next_upload_can_proceed(self):
        self.registry.upload_idle_timeout = 0.01
        opened = []
        real_spool = tempfile.SpooledTemporaryFile

        def spool(*args, **kwargs):
            result = real_spool(*args, **kwargs)
            opened.append(result)
            return result

        calls = 0
        unfinished = multipart(b"partial").split(b"\r\n--test-boundary--")[0]

        async def receive():
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"type": "http.request", "body": unfinished, "more_body": True}
            await asyncio.Event().wait()

        with patch("starlette.formparsers.SpooledTemporaryFile", side_effect=spool):
            self.assertEqual(asyncio.run(self.raw_upload(receive))[0], 408)
        self.assertTrue(opened)
        self.assertTrue(all(handle.closed for handle in opened))
        self.assertEqual(self.registry._reserved, 0)
        self.assertFalse(self.registry._receivers[ROOM].uploading)
        self.assertEqual(self.upload().status_code, 202)

    def test_invalid_multipart_and_parse_failure_do_not_leak_staging(self):
        cases = [
            {"files": [("file", ("a", b"a")), ("file", ("b", b"b"))]},
            {"files": {"unexpected": ("a", b"a")}},
            {"files": {"file": ("a", b"a")}, "data": {"name": "x", "extra": "bad"}},
            {"files": {"file": ("a", b"a")}, "data": {"name": "x" * 5000}},
        ]
        for index, args in enumerate(cases):
            response = self.client.post(self.authorize().text, **args)
            self.assertEqual(response.status_code, 413 if index == 3 else 400)
            self.assertEqual(self.registry._reserved, 0)
        self.assertEqual(self.pending(), [])

    def test_one_active_upload_per_room_and_reservation_before_parse(self):
        ticket = self.ticket()
        async def exercise():
            began = asyncio.Event()
            release = asyncio.Event()

            async def slow_receive():
                began.set()
                await release.wait()
                return {"type": "http.disconnect"}

            async def no_read():
                raise AssertionError("Second request body must not be consumed")

            pending = asyncio.create_task(self.raw_upload(slow_receive, ticket=ticket))
            await began.wait()
            self.assertEqual(self.registry._reserved, self.registry.max_file_bytes)
            self.assertEqual(self.authorize().status_code, 429)
            second = await self.raw_upload(no_read, ticket=ticket)
            release.set()
            first = await pending
            return first, second

        first, second = asyncio.run(exercise())
        self.assertEqual(first[0], 400)
        self.assertEqual(second[0], 403)
        self.assertEqual(self.registry._reserved, 0)

    def test_room_global_and_metadata_capacity_are_bounded(self):
        self.registry.max_room_bytes = 1024
        self.upload(b"A")
        self.assertEqual(self.upload(b"B").status_code, 503)
        self.ack(self.pending()[0])
        self.registry.max_global_bytes = 1023
        self.assertEqual(self.upload().status_code, 503)
        self.registry.max_global_bytes = 8192
        self.registry.max_room_files = 1
        self.upload(b"")
        self.assertEqual(self.upload(b"").status_code, 503)
        self.registry.max_rooms = 1
        new_token = "a" * 64
        self.assertEqual(self.register(token=new_token, room=hashlib.sha256(new_token.encode()).hexdigest()).status_code, 503)

    def test_cancelled_request_also_releases_reserved_capacity(self):
        async def exercise():
            started = asyncio.Event()

            async def receive():
                started.set()
                await asyncio.Event().wait()

            task = asyncio.create_task(self.raw_upload(receive))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(exercise())
        self.assertEqual(self.registry._reserved, 0)
        self.assertFalse(self.registry._receivers[ROOM].uploading)


if __name__ == "__main__":
    unittest.main()
