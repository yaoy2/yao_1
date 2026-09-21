import json
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from utils.phone_transfer_relay import MIB, RelayBroker


ROOM = "1" * 64
KEY = "2" * 64
RECEIVER = "3" * 32
SENDER = "4" * 32


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now


def request(client=SENDER, role="sender", room=ROOM, key=KEY, ack=0, packets=None, **extra):
    return {"room": room, "relay_key": key, "client_id": client,
            "role": role, "ack": ack, "packets": packets or [], **extra}


def packet(number, to=RECEIVER, body="YWJj"):
    return {"id": f"{number:032x}", "to": to, "body": body}


class PhoneTransferRelayTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.broker = RelayBroker(clock=self.clock)
        self.join(self.broker)

    def join(self, broker, room=ROOM, key=KEY):
        self.assertTrue(broker.exchange(request(RECEIVER, "receiver", room, key))["ok"])
        self.assertTrue(broker.exchange(request(room=room, key=key))["ok"])

    def receive(self, broker=None, **extra):
        return (broker or self.broker).exchange(request(RECEIVER, "receiver", **extra))

    def test_only_receiver_creates_room_and_key_is_pinned(self):
        empty = RelayBroker()
        self.assertEqual(empty.exchange(request()), {"ok": False, "error": "receiver_offline"})
        self.assertEqual(len(empty._rooms), 0)
        self.join(empty)
        with patch("utils.phone_transfer_relay.hmac.compare_digest", wraps=__import__("hmac").compare_digest) as compare:
            result = empty.exchange(request(key="f" * 64))
        self.assertEqual(result, {"ok": False, "error": "auth_failed"})
        compare.assert_called_once_with(KEY, "f" * 64)
        self.assertEqual(empty.exchange(request())["peers"], [{"id": RECEIVER, "role": "receiver"}])

    def test_roles_receiver_exclusivity_and_three_sender_limit(self):
        self.assertEqual(self.broker.exchange(request(SENDER, "receiver"))["error"], "role_conflict")
        self.assertEqual(self.broker.exchange(request("5" * 32, "receiver"))["error"], "receiver_busy")
        for cid in ("5" * 32, "6" * 32):
            self.assertTrue(self.broker.exchange(request(cid))["ok"])
        self.assertEqual(self.broker.exchange(request("7" * 32))["error"], "room_full")
        self.assertEqual(self.broker.exchange(request(packets=[packet(1, "5" * 32)]))["error"], "invalid_target")
        self.assertEqual(self.receive()["messages"], [])

    def test_order_repeat_delivery_cumulative_ack_and_bidirectional_packets(self):
        packets = [packet(i) for i in range(1, 4)]
        self.assertEqual(self.broker.exchange(request(packets=packets))["accepted"], [p["id"] for p in packets])
        received = self.receive()["messages"]
        self.assertEqual([m["id"] for m in received], [1, 2, 3])
        self.assertEqual([m["source"] for m in received], [SENDER] * 3)
        self.assertEqual(self.receive()["messages"], received)
        self.assertEqual(self.receive(ack=2)["messages"], received[2:])
        self.assertEqual(self.receive(ack=1)["messages"], received[2:])
        self.assertEqual(self.receive(ack=3)["messages"], [])
        result = self.receive(ack=3, packets=[packet(4, SENDER)])
        self.assertEqual(result["accepted"], [packet(4)["id"]])
        self.assertEqual(self.broker.exchange(request())["messages"][0]["source"], RECEIVER)

    def test_dedup_survives_retries_before_and_after_ack(self):
        outgoing = request(packets=[packet(1), packet(1)])
        for _ in range(3):
            self.assertEqual(self.broker.exchange(outgoing)["accepted"], [packet(1)["id"]])
        self.assertEqual(len(self.receive()["messages"]), 1)
        self.receive(ack=1)
        self.assertEqual(self.broker.exchange(outgoing)["accepted"], [packet(1)["id"]])
        self.assertEqual(self.receive()["messages"], [])
        self.assertEqual(self.broker.exchange(request(packets=[packet(1, body="ZGVm")]))["error"], "invalid_packet")

    def test_full_request_validation_precedes_ack_or_enqueue(self):
        self.broker.exchange(request(packets=[packet(1)]))
        previous = self.receive()["messages"]
        invalid = request(RECEIVER, "receiver", ack=1,
                          packets=[packet(2, SENDER), {"id": "bad", "to": SENDER, "body": "YWJj"}])
        self.assertEqual(self.broker.exchange(invalid)["error"], "invalid_request")
        self.assertEqual(self.receive()["messages"], previous)
        self.assertEqual(self.broker.exchange(request())["messages"], [])
        self.assertEqual(self.receive(ack=99)["error"], "invalid_ack")
        self.assertEqual(self.receive()["messages"], previous)
        # A syntactically valid packet-ID conflict must not partially enqueue.
        conflict = request(packets=[packet(2), packet(1, body="ZGVm")])
        self.assertEqual(self.broker.exchange(conflict)["error"], "invalid_packet")
        self.assertEqual(self.receive()["messages"], previous)

    def test_invalid_shapes_and_request_limits(self):
        cases = [None, {}, request(room="X" * 64), request(key="f"), request(client="x" * 32),
                 request(role="admin"), request(ack=True), request(ack=-1), request(ack=2**53),
                 request(packets=[packet(i) for i in range(17)]),
                 request(packets=[packet(1, body="+/")]), request(packets=[packet(1, SENDER)]),
                 request(packets=[packet(1, body="A" * (3 * MIB // 2 + 1))]),
                 request(packets=[packet(1, body="A" * MIB), packet(2, body="B" * MIB)]),
                 request(leave="yes"), request(leave=True, packets=[packet(1)]), request(unexpected=1)]
        for invalid in cases:
            with self.subTest(shape=str(type(invalid))):
                self.assertEqual(self.broker.exchange(invalid), {"ok": False, "error": "invalid_request"})
        self.assertEqual(self.receive()["messages"], [])
        self.assertTrue(self.broker.exchange(request(request_id={"ignored": [1, "anything"]}))["ok"])

    def test_absent_and_full_targets_are_not_accepted_and_retry_is_ordered(self):
        broker = RelayBroker(clock=self.clock, max_mailbox_bytes=1200)
        self.join(broker)
        self.assertEqual(broker.exchange(request(packets=[packet(1, "f" * 32)]))["accepted"], [])
        first, large, small = packet(2, body="A" * 800), packet(3, body="B" * 800), packet(4)
        self.assertEqual(broker.exchange(request(packets=[first, large, small]))["accepted"], [first["id"]])
        self.assertEqual(len(self.receive(broker)["messages"]), 1)
        self.receive(broker, ack=1)
        self.assertEqual(broker.exchange(request(packets=[large, small]))["accepted"], [large["id"], small["id"]])
        self.assertEqual([m["body"] for m in self.receive(broker)["messages"]], [large["body"], small["body"]])

    def test_global_bytes_and_empty_room_count_are_bounded(self):
        broker = RelayBroker(clock=self.clock, max_total_bytes=2000, max_rooms=2)
        self.join(broker)
        other_room = "8" * 64
        self.join(broker, other_room)
        self.assertEqual(broker.exchange(request(packets=[packet(1, body="A" * 1100)]))["accepted"], [packet(1)["id"]])
        self.assertEqual(broker.exchange(request(room=other_room, packets=[packet(2, body="B" * 1100)]))["accepted"], [])
        self.assertLessEqual(broker._queued_bytes, 2000)
        self.assertEqual(broker.exchange(request(RECEIVER, "receiver", room="9" * 64))["error"], "relay_full")
        self.receive(broker)
        self.receive(broker, ack=1)
        self.assertEqual(broker.exchange(request(room=other_room, packets=[packet(2, body="B" * 1100)]))["accepted"], [packet(2)["id"]])

    def test_response_batches_keep_unreturned_messages_unacknowledgeable(self):
        for number in (1, 2):
            self.broker.exchange(request(packets=[packet(number, body="A" * MIB)]))
        first = self.receive()
        self.assertEqual(len(first["messages"]), 1)
        self.assertLessEqual(len(json.dumps(first, separators=(",", ":"))), 2 * MIB)
        self.assertEqual(self.receive(ack=2)["error"], "invalid_ack")
        second = self.receive(ack=1)
        self.assertEqual([m["id"] for m in second["messages"]], [2])
        self.assertEqual(self.receive(ack=2)["messages"], [])
        self.assertEqual(self.broker._queued_bytes, 0)

    def test_pending_dedup_and_message_count_are_never_evicted(self):
        broker = RelayBroker(clock=self.clock, max_dedup_packets=2, max_mailbox_messages=2)
        self.join(broker)
        broker.exchange(request(packets=[packet(1), packet(2)]))
        self.assertEqual(broker.exchange(request(packets=[packet(3)]))["accepted"], [])
        self.assertEqual(len(self.receive(broker)["messages"]), 2)
        self.receive(broker, ack=1)
        self.assertEqual(broker.exchange(request(packets=[packet(3)]))["accepted"], [packet(3)["id"]])
        self.assertEqual([m["id"] for m in self.receive(broker)["messages"]], [2, 3])
        self.assertLessEqual(len(broker._rooms[ROOM].clients[SENDER].dedup), 2)

    def test_client_expiry_requires_new_id_and_room_expiry_discards_stale_queues(self):
        self.broker.exchange(request(packets=[packet(1)]))
        self.clock.now = 19
        self.receive()
        self.clock.now = 21
        self.assertEqual(self.broker.exchange(request())["error"], "client_expired")
        self.assertTrue(self.broker.exchange(request("5" * 32))["ok"])
        self.assertEqual(len(self.receive()["messages"]), 1)
        self.clock.now = 42
        self.assertEqual(self.receive()["error"], "client_expired")
        self.assertEqual(self.broker._queued_bytes, 0)
        self.clock.now = 200
        self.assertEqual(self.broker.exchange(request())["error"], "receiver_offline")
        self.assertTrue(self.broker.exchange(request("6" * 32, "receiver", key="a" * 64))["ok"])

    def test_bad_auth_cannot_keep_a_client_or_room_alive(self):
        self.clock.now = 19
        self.assertEqual(self.broker.exchange(request(key="f" * 64))["error"], "auth_failed")
        self.clock.now = 21
        self.assertEqual(self.broker.exchange(request())["error"], "client_expired")

    def test_authenticated_leave_releases_receiver_and_is_idempotent(self):
        self.broker.exchange(request(packets=[packet(1)]))
        self.assertEqual(self.receive(key="f" * 64, leave=True)["error"], "auth_failed")
        self.assertEqual(len(self.receive()["messages"]), 1)
        empty = {"ok": True, "peers": [], "messages": [], "accepted": []}
        self.assertEqual(self.receive(leave=True), empty)
        self.assertEqual(self.receive(leave=True), empty)
        self.assertEqual(self.broker._queued_bytes, 0)
        self.assertEqual(self.receive()["error"], "client_expired")
        self.assertTrue(self.broker.exchange(request("5" * 32, "receiver"))["ok"])
        self.assertEqual(self.broker.exchange(request("6" * 32, leave=True))["error"], "client_expired")

    def test_concurrent_retries_enqueue_once_and_distinct_messages_keep_order(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            repeated = list(pool.map(lambda _: self.broker.exchange(request(packets=[packet(1)])), range(40)))
            unique = list(pool.map(lambda number: self.broker.exchange(request(packets=[packet(number)])), range(2, 102)))
        self.assertTrue(all(r["accepted"] == [packet(1)["id"]] for r in repeated))
        self.assertTrue(all(len(r["accepted"]) == 1 for r in unique))
        received = self.receive()["messages"]
        self.assertEqual(len(received), 101)
        self.assertEqual([m["id"] for m in received], list(range(1, 102)))
        self.receive(ack=101)
        self.assertEqual(self.broker._queued_bytes, 0)


if __name__ == "__main__":
    unittest.main()
