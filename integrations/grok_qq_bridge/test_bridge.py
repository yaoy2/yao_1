"""Offline boundary tests; never connects to QQ, Grok, or any other service."""
from copy import deepcopy
import unittest

from integrations.grok_qq_bridge.bridge import Gate, Rejected


class GateTests(unittest.TestCase):
    def setUp(self):
        self.gate = Gate("11111", "22222", start_epoch=1000, timeout=30, max_chars=40)
        self.event = {
            "post_type": "message", "message_type": "private", "self_id": 11111,
            "user_id": 22222, "time": 1001, "message_id": 1,
            "message": [{"type": "text", "data": {"text": "/grok-test hello"}}],
        }

    def request(self):
        return self.gate.accept(deepcopy(self.event), 10)

    @staticmethod
    def callback(pending, text="echo hello"):
        return {"request_id": pending.request_id,
                "callback_token": pending.callback_token, "text": text}

    def assert_rejected(self, code, callback):
        with self.assertRaises(Rejected) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)

    def test_only_owner_private_new_message_on_bound_bot(self):
        for change in ({"user_id": 33333}, {"self_id": 44444},
                       {"message_type": "group"}, {"post_type": "message_sent"},
                       {"time": 900}):
            with self.subTest(change=change):
                event = deepcopy(self.event)
                event.update(change)
                self.assertIsNone(self.gate.accept(event, 10))
        self.assertEqual(0, self.gate.accepted)

    def test_ordinary_messages_and_similar_prefixes_are_ignored(self):
        for text in ("hello", "/grok-testing hello", "prefix /grok-test hello"):
            self.event["message"][0]["data"]["text"] = text
            self.assertIsNone(self.request())
        self.event["message"] = [{"type": "image", "data": {"file": "ignored"}}]
        self.assertIsNone(self.request())

    def test_length_validation_before_dispatch_and_before_consumption(self):
        self.event["message"][0]["data"]["text"] = "/grok-test " + "a" * 41
        self.assert_rejected("input_length", self.request)
        self.assertEqual(0, self.gate.accepted)
        self.event["message"][0]["data"]["text"] = "/grok-test hello"
        pending = self.request()
        self.assert_rejected("reply_length", lambda: self.gate.claim(self.callback(pending, "a" * 41), 11))
        self.assertFalse(pending.claimed)
        self.assertIs(pending, self.gate.claim(self.callback(pending), 12))

    def test_wrong_token_or_request_id_cannot_consume_request(self):
        pending = self.request()
        payload = self.callback(pending)
        payload["callback_token"] = "错误 token"
        self.assert_rejected("invalid_callback_token", lambda: self.gate.claim(payload, 11))
        payload = self.callback(pending)
        payload["request_id"] = "未知 request"
        self.assert_rejected("unknown_request", lambda: self.gate.claim(payload, 11))
        self.assertFalse(pending.claimed)

    def test_claim_is_one_time_and_blocks_second_inflight(self):
        pending = self.request()
        payload = self.callback(pending)
        self.gate.claim(payload, 11)
        self.assert_rejected("callback_already_consumed", lambda: self.gate.claim(payload, 12))
        self.event["message_id"] = 2
        self.assert_rejected("one_request_already_pending", self.request)
        self.gate.finish(pending.request_id, sent=True)
        self.assert_rejected("callback_already_consumed", lambda: self.gate.claim(payload, 13))
        self.assertEqual(1, self.gate.sent)

    def test_timeout_rejects_callback_and_replay(self):
        pending = self.request()
        self.assert_rejected("callback_expired", lambda: self.gate.claim(self.callback(pending), 40))
        self.assertIsNone(self.gate.pending)
        self.assert_rejected("callback_already_consumed", lambda: self.gate.claim(self.callback(pending), 41))
        self.assertEqual(0, self.gate.sent)

    def test_duplicate_and_total_limit_do_not_start_extra_turns(self):
        for message_id in range(1, 4):
            self.event["message_id"] = message_id
            pending = self.request()
            self.assertIsNone(self.request())
            self.gate.finish(pending.request_id)
            self.assertIsNone(self.request())
        self.event["message_id"] = 4
        self.assert_rejected("test_message_limit", self.request)
        self.assertEqual(3, self.gate.accepted)

    def test_callback_requires_exact_shape(self):
        pending = self.request()
        payload = self.callback(pending)
        payload["user_id"] = "unexpected recipient"
        self.assert_rejected("invalid_callback_shape", lambda: self.gate.claim(payload, 11))
        payload = self.callback(pending)
        payload["text"] = ["not text"]
        self.assert_rejected("invalid_callback_types", lambda: self.gate.claim(payload, 11))
        self.assertFalse(pending.claimed)

    def test_periodic_expiry_does_not_interrupt_claimed_send(self):
        pending = self.request()
        self.gate.claim(self.callback(pending), 11)
        self.assertIsNone(self.gate.expire(50))
        self.gate.finish(pending.request_id)
        self.event["message_id"] = 2
        pending = self.request()
        self.assertEqual(pending.request_id, self.gate.expire(50))


if __name__ == "__main__":
    unittest.main()
