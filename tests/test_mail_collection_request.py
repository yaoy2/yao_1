"""CAS ownership tests: no mail, model, credential or real repository access."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import mail_collection_request as requests
from scripts import mail_workbench_sync as sync
from tests.test_mail_collection_state import AT, CLAIM_ID, REQUEST_ID, pending, running, terminal
from tests.test_mail_workbench_sync import fixture
from utils import mail_collection_state as state
from utils import mail_workspace


class FakeClient:
    def __init__(self, data):
        self.snapshot = copy.deepcopy(data)
        self.version = "version-1"
        self.read_count = 0
        self.writes = []
        self.before_write = None
        self.unconfirmed = False

    def read(self):
        self.read_count += 1
        return {"snapshot": copy.deepcopy(self.snapshot), "version": self.version}

    def write(self, snapshot, version):
        self.writes.append((copy.deepcopy(snapshot), version))
        if self.before_write is not None:
            callback, self.before_write = self.before_write, None
            callback(self)
        if version != self.version:
            raise sync.MailCommandError("conflict")
        self.snapshot = copy.deepcopy(snapshot)
        self.version += "-next"
        return None if self.unconfirmed else self.version


class CollectionRequestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original = fixture()
        self.original["manual_collection"] = pending()
        mail_workspace._atomic_json(self.root / "dashboard.json", self.original)
        self.client = FakeClient(self.original)

    def test_local_request_creates_once_or_reuses_the_active_remote_request(self):
        self.client.snapshot.pop("manual_collection")
        first = requests.request(self.root, client=self.client, at=AT)
        self.assertIs(True, first["created"])
        self.assertEqual(first["manual_collection"], mail_workspace.load_dashboard(self.root)["manual_collection"])
        second = requests.request(self.root, client=self.client, at=AT)
        self.assertIs(False, second["created"])
        self.assertEqual(first["manual_collection"], second["manual_collection"])
        self.assertEqual(1, len(self.client.writes))

    def test_claim_progress_and_finish_preserve_user_decisions_and_local_sources(self):
        claimed = requests.claim(self.root, REQUEST_ID, claim_id=CLAIM_ID, client=self.client, at=AT)
        self.assertEqual(CLAIM_ID, claimed["manual_collection"]["claim_id"])
        self.assertEqual("running", self.client.snapshot["manual_collection"]["status"])
        requests.progress(self.root, REQUEST_ID, CLAIM_ID, phase="reviewing", message_count=3,
                          new_message_count=2, client=self.client, at=AT)
        self.client.snapshot["actions"][0].update(status="done", completed_at=AT, updated_at=AT)
        self.client.version += "-user-edit"
        requests.progress(self.root, REQUEST_ID, CLAIM_ID, phase="syncing", action_count=1,
                          client=self.client, at=AT)
        finished = requests.finish(self.root, REQUEST_ID, CLAIM_ID, status="success", client=self.client, at=AT)
        self.assertEqual("success", finished["manual_collection"]["status"])
        self.assertEqual((3, 2, 1), tuple(finished["manual_collection"][key]
                         for key in ("message_count", "new_message_count", "action_count")))
        self.assertEqual("done", finished["snapshot"]["actions"][0]["status"])
        local = mail_workspace.load_dashboard(self.root)
        self.assertEqual(self.original["messages"][0], local["messages"][0])
        self.assertEqual(self.original["coverage"], local["coverage"])
        self.assertEqual("done", local["actions"][0]["status"])
        self.assertNotIn("body_text", finished["snapshot"]["messages"][0])
        self.assertNotIn("download_path", finished["snapshot"]["messages"][0]["attachments"][0])

    def test_two_claimers_only_one_can_take_pending_request(self):
        requests.claim(self.root, REQUEST_ID, claim_id=CLAIM_ID, client=self.client, at=AT)
        with self.assertRaises(sync.MailCommandError) as caught:
            requests.claim(self.root, REQUEST_ID, claim_id="c" * 32, client=self.client, at=AT)
        self.assertEqual("collection_busy", caught.exception.code)
        self.assertEqual(1, len(self.client.writes))
        self.assertEqual(CLAIM_ID, self.client.snapshot["manual_collection"]["claim_id"])

    def test_claim_losing_a_cas_race_never_persists_a_local_claim(self):
        before = (self.root / "dashboard.json").read_bytes()

        def competing_claim(client):
            client.snapshot["manual_collection"] = state.claim_collection(pending(), AT, claim_id="c" * 32)
            client.version += "-competitor"

        self.client.before_write = competing_claim
        with self.assertRaises(sync.MailCommandError) as caught:
            requests.claim(self.root, REQUEST_ID, claim_id=CLAIM_ID, client=self.client, at=AT)
        self.assertEqual("conflict", caught.exception.code)
        self.assertEqual(1, len(self.client.writes))
        self.assertEqual(before, (self.root / "dashboard.json").read_bytes())

    def test_unconfirmed_claim_write_is_not_returned_as_execution_permission(self):
        before = (self.root / "dashboard.json").read_bytes()
        self.client.unconfirmed = True
        with self.assertRaises(sync.MailCommandError) as caught:
            requests.claim(self.root, REQUEST_ID, claim_id=CLAIM_ID, client=self.client, at=AT)
        self.assertEqual("upload_unconfirmed", caught.exception.code)
        self.assertEqual(before, (self.root / "dashboard.json").read_bytes())
        # A caller can recover ownership with its pre-recorded ID after a read.
        self.assertEqual(CLAIM_ID, self.client.read()["snapshot"]["manual_collection"]["claim_id"])

    def test_old_request_and_foreign_claim_cannot_update_the_current_request(self):
        self.client.snapshot["manual_collection"] = running()
        for identifier, claim_id, code in (("d" * 32, CLAIM_ID, "collection_superseded"),
                                           (REQUEST_ID, "c" * 32, "collection_claim_mismatch")):
            with self.subTest(code=code), self.assertRaises(sync.MailCommandError) as caught:
                requests.finish(self.root, identifier, claim_id, status="success", client=self.client, at=AT)
            self.assertEqual(code, caught.exception.code)
        self.assertEqual([], self.client.writes)

    def test_finish_retry_acknowledges_only_the_identical_completed_result(self):
        self.client.snapshot["manual_collection"] = terminal(message_count=2, new_message_count=1, action_count=1)
        result = requests.finish(self.root, REQUEST_ID, CLAIM_ID, status="success", message_count=2,
                                 new_message_count=1, action_count=1, client=self.client, at=AT)
        self.assertEqual("success", result["manual_collection"]["status"])
        self.assertEqual([], self.client.writes)
        self.assertEqual(result["manual_collection"], mail_workspace.load_dashboard(self.root)["manual_collection"])
        for changes in ({"message_count": 3}, {"status": "error", "error_code": "REVIEW_FAILED"}):
            with self.subTest(changes=changes), self.assertRaises(sync.MailCommandError):
                requests.finish(self.root, REQUEST_ID, CLAIM_ID, client=self.client, at=AT,
                                 **{"status": "success", **changes})
        self.assertEqual([], self.client.writes)

    def test_terminal_write_conflict_keeps_remote_running_and_local_source_bytes(self):
        self.client.snapshot["manual_collection"] = running("syncing")
        before = (self.root / "dashboard.json").read_bytes()

        def newer_user_edit(client):
            client.snapshot["actions"][0].update(status="no_action", updated_at=AT)
            client.version += "-user"

        self.client.before_write = newer_user_edit
        with self.assertRaises(sync.MailCommandError) as caught:
            requests.finish(self.root, REQUEST_ID, CLAIM_ID, status="success", client=self.client, at=AT)
        self.assertEqual("conflict", caught.exception.code)
        self.assertEqual("running", self.client.snapshot["manual_collection"]["status"])
        self.assertEqual("no_action", self.client.snapshot["actions"][0]["status"])
        self.assertEqual(before, (self.root / "dashboard.json").read_bytes())

    def test_remote_input_and_wrong_account_fail_before_any_write(self):
        for mutate in (lambda data: data["manual_collection"].update(prompt="private shell command"),
                       lambda data: data.update(account="wrong@example.invalid")):
            with self.subTest(mutate=mutate):
                client = FakeClient(self.original)
                mutate(client.snapshot)
                with self.assertRaises(sync.MailCommandError):
                    requests.claim(self.root, REQUEST_ID, client=client, at=AT)
                self.assertEqual([], client.writes)

    def test_review_error_is_safe_and_raw_error_text_cannot_be_published(self):
        self.client.snapshot["manual_collection"] = running("reviewing")
        with self.assertRaises(sync.MailCommandError) as caught:
            requests.finish(self.root, REQUEST_ID, CLAIM_ID, status="error", error_code="Authorization: private",
                            client=self.client, at=AT)
        self.assertNotIn("Authorization", str(caught.exception))
        self.assertEqual([], self.client.writes)
        result = requests.finish(self.root, REQUEST_ID, CLAIM_ID, status="error", error_code="REVIEW_FAILED",
                                 client=self.client, at=AT)
        self.assertEqual("REVIEW_FAILED", result["manual_collection"]["error_code"])

    def test_local_write_failure_after_claim_reports_confirmed_remote_version(self):
        with patch.object(mail_workspace, "_atomic_json", side_effect=OSError("private local path")):
            with self.assertRaises(sync.MailCommandError) as caught:
                requests.claim(self.root, REQUEST_ID, claim_id=CLAIM_ID, client=self.client, at=AT)
        self.assertEqual("local_write_failed_after_upload", caught.exception.code)
        self.assertEqual(CLAIM_ID, self.client.snapshot["manual_collection"]["claim_id"])
        self.assertNotIn("private local path", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
