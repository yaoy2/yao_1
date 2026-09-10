"""Direct API and unattended worker checks; no real mail or credentials used."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import mail_collection_request, mail_filing_worker, mail_manual_collect
from scripts import mail_workbench_sync as sync
from tests.test_mail_workbench_sync import (
    FakeSession, NEW_SHA, PRIVATE_MARKER, TEST_TOKEN, content_response, fixture,
    http_result, repo_response,
)


class DirectMailApiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.dashboard = self.root / "dashboard.json"
        self.dashboard.write_text(json.dumps(fixture()), encoding="utf-8")

    def client(self, session, **kwargs):
        kwargs.setdefault("environ", {"MAIL_WORKBENCH_TOKEN": TEST_TOKEN})
        kwargs.setdefault("secrets", {})
        return sync.GithubAPI(session=session, **kwargs)

    def test_missing_or_invalid_credential_stops_before_network_or_local_writes(self):
        before = self.dashboard.read_bytes()
        for token, code in (("", "missing_token"), (TEST_TOKEN + "\x00Injected", "invalid_config"),
                            (TEST_TOKEN + "\rInjected", "invalid_config")):
            session = FakeSession([])
            with self.subTest(code=code), self.assertRaises(sync.MailCommandError) as caught:
                sync.synchronize(self.root, "push", session=session, secrets={},
                                 environ={"MAIL_WORKBENCH_TOKEN": token})
            self.assertEqual(code, caught.exception.code)
            self.assertEqual([], session.calls)
            self.assertEqual(before, self.dashboard.read_bytes())

    def test_explicit_environment_token_needs_no_secret_file_or_cli_login(self):
        with patch.object(sync, "_local_secrets", side_effect=AssertionError("Must not read files")):
            client = sync.GithubAPI(environ={"MAIL_WORKBENCH_TOKEN": TEST_TOKEN})
        self.assertEqual(TEST_TOKEN, client.config["token"])

    def test_backup_credential_never_changes_workspace_destination(self):
        for secrets, environ in (
            ({"github_backup": {"token": TEST_TOKEN, "repo": "yaoy2/yao_1", "branch": "other"}}, {}),
            ({}, {"GITHUB_BACKUP_TOKEN": TEST_TOKEN, "GITHUB_BACKUP_REPO": "yaoy2/yao_1"}),
            ({"mail_workbench": {"token": TEST_TOKEN, "repo": "other/repo", "branch": "other"}}, {}),
        ):
            client = sync.GithubAPI("owner/private-mail", "office", secrets=secrets, environ=environ)
            self.assertEqual({"repo": "owner/private-mail", "branch": "office", "token": TEST_TOKEN}, client.config)

    def test_local_and_global_streamlit_secrets_work_from_another_directory(self):
        home, project, elsewhere = [self.root / name for name in ("home", "project", "elsewhere")]
        for directory in (home, project):
            (directory / ".streamlit").mkdir(parents=True)
        elsewhere.mkdir()
        (home / ".streamlit/secrets.toml").write_text('[mail_workbench]\ntoken="global-test-token"', encoding="utf-8")
        (project / ".streamlit/secrets.toml").write_text('[mail_workbench]\ntoken="' + TEST_TOKEN + '"', encoding="utf-8-sig")
        previous = Path.cwd()
        try:
            os.chdir(elsewhere)
            with patch.object(Path, "home", return_value=home), patch.object(sync, "PROJECT_ROOT", project):
                self.assertEqual(TEST_TOKEN, sync.GithubAPI(environ={}).config["token"])
                # A project without its own credential uses the normal global location.
                with patch.object(sync, "PROJECT_ROOT", elsewhere):
                    self.assertEqual("global-test-token", sync.GithubAPI(environ={}).config["token"])
        finally:
            os.chdir(previous)

    def test_explicit_secret_file_is_used_without_reading_default_locations(self):
        path = self.root / "local-secrets.toml"
        path.write_text('[mail_workbench]\ntoken="' + TEST_TOKEN + '"', encoding="utf-8")
        with patch.object(Path, "home", side_effect=AssertionError("No fallback")):
            client = sync.GithubAPI(environ={"MAIL_WORKBENCH_SECRETS_FILE": str(path)})
        self.assertEqual(TEST_TOKEN, client.config["token"])

    def test_invalid_explicit_secrets_fail_safely_without_falling_back(self):
        path = self.root / "bad-secrets.toml"
        path.write_text('[mail_workbench\ntoken="' + PRIVATE_MARKER + '"', encoding="utf-8")
        for location in (str(path), str(self.root / "missing.toml"), "relative.toml"):
            with self.subTest(location=location), self.assertRaises(sync.MailCommandError) as caught:
                sync.GithubAPI(environ={"MAIL_WORKBENCH_SECRETS_FILE": location})
            self.assertEqual("invalid_config", caught.exception.code)
            self.assertNotIn(PRIVATE_MARKER, str(caught.exception))

    def test_redirects_stop_without_following_or_writing_at_every_stage(self):
        before = self.dashboard.read_bytes()
        for prior in ([], [repo_response()], [repo_response(), content_response()]):
            for status in (301, 302, 307, 308):
                redirected = http_result(status, {"message": PRIVATE_MARKER})
                session = FakeSession([*prior, redirected])
                with self.subTest(stage=len(prior), status=status), self.assertRaises(sync.MailCommandError) as caught:
                    sync.synchronize(self.root, "push", session=session, secrets={},
                                     environ={"MAIL_WORKBENCH_TOKEN": TEST_TOKEN})
                self.assertEqual("repository_mismatch", caught.exception.code)
                redirected.json.assert_not_called()
                self.assertEqual(len(prior) + 1, len(session.calls))
                self.assertEqual(before, self.dashboard.read_bytes())

    def test_error_response_bodies_are_never_parsed(self):
        for status, code in ((401, "unauthorized"), (403, "forbidden"), (429, "remote_error"), (502, "remote_error")):
            response = http_result(status)
            response.json.side_effect = AssertionError(PRIVATE_MARKER)
            with self.subTest(status=status), self.assertRaises(sync.MailCommandError) as caught:
                self.client(FakeSession([response])).read()
            self.assertEqual(code, caught.exception.code)
            response.json.assert_not_called()

    def test_malformed_success_responses_and_unconfirmed_uploads_fail_safely(self):
        invalid = http_result()
        invalid.json.side_effect = ValueError(PRIVATE_MARKER)
        for response in (invalid, http_result(payload=[PRIVATE_MARKER])):
            with self.assertRaises(sync.MailCommandError) as caught:
                self.client(FakeSession([response])).read()
            self.assertEqual("invalid_response", caught.exception.code)
            self.assertNotIn(PRIVATE_MARKER, str(caught.exception))
        session = FakeSession([repo_response(), content_response(), http_result(payload={"content": {}})])
        with self.assertRaises(sync.MailCommandError) as caught:
            sync.synchronize(self.root, "push", session=session, secrets={}, environ={"MAIL_WORKBENCH_TOKEN": TEST_TOKEN})
        self.assertEqual("upload_unconfirmed", caught.exception.code)

    def test_branch_names_are_query_encoded(self):
        session = FakeSession([repo_response(), content_response()])
        self.client(session, branch="office/L & review").read()
        self.assertTrue(session.calls[1][1].endswith("?ref=office%2FL+%26+review"))

    def test_workers_and_request_entry_use_http_without_spawning_cli(self):
        config = {"private_repo": sync.DEFAULT_REPO, "private_branch": "main",
                  "collection_mode": "manual", "collection_storage": "on_demand",
                  "filing": {"enabled": True, "destination_root": str(self.root)}}
        (self.root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        for entry in ("request", "collect", "file"):
            responses = [repo_response(), content_response()]
            if entry == "request":
                responses.append(http_result(payload={"content": {"sha": NEW_SHA}}))
            session = FakeSession(responses)
            collector, reviewer, exporter = [Mock(side_effect=AssertionError("No mail or files requested")) for _ in range(3)]
            with self.subTest(entry=entry), patch.dict(os.environ, {"MAIL_WORKBENCH_TOKEN": TEST_TOKEN}), \
                    patch.object(sync.requests, "request", session.request), \
                    patch.object(subprocess, "run", side_effect=AssertionError("No CLI")) as process:
                if entry == "request":
                    result = mail_collection_request.request(self.root)
                    self.assertTrue(result["created"])
                elif entry == "collect":
                    result = mail_manual_collect.run_once(self.root, collector=collector, reviewer=reviewer)
                    self.assertEqual("idle", result["status"])
                else:
                    result = mail_filing_worker.run_once(self.root, exporter=exporter)
                    self.assertEqual("idle", result["status"])
                process.assert_not_called()
            for operation in (collector, reviewer, exporter):
                operation.assert_not_called()
            self.assertEqual([], session.responses)


if __name__ == "__main__":
    unittest.main()
