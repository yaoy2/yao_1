"""Bounded, process-local mailboxes for opaque encrypted transfer packets.

The broker never decrypts, persists, or logs packets. A Streamlit resource cache
may share one instance between sessions; ``exchange`` is thread safe.
"""

from collections import OrderedDict, deque
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
import threading
import time


MIB = 1024 * 1024
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX_32 = re.compile(r"[0-9a-f]{32}\Z")
_BODY = re.compile(r"[A-Za-z0-9_-]+\Z")
_REQUEST_KEYS = {"room", "relay_key", "client_id", "role", "ack", "packets"}
_OPTIONAL_KEYS = {"leave", "request_id"}


def _json_size(value):
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")))


@dataclass(slots=True, repr=False)
class _Message:
    id: int
    source: str
    packet_id: str
    body: str
    size: int

    def public(self):
        return {"id": self.id, "source": self.source, "body": self.body}


@dataclass(slots=True, repr=False)
class _Client:
    role: str
    seen: float
    mailbox: deque = field(default_factory=deque)
    queued_bytes: int = 0
    next_id: int = 1
    delivered: int = 0
    acked: int = 0
    # packet id -> (target id, ciphertext digest, destination message id)
    dedup: OrderedDict = field(default_factory=OrderedDict)


@dataclass(slots=True, repr=False)
class _Room:
    key: str
    seen: float
    clients: dict = field(default_factory=dict)
    expired: dict = field(default_factory=dict)


class RelayBroker:
    """A small authenticated relay with at-least-once mailbox delivery.

    ACKs are cumulative per client and may only acknowledge messages returned
    to that client. Retry unaccepted packets in order with unchanged packet IDs.
    Recent accepted IDs are deduplicated; pending messages are never evicted to
    make space. ``client_expired`` requires a fresh client ID and a new handshake.
    The byte limits count serialized mailbox messages, including their envelopes.
    Rooms, message counts, tombstones, and dedup history are also bounded.
    """

    def __init__(
        self, *, clock=time.monotonic, client_ttl=20, room_ttl=120,
        max_mailbox_bytes=4 * MIB, max_total_bytes=32 * MIB,
        max_request_bytes=2 * MIB, max_response_bytes=2 * MIB,
        max_body_chars=3 * MIB // 2, max_packets=16, max_rooms=64,
        max_mailbox_messages=1024, max_dedup_packets=256,
        max_expired_clients=128,
    ):
        self._clock = clock
        self.client_ttl = client_ttl
        self.room_ttl = room_ttl
        self.max_mailbox_bytes = max_mailbox_bytes
        self.max_total_bytes = max_total_bytes
        self.max_request_bytes = max_request_bytes
        self.max_response_bytes = max_response_bytes
        self.max_body_chars = max_body_chars
        self.max_packets = max_packets
        self.max_rooms = max_rooms
        self.max_mailbox_messages = max_mailbox_messages
        self.max_dedup_packets = max_dedup_packets
        self.max_expired_clients = max_expired_clients
        self._rooms = {}
        self._queued_bytes = 0
        self._lock = threading.Lock()

    def _validate(self, request):
        if (type(request) is not dict or not _REQUEST_KEYS <= set(request)
                or set(request) - _REQUEST_KEYS - _OPTIONAL_KEYS):
            return None
        for key, pattern in (("room", _HEX_64), ("relay_key", _HEX_64), ("client_id", _HEX_32)):
            if type(request[key]) is not str or not pattern.fullmatch(request[key]):
                return None
        if request["role"] not in ("receiver", "sender"):
            return None
        if type(request["ack"]) is not int or not 0 <= request["ack"] <= 2**53 - 1:
            return None
        raw_packets = request["packets"]
        if type(raw_packets) is not list or len(raw_packets) > self.max_packets:
            return None
        if type(request.get("leave", False)) is not bool or request.get("leave") and raw_packets:
            return None
        packets = []
        body_chars = 0
        seen = {}
        for packet in raw_packets:
            if type(packet) is not dict or set(packet) != {"id", "to", "body"}:
                return None
            if any(type(packet[k]) is not str or not _HEX_32.fullmatch(packet[k]) for k in ("id", "to")):
                return None
            body = packet["body"]
            if type(body) is not str or not 0 < len(body) <= self.max_body_chars:
                return None
            body_chars += len(body)
            if body_chars > self.max_request_bytes or not _BODY.fullmatch(body):
                return None
            if packet["to"] == request["client_id"]:
                return None
            signature = (packet["to"], hashlib.sha256(body.encode("ascii")).digest())
            if packet["id"] in seen and seen[packet["id"]] != signature:
                return None
            seen[packet["id"]] = signature
            packets.append((packet["id"], packet["to"], body, signature[1]))
        normalized = {key: request[key] for key in _REQUEST_KEYS - {"packets"}}
        normalized["packets"] = [{"id": p[0], "to": p[1], "body": p[2]} for p in packets]
        normalized["leave"] = request.get("leave", False)
        try:
            request_size = _json_size(request)
        except (TypeError, ValueError, OverflowError, RecursionError):
            return None
        if request_size > self.max_request_bytes:
            return None
        return normalized, packets

    def _expire(self, now):
        for room_id, room in list(self._rooms.items()):
            if now - room.seen >= self.room_ttl:
                self._queued_bytes -= sum(c.queued_bytes for c in room.clients.values())
                del self._rooms[room_id]
                continue
            room.expired = {cid: until for cid, until in room.expired.items() if until > now}
            for cid, client in list(room.clients.items()):
                if now - client.seen >= self.client_ttl:
                    self._queued_bytes -= client.queued_bytes
                    del room.clients[cid]
                    room.expired[cid] = now + self.room_ttl

    @staticmethod
    def _pending(room, target_id, message_id):
        target = room.clients.get(target_id)
        return target is not None and message_id > target.acked

    def exchange(self, request):
        """Validate a full request, then atomically ACK, enqueue, and poll."""
        validated = self._validate(request)
        if validated is None:
            return {"ok": False, "error": "invalid_request"}
        request, packets = validated
        with self._lock:
            now = self._clock()
            room_id, cid = request["room"], request["client_id"]
            room = self._rooms.get(room_id)
            # Do not change existing rooms, even their expiry state, on bad auth.
            if room is not None and now - room.seen < self.room_ttl:
                if not hmac.compare_digest(room.key, request["relay_key"]):
                    return {"ok": False, "error": "auth_failed"}
                client = room.clients.get(cid)
                if client and client.role != request["role"]:
                    return {"ok": False, "error": "role_conflict"}
                if client and request["ack"] > client.delivered:
                    return {"ok": False, "error": "invalid_ack"}
                for packet_id, target_id, _, digest in packets:
                    previous = client.dedup.get(packet_id) if client else None
                    if previous and previous[:2] != (target_id, digest):
                        return {"ok": False, "error": "invalid_packet"}
                    target = room.clients.get(target_id)
                    if target and target.role == request["role"]:
                        return {"ok": False, "error": "invalid_target"}
            # Syntax, authentication, role and packet-identity errors are all
            # checked before either ACKs or queues can be modified.
            self._expire(now)
            room = self._rooms.get(room_id)
            if request["leave"]:
                if room is None or cid not in room.clients and cid not in room.expired:
                    return {"ok": False, "error": "client_expired"}
                departing = room.clients.pop(cid, None)
                if departing is not None:
                    self._queued_bytes -= departing.queued_bytes
                    room.expired[cid] = now + self.room_ttl
                return {"ok": True, "peers": [], "messages": [], "accepted": []}
            if room is None:
                if request["role"] != "receiver":
                    return {"ok": False, "error": "receiver_offline"}
                if request["ack"]:
                    return {"ok": False, "error": "client_expired"}
                if len(self._rooms) >= self.max_rooms:
                    return {"ok": False, "error": "relay_full"}
                room = _Room(request["relay_key"], now)
                self._rooms[room_id] = room
            if cid in room.expired:
                return {"ok": False, "error": "client_expired"}
            client = room.clients.get(cid)
            if client is None:
                if request["ack"]:
                    return {"ok": False, "error": "client_expired"}
                receivers = [c for c in room.clients.values() if c.role == "receiver"]
                if request["role"] == "receiver" and receivers:
                    return {"ok": False, "error": "receiver_busy"}
                if request["role"] == "sender" and not receivers:
                    return {"ok": False, "error": "receiver_offline"}
                if len(room.clients) >= 4 or len(room.clients) + len(room.expired) >= self.max_expired_clients:
                    return {"ok": False, "error": "room_full"}
                client = _Client(request["role"], now)
                room.clients[cid] = client
            client.seen = room.seen = now
            client.acked = max(client.acked, request["ack"])
            while client.mailbox and client.mailbox[0].id <= client.acked:
                acknowledged = client.mailbox.popleft()
                client.queued_bytes -= acknowledged.size
                self._queued_bytes -= acknowledged.size
            accepted = []
            blocked_targets = set()
            for packet_id, target_id, body, digest in packets:
                target = room.clients.get(target_id)
                if target is None or target_id in blocked_targets:
                    continue
                if packet_id in client.dedup:
                    if packet_id not in accepted:
                        accepted.append(packet_id)
                    continue
                # Only completed packets may leave the bounded dedup window.
                if len(client.dedup) >= self.max_dedup_packets:
                    removable = next((pid for pid, (tid, _, mid) in client.dedup.items()
                                      if not self._pending(room, tid, mid)), None)
                    if removable is not None:
                        del client.dedup[removable]
                item = _Message(target.next_id, cid, packet_id, body, 0)
                item.size = _json_size(item.public())
                if (len(client.dedup) >= self.max_dedup_packets
                        or len(target.mailbox) >= self.max_mailbox_messages
                        or target.queued_bytes + item.size > self.max_mailbox_bytes
                        or self._queued_bytes + item.size > self.max_total_bytes
                        or item.size + 1024 > self.max_response_bytes):
                    blocked_targets.add(target_id)
                    continue
                target.next_id += 1
                target.mailbox.append(item)
                target.queued_bytes += item.size
                self._queued_bytes += item.size
                client.dedup[packet_id] = (target_id, digest, item.id)
                accepted.append(packet_id)
            response = {
                "ok": True,
                "peers": [{"id": peer_id, "role": peer.role}
                          for peer_id, peer in room.clients.items() if peer_id != cid],
                "messages": [],
                "accepted": accepted,
            }
            response_size = _json_size(response)
            for item in client.mailbox:
                addition = item.size + (1 if response["messages"] else 0)
                if response_size + addition > self.max_response_bytes:
                    break
                response["messages"].append(item.public())
                response_size += addition
                client.delivered = max(client.delivered, item.id)
            return response
