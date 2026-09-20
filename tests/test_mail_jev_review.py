import copy
import json
from pathlib import Path
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from utils import mail_jev_review as jev
from utils import mail_manual_review as review
from utils import mail_workspace as workspace
from tests.test_mail_manual_review import message, response
from tests.test_mail_manual_collection_page import page, loaded_fixture, collection_fixture
from tests import test_mail_workspace as workspace_fixtures
from scripts import mail_jev_setup


def answer_set(payload):
    result = {}
    for key, question in payload["questions"].items():
        if question["type"] == "noul":
            result[key] = {"type": "noul", "noul": .01 if key == "omitted" else .99}
        else:
            choice = next(iter(question["criteria"]))
            count = len(question["criteria"])
            result[key] = {"type": "choice", "choice": choice, "confidence": .96,
                           "probabilities": {k: .98 if k == choice else .02 / (count - 1)
                                             for k in question["criteria"]}}
    return {"answers": result}


class JevTests(unittest.TestCase):
    def setUp(self):
        self.source, self.limits = review._pack(message())
        self.draft = response()

    def run_one(self, mutate=None, *, limits=None, draft=None, status=200):
        captured = []
        def post(url, **kwargs):
            captured.append((url, kwargs))
            data = answer_set(kwargs["json"])
            if mutate:
                mutate(data)
            return SimpleNamespace(status_code=status, json=lambda: data, close=Mock())
        result = jev.verify_one(self.source, draft or self.draft, limits or [],
                                api_key="fixture-key", deadline=time.monotonic() + 30, post=post)
        return result, captured

    def test_verified_task_is_pending_and_private_fields_are_not_sent(self):
        result, calls = self.run_one()
        self.assertEqual(["pending"], result["action_statuses"])
        self.assertEqual("verified", result["review"]["status"])
        self.assertEqual(1, len(calls))
        self.assertEqual(jev.ENDPOINT, calls[0][0])
        self.assertFalse(calls[0][1]["allow_redirects"])
        self.assertNotIn("private@example.test", json.dumps(calls[0][1]["json"]))
        self.assertNotIn("fixture-key", json.dumps(result))

    def test_informational_mail_only_is_no_action(self):
        draft = response()
        draft["actions"] = []
        result, _ = self.run_one(draft=draft)
        self.assertEqual("no_action", result["message_status"])

    def test_contradiction_omission_voluntary_and_low_confidence_require_review(self):
        changes = [
            lambda a: a["summary"].update(choice="contradicts", probabilities={
                "supports": .01, "contradicts": .98, "insufficient": .01}),
            lambda a: a["omitted"].update(noul=.8),
            lambda a: a["required_0"].update(noul=.4),
            lambda a: a["support_0"].update(confidence=.6),
        ]
        for change in changes:
            with self.subTest(change=change):
                result, _ = self.run_one(lambda data: change(data["answers"]))
                self.assertEqual(["needs_confirmation"], result["action_statuses"])
                self.assertEqual("attention", result["review"]["status"])

    def test_malformed_responses_fail_closed(self):
        changes = [
            lambda a: a.pop("summary"),
            lambda a: a["required_0"].update(noul=float("nan")),
            lambda a: a["required_0"].update(noul=True),
            lambda a: a["summary"].update(confidence=2),
            lambda a: a["summary"].update(choice="injected"),
            lambda a: a["summary"].update(probabilities={"supports": 1}),
            lambda a: a["summary"].update(type="noul"),
        ]
        for change in changes:
            with self.subTest(change=change):
                result, _ = self.run_one(lambda data: change(data["answers"]))
                self.assertEqual("unavailable", result["review"]["status"])
                self.assertEqual(["needs_confirmation"], result["action_statuses"])

    def test_unread_or_oversized_source_never_calls_service(self):
        result, calls = self.run_one(limits=["附件未读"])
        self.assertEqual("incomplete", result["review"]["status"])
        self.assertFalse(calls)
        self.source["body_text"] = "x" * jev.MAX_STATE_CHARS
        result, calls = self.run_one()
        self.assertEqual("incomplete", result["review"]["status"])
        self.assertFalse(calls)

    def test_network_redirect_and_auth_failure_keep_pending(self):
        for status in (302, 401, 422, 500):
            result, _ = self.run_one(status=status)
            self.assertEqual("unavailable", result["review"]["status"])
        post = Mock(side_effect=requests.Timeout("secret raw text"))
        result = jev.verify_one(self.source, self.draft, [], api_key="key",
                                deadline=time.monotonic() + 30, post=post)
        self.assertEqual("unavailable", result["review"]["status"])
        self.assertNotIn("secret", str(result))

    def test_retry_and_global_budget_are_bounded(self):
        with patch.object(jev.time, "sleep"):
            result, calls = self.run_one(status=429)
        self.assertEqual(2, len(calls))
        self.assertEqual("unavailable", result["review"]["status"])
        post = Mock()
        result = jev.verify_one(self.source, self.draft, [], api_key="key", deadline=0, post=post)
        post.assert_not_called()
        self.assertEqual("budget", result["review"]["status"])

    def test_no_key_and_disabled_do_not_call_service(self):
        post = Mock(side_effect=AssertionError("no network"))
        for env, status in (({}, "not_configured"),
                            ({"TYPESAFE_API_KEY": "key", "MAIL_JEV_ENABLED": "0"}, "disabled")):
            result = jev.verify_batch([(self.source, self.draft, [])], environ=env, post=post)
            self.assertEqual(status, result[0]["review"]["status"])
        post.assert_not_called()

    def test_public_metadata_never_copies_service_text(self):
        self.assertEqual({"status": "verified", "version": 1},
                         jev.public_review({"status": "verified", "source": "secret", "key": "secret"}))
        self.assertEqual({}, jev.public_review({"status": "secret"}))

    def test_batch_order_and_drafts_are_preserved(self):
        drafts = [copy.deepcopy(self.draft) for _ in range(3)]
        for i, draft in enumerate(drafts):
            draft["id"] = str(i)
        before = copy.deepcopy(drafts)
        def verify(source, draft, limits, **kwargs):
            return {"id": draft["id"]}
        with patch.object(jev, "verify_one", side_effect=verify):
            result = jev.verify_batch([(self.source, d, []) for d in drafts],
                                      environ={"TYPESAFE_API_KEY": "key"})
        self.assertEqual(["0", "1", "2"], [r["id"] for r in result])
        self.assertEqual(before, drafts)


class ReviewIntegrationTests(unittest.TestCase):
    def test_grounding_precedes_jev_and_existing_mail_is_not_sent(self):
        batch = {"messages": [message("old"), message()], "actions": []}
        verification = {"review": {"status": "verified", "version": 1},
                        "action_statuses": ["pending"], "message_status": "needs_confirmation"}
        with patch.object(review, "_invoke", return_value=[response()]), \
                patch.object(jev, "verify_batch", return_value=[verification]) as check:
            result = review.review_batch(batch, {"messages": [message("old")], "actions": []}, Path.cwd())
        self.assertEqual(1, len(check.call_args.args[0]))
        self.assertEqual("pending", result["actions"][0]["status"])
        self.assertNotIn("jev_review", result["messages"][0])
        invalid = response()
        invalid["evidence"][0]["quote"] = "不存在的原文"
        with patch.object(review, "_invoke", return_value=[invalid]), patch.object(jev, "verify_batch") as check:
            with self.assertRaises(review.ReviewError):
                review.review_batch({"messages": [message()]}, {"messages": [], "actions": []}, Path.cwd())
        check.assert_not_called()

    def test_new_info_triage_survives_snapshot_but_never_replaces_human(self):
        fixture = workspace_fixtures.MailWorkspaceTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        batch = fixture.batch()
        batch["actions"] = []
        incoming = batch["messages"][0]
        incoming.update(jev_triage="no_action", jev_review={"status": "verified", "secret": "raw"})
        workspace.ingest(fixture.root, batch)
        first = workspace.load_dashboard(fixture.root)
        self.assertEqual("no_action", first["messages"][0]["triage_status"])
        exported = workspace.public_snapshot(first, fixture.root)
        self.assertEqual({"status": "verified", "version": 1}, exported["messages"][0]["jev_review"])
        self.assertNotIn("jev_triage", exported["messages"][0])
        first["messages"][0].update(triage_status="pending", triage_updated_at="2026-09-06T10:00:00+08:00")
        workspace._atomic_json(fixture.root / "dashboard.json", first)
        workspace.ingest(fixture.root, batch)
        self.assertEqual("pending", workspace.load_dashboard(fixture.root)["messages"][0]["triage_status"])

    def test_poll_refreshes_without_writing_or_losing_drafts(self):
        old = loaded_fixture(collection_fixture())
        new = loaded_fixture(collection_fixture("success", "complete"), version="after")
        state = {"mail_loaded": old, "mail_action_drafts": {"a1": "done"}}
        gateway = Mock()
        gateway.load_snapshot.return_value = new
        with patch.object(page, "st", SimpleNamespace(session_state=state, secrets={})):
            self.assertTrue(page.poll_collection(gateway))
            self.assertFalse(page.poll_collection(gateway))
        self.assertEqual({"a1": "done"}, state["mail_action_drafts"])
        gateway.request_collection.assert_not_called()
        self.assertEqual(1, gateway.load_snapshot.call_count)

    def test_poll_failure_retains_last_snapshot(self):
        old = loaded_fixture(collection_fixture())
        state = {"mail_loaded": old}
        gateway = Mock()
        gateway.load_snapshot.side_effect = RuntimeError("offline")
        with patch.object(page, "st", SimpleNamespace(session_state=state, secrets={})):
            self.assertFalse(page.poll_collection(gateway))
        self.assertIs(old, state["mail_loaded"])

    def test_setup_uses_only_synthetic_text_and_redacts_errors(self):
        with patch.object(mail_jev_setup.requests, "post", side_effect=requests.Timeout("secret-key")) as post:
            error = mail_jev_setup.check_key("secret-key")
        self.assertNotIn("secret-key", error)
        self.assertEqual("这是一条连接测试消息。", post.call_args.kwargs["json"]["state"])
        self.assertFalse(post.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
