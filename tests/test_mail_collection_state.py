"""Synthetic manual collection state and execution ownership checks."""

import copy
import unittest

from utils import mail_collection_state as state


AT = "2026-09-09T10:00:00+08:00"
REQUEST_ID = "a" * 32
CLAIM_ID = "b" * 32


def pending():
    value = state.new_request(AT)
    value["request_id"] = REQUEST_ID
    return value


def running(phase="collecting"):
    value = state.claim_collection(pending(), AT, claim_id=CLAIM_ID)
    if phase != "collecting":
        value = state.advance_collection(value, CLAIM_ID, AT, phase=phase)
    return value


def terminal(status="success", **counts):
    return state.finish_collection(running("syncing"), CLAIM_ID, AT, status=status,
                                   error_code="REVIEW_FAILED" if status != "success" else "", **counts)


class CollectionStateTests(unittest.TestCase):
    def test_minimal_optional_fields_and_canonical_constructors(self):
        value = pending()
        minimal = {key: value[key] for key in state.COLLECTION_REQUIRED_FIELDS}
        self.assertIs(minimal, state.validate_collection(minimal))
        self.assertEqual(set(state.COLLECTION_FIELDS), set(value))
        self.assertIs(value, state.validate_collection(value))
        self.assertEqual("collecting", running()["phase"])
        self.assertEqual("complete", terminal()["phase"])

    def test_active_request_cannot_be_replaced_and_new_request_time_is_monotonic(self):
        for previous in (pending(), running()):
            with self.subTest(status=previous["status"]), self.assertRaises(state.CollectionStateError) as caught:
                state.new_request(AT, previous)
            self.assertEqual("collection_busy", caught.exception.code)
        previous = terminal()
        new = state.new_request("2026-09-01T00:00:00+08:00", previous)
        self.assertNotEqual(previous["request_id"], new["request_id"])
        self.assertGreater(state._moment(new["requested_at"]), state._moment(previous["requested_at"]))

    def test_claim_and_progress_preserve_request_version_and_require_ownership(self):
        original = pending()
        before = copy.deepcopy(original)
        value = state.claim_collection(original, AT, claim_id=CLAIM_ID)
        self.assertEqual(before, original)
        self.assertEqual(before["requested_at"], value["requested_at"])
        self.assertGreater(value["updated_at"], before["updated_at"])
        for function, kwargs in ((state.advance_collection, {"phase": "reviewing"}),
                                 (state.finish_collection, {"status": "success"})):
            with self.subTest(function=function.__name__), self.assertRaises(state.CollectionStateError) as caught:
                function(value, "c" * 32, AT, **kwargs)
            self.assertEqual("collection_claim_mismatch", caught.exception.code)
        with self.assertRaises(state.CollectionStateError):
            state.claim_collection(value, AT)

    def test_phase_and_terminal_transitions_cannot_go_backwards(self):
        value = running("syncing")
        for phase in ("collecting", "reviewing", "queued", "complete", "shell", []):
            with self.subTest(phase=phase), self.assertRaises(state.CollectionStateError):
                state.advance_collection(value, CLAIM_ID, AT, phase=phase)
        finished = state.finish_collection(value, CLAIM_ID, AT, status="success")
        with self.assertRaises(state.CollectionStateError):
            state.advance_collection(finished, CLAIM_ID, AT, phase="syncing")
        with self.assertRaises(state.CollectionStateError):
            state.finish_collection(finished, CLAIM_ID, AT, status="error", error_code="REVIEW_FAILED")

    def test_zero_message_success_and_partial_counts_are_valid(self):
        complete = terminal()
        self.assertEqual((0, 0, 0, ""), tuple(complete[key] for key in
                         ("message_count", "new_message_count", "action_count", "error_code")))
        partial = terminal("partial", message_count=3, new_message_count=2, action_count=1)
        self.assertEqual("REVIEW_FAILED", partial["error_code"])
        self.assertGreater(state._moment(partial["finished_at"]), state._moment(partial["started_at"]))

    def test_public_allowlist_drops_local_details_but_remote_validation_rejects_them(self):
        value = dict(running(), batch_path="E:/private/input.json", prompt="secret body", command="unsafe")
        self.assertEqual(running(), state.public_collection(value))
        with self.assertRaises(state.CollectionStateError):
            state.validate_collection(value)
        self.assertIn("batch_path", value)

    def test_invalid_fields_states_counts_and_error_text_are_rejected(self):
        invalid = [
            dict(pending(), request_id="../outside"), dict(pending(), requested_at="2026-09-09"),
            dict(pending(), updated_at="2026-09-08T10:00:00+08:00"), dict(pending(), phase="reviewing"),
            dict(pending(), claim_id=CLAIM_ID), dict(pending(), status="queued"),
            dict(pending(), message_count=True), dict(pending(), action_count=-1),
            dict(pending(), new_message_count=1), dict(pending(), error_code="Authorization: private"),
            dict(running(), claim_id=""), dict(running(), started_at=""),
            dict(running(), finished_at=AT), dict(running(), started_at=None),
            dict(terminal(), finished_at=""), dict(terminal(), error_code="REVIEW_FAILED"),
            dict(terminal("error"), error_code=""), dict(terminal(), new_message_count=1),
            dict(terminal(), phase="syncing"),
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(state.CollectionStateError):
                state.validate_collection(value)

    def test_latest_remote_replaces_even_a_newer_local_time_or_removes_stale_request(self):
        local = {"manual_collection": pending(), "other": "preserved"}
        local["manual_collection"]["updated_at"] = "2030-01-01T00:00:00+08:00"
        for remote in ({"manual_collection": terminal()}, {}, None):
            with self.subTest(remote=remote):
                result = state.apply_remote_collection(copy.deepcopy(local), remote)
                self.assertEqual("preserved", result["other"])
                if remote and "manual_collection" in remote:
                    self.assertEqual(remote["manual_collection"], result["manual_collection"])
                else:
                    self.assertNotIn("manual_collection", result)


if __name__ == "__main__":
    unittest.main()
