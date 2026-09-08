import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import mail_imap_collect as cli
from scripts.mail_imap_setup import SetupError
from utils import mail_imap_credentials as credentials
from utils import mail_workspace


ACCOUNT = "fixture@example.edu"
HOST = "mail.example.edu"
TARGET = credentials.TARGET_PREFIX + HOST + "/" + ACCOUNT
SECRET = "synthetic-credential-never-persist-材料"
FIRST = "2026-09-01T00:00:00+08:00"
NOW = "2026-09-08T20:00:00+08:00"


def message_bytes(identifier, *, subject="合成行政通知", body="仅供离线测试的邮件正文。", attachment=False):
    message = EmailMessage()
    message["Message-ID"] = identifier
    message["From"] = "Test Office <office@example.edu>"
    message["Subject"] = subject
    message.set_content(body)
    if attachment:
        message.add_attachment(b"synthetic form content", maintype="application", subtype="pdf", filename="材料表.pdf")
    return message.as_bytes()


class ReadonlyMailbox:
    """Entirely local test double; any write-like method is unavailable."""

    def __init__(self, records):
        self.records = records
        self.calls = []
        self.debug = None

    def login(self, username, password):
        if (username, password) != (ACCOUNT, SECRET):
            raise AssertionError("unexpected synthetic credential")
        self.calls.append(("LOGIN", username))
        return "OK", [b"fixture authenticated"]

    def list(self):
        self.calls.append(("LIST",))
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"']

    def select(self, folder, readonly=False):
        if not readonly or folder != '"INBOX"':
            raise AssertionError("test mailbox only permits read-only INBOX")
        self.calls.append(("SELECT", folder, readonly))
        return "OK", [str(len(self.records)).encode()]

    def uid(self, command, *arguments):
        self.calls.append((command, *arguments))
        if command == "SEARCH":
            identifiers = list(self.records)
            if arguments[1] == "HEADER":
                expected = arguments[3].strip('"').encode()
                identifiers = [uid for uid in identifiers if expected in self.records[uid][0]]
            return "OK", [" ".join(map(str, identifiers)).encode()]
        if command != "FETCH":
            raise AssertionError("test mailbox rejects mutating commands")
        uid = int(arguments[0])
        raw, date = self.records[uid]
        if arguments[1] == "(UID INTERNALDATE RFC822.SIZE)":
            return "OK", [f'1 (UID {uid} INTERNALDATE "{date}" RFC822.SIZE {len(raw)})'.encode()]
        if arguments[1] == "(UID BODY.PEEK[])":
            return "OK", [(f"1 (UID {uid} BODY[] {{{len(raw)}}}".encode(), raw), b")"]
        raise AssertionError("unexpected FETCH shape")

    def shutdown(self):
        self.calls.append(("SHUTDOWN",))


class CollectionWindowTests(unittest.TestCase):
    def test_first_run_starts_at_configured_boundary(self):
        self.assertEqual((FIRST, NOW), cli.collection_window({"collection_start": FIRST},
                         {"coverage": {"through": None}}, at=NOW))

    def test_previous_coverage_overlaps_one_day(self):
        self.assertEqual(("2026-09-06T17:30:00+08:00", NOW),
                         cli.collection_window({"collection_start": FIRST},
                         {"coverage": {"through": "2026-09-07T17:30:00+08:00"}}, at=NOW))

    def test_overlap_never_precedes_initial_boundary(self):
        self.assertEqual((FIRST, NOW), cli.collection_window({"collection_start": FIRST},
                         {"coverage": {"through": "2026-09-01T12:00:00+08:00"}}, at=NOW))

    def test_explicit_since_is_normalized_and_bounded(self):
        config = {"collection_start": FIRST}
        self.assertEqual(("2026-09-05T08:00:00+08:00", NOW),
                         cli.collection_window(config, {}, at=NOW, since="2026-09-05T00:00:00Z"))
        with self.assertRaisesRegex(ValueError, "precedes configured boundary"):
            cli.collection_window(config, {}, at=NOW, since="2026-08-31T23:59:59+08:00")
        with self.assertRaisesRegex(ValueError, "reversed"):
            cli.collection_window(config, {}, at=NOW, since="2026-09-09T00:00:00+08:00")


class AttachmentReconciliationTests(unittest.TestCase):
    def reconcile(self, old, incoming):
        dashboard = {"messages": [{"id": "mail-1", "category": "教学", "summary": "已有人工整理摘要",
                                   "attachments": old}]}
        original = copy.deepcopy(dashboard)
        batch = {"messages": [{"id": "mail-1", "category": "待整理", "summary": "待整理",
                               "attachments": copy.deepcopy(incoming)}]}
        result = cli.reconcile_existing(batch, dashboard)
        self.assertEqual(original, dashboard)
        self.assertEqual("教学", result["messages"][0]["category"])
        self.assertEqual("已有人工整理摘要", result["messages"][0]["summary"])
        return result["messages"][0]["attachments"]

    def test_unique_exact_name_preserves_identity_for_previously_missing_file(self):
        result = self.reconcile([{"id": "old-1", "name": "材料表.pdf", "status": "missing"}],
                                [{"id": "new-1", "name": "材料表.pdf", "sha256": "a" * 64}])
        self.assertEqual("old-1", result[0]["id"])

    def test_unique_hash_matches_renamed_file_and_disambiguates_duplicate_names(self):
        old = [{"id": "old-a", "name": "同名.pdf", "sha256": "a" * 64},
               {"id": "old-b", "name": "同名.pdf", "sha256": "b" * 64}]
        incoming = [{"id": "new-b", "name": "更名.pdf", "sha256": "b" * 64},
                    {"id": "new-a", "name": "同名.pdf", "sha256": "a" * 64}]
        self.assertEqual(["old-b", "old-a"], [a["id"] for a in self.reconcile(old, incoming)])

    def test_name_matching_is_exact_with_unicode_normalization(self):
        old = [{"id": "old-a", "name": "café.pdf"}, {"id": "old-b", "name": "通知.pdf"}]
        incoming = [{"id": "new-a", "name": "cafe\u0301.pdf"}, {"id": "new-b", "name": "通知 (1).pdf"}]
        self.assertEqual(["old-a", "new-b"], [a["id"] for a in self.reconcile(old, incoming)])

    def test_nonbreaking_spaces_match_existing_filename_without_changing_display_name(self):
        incoming_name = "材料\u00a0\u00a0汇总表.xlsx"
        result = self.reconcile([{"id": "old-a", "name": "材料 汇总表.xlsx", "status": "missing"}],
                                [{"id": "new-a", "name": incoming_name, "sha256": "a" * 64}])
        self.assertEqual("old-a", result[0]["id"])
        self.assertEqual(incoming_name, result[0]["name"])

    def test_whitespace_normalization_does_not_resolve_ambiguous_names(self):
        result = self.reconcile([{"id": "old-a", "name": "材料 表.xlsx"}],
                                [{"id": "new-a", "name": "材料 表.xlsx", "sha256": "a" * 64},
                                 {"id": "new-b", "name": "材料\u00a0表.xlsx", "sha256": "b" * 64}])
        self.assertEqual(["new-a", "new-b"], [a["id"] for a in result])

    def test_duplicate_old_names_are_ambiguous(self):
        result = self.reconcile([{"id": "old-a", "name": "同名.pdf"}, {"id": "old-b", "name": "同名.pdf"}],
                                [{"id": "new-a", "name": "同名.pdf", "sha256": "a" * 64}])
        self.assertEqual("new-a", result[0]["id"])

    def test_duplicate_incoming_names_are_not_assigned_by_order(self):
        result = self.reconcile([{"id": "old-a", "name": "同名.pdf"}],
                                [{"id": "new-a", "name": "同名.pdf", "sha256": "a" * 64},
                                 {"id": "new-b", "name": "同名.pdf", "sha256": "b" * 64}])
        self.assertEqual(["new-a", "new-b"], [a["id"] for a in result])

    def test_strong_hash_match_wins_before_fallback_name_regardless_of_order(self):
        old = [{"id": "old-a", "name": "alpha.pdf", "sha256": "a" * 64}]
        incoming = [{"id": "new-name", "name": "alpha.pdf", "sha256": "b" * 64},
                    {"id": "new-hash", "name": "beta.pdf", "sha256": "a" * 64}]
        for candidates in (incoming, list(reversed(incoming))):
            with self.subTest(order=[a["id"] for a in candidates]):
                result = self.reconcile(old, candidates)
                by_name = {a["name"]: a["id"] for a in result}
                self.assertEqual({"alpha.pdf": "new-name", "beta.pdf": "old-a"}, by_name)

    def test_new_messages_keep_parser_metadata(self):
        batch = {"messages": [{"id": "new-mail", "category": "待整理", "summary": "短摘要", "attachments": []}]}
        self.assertEqual(batch, cli.reconcile_existing(copy.deepcopy(batch), {"messages": []}))


class CollectWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mail_workspace.initialize(self.root, ACCOUNT)
        self.config = {"account": ACCOUNT, "collection_start": FIRST, "mail_folders": ["收件箱"],
                       "source_url": "https://mail.nsu.edu.cn/owa/", "imap": {"host": HOST, "port": 993,
                       "ssl": True, "verify_tls": True, "credential_target": TARGET}}
        self.write_config()
        self.dashboard_before = (self.root / "dashboard.json").read_bytes()
        self.read_mock = self.start_patch(patch.object(cli, "read_credential", return_value=(ACCOUNT, SECRET)))
        self.network_mock = self.start_patch(patch.object(cli.mail_imap.imaplib, "IMAP4_SSL",
                                  side_effect=AssertionError("network use is forbidden in this test")))
        self.start_patch(patch.object(credentials, "_advapi", side_effect=AssertionError("native credential access is forbidden")))
        self.start_patch(patch.object(cli, "now_iso", return_value=NOW))

    def start_patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def write_config(self):
        (self.root / "config.json").write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")

    def assert_no_cursor_or_archive_changes(self):
        self.assertEqual(self.dashboard_before, (self.root / "dashboard.json").read_bytes())
        self.assertEqual([], list((self.root / "archive").rglob("*")))

    def read_batch(self, summary):
        path = Path(summary["batch_path"])
        self.assertTrue(path.resolve().is_relative_to(self.root / "incoming"))
        return json.loads(path.read_text(encoding="utf-8"))

    def fixture_client(self, records):
        client = ReadonlyMailbox(records)
        self.network_mock.side_effect = None
        self.network_mock.return_value = client
        return client

    def test_missing_credential_creates_safe_partial_batch_without_cursor_write(self):
        self.read_mock.side_effect = credentials.CredentialNotFound(SECRET)
        summary = cli.collect_workspace(self.root, at=NOW)
        self.assertEqual("partial", summary["status"])
        self.assertEqual(["IMAP_LOCAL_CREDENTIAL_REQUIRED"], summary["errors"])
        self.assertEqual(0, summary["message_count"])
        self.assertEqual(0, summary["attachment_count"])
        self.assertFalse(summary["window"]["complete"])
        self.assertEqual([], self.read_batch(summary)["messages"])
        self.network_mock.assert_not_called()
        self.read_mock.assert_called_once_with(TARGET)
        self.assert_no_cursor_or_archive_changes()
        for path in self.root.rglob("*.json"):
            self.assertNotIn(SECRET, path.read_text(encoding="utf-8"))

    def test_stored_account_mismatch_is_partial_without_login(self):
        self.read_mock.return_value = ("other@example.edu", SECRET)
        summary = cli.collect_workspace(self.root, at=NOW)
        self.assertEqual("partial", summary["status"])
        self.assertEqual(["IMAP_LOCAL_CREDENTIAL_REQUIRED"], summary["errors"])
        self.network_mock.assert_not_called()
        self.assert_no_cursor_or_archive_changes()

    def test_workspace_account_mismatch_is_rejected_before_credential_access(self):
        dashboard = json.loads(self.dashboard_before)
        dashboard["account"] = "other@example.edu"
        (self.root / "dashboard.json").write_text(json.dumps(dashboard), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "workspace account mismatch"):
            cli.collect_workspace(self.root, at=NOW)
        self.read_mock.assert_not_called()
        self.network_mock.assert_not_called()
        self.assertFalse((self.root / "incoming").exists())

    def test_unrelated_credential_target_is_rejected_before_credential_access(self):
        self.config["imap"]["credential_target"] = credentials.TARGET_PREFIX + HOST + "/other@example.edu"
        self.write_config()
        with self.assertRaisesRegex(SetupError, "invalid_config"):
            cli.collect_workspace(self.root, at=NOW)
        self.read_mock.assert_not_called()
        self.network_mock.assert_not_called()

    def test_invalid_folder_configuration_is_rejected_before_credentials(self):
        for folders in ([], "INBOX", [""], [None]):
            with self.subTest(folders=folders):
                self.config["mail_folders"] = folders
                self.write_config()
                with self.assertRaisesRegex(ValueError, "invalid folder configuration"):
                    cli.collect_workspace(self.root, at=NOW)
        self.read_mock.assert_not_called()
        self.network_mock.assert_not_called()

    def test_end_to_end_mock_mailbox_stages_files_and_safe_status_then_shutdown(self):
        raw = message_bytes("<normal@example.edu>", attachment=True)
        auth = message_bytes("<auth@example.edu>", subject="Your verification code is 483921",
                             body="Your one-time password is 483921.")
        client = self.fixture_client({1: (raw, "08-Sep-2026 12:00:00 +0800"),
                                      2: (auth, "08-Sep-2026 13:00:00 +0800")})
        config_before = (self.root / "config.json").read_bytes()
        summary = cli.collect_workspace(self.root, kind="morning", at=NOW)
        self.assertEqual("staged", summary["status"])
        self.assertEqual((1, 1, 0), (summary["message_count"], summary["attachment_count"], summary["error_count"]))
        batch = self.read_batch(summary)
        self.assertEqual("morning", batch["kind"])
        self.assertEqual([], batch["actions"])
        self.assertTrue(batch["collection"]["readonly"])
        self.assertEqual(1, batch["collection"]["skipped_authentication_notifications"]["count"])
        message = batch["messages"][0]
        self.assertEqual(raw, Path(message["raw_eml_download_path"]).read_bytes())
        attachment = message["attachments"][0]
        self.assertEqual(hashlib.sha256(Path(attachment["download_path"]).read_bytes()).hexdigest(), attachment["sha256"])
        self.assertEqual("待整理", message["summary"])
        saved_status = json.loads((self.root / "state" / "imap_collection.json").read_text(encoding="utf-8"))
        self.assertEqual(summary, saved_status)
        for private in (SECRET, "483921", "合成行政通知", "仅供离线测试的邮件正文。", "材料表.pdf"):
            self.assertNotIn(private, json.dumps(saved_status, ensure_ascii=False))
        self.assertEqual(config_before, (self.root / "config.json").read_bytes())
        self.assert_no_cursor_or_archive_changes()
        self.assertEqual(("SHUTDOWN",), client.calls[-1])
        self.assertEqual(1, client.calls.count(("SHUTDOWN",)))
        self.assertTrue(all(call[2] is True for call in client.calls if call[0] == "SELECT"))
        self.assertTrue(all("BODY.PEEK" in call[2] for call in client.calls if call[0] == "FETCH" and "BODY" in call[2]))
        self.assertFalse(any(call[0] in {"CLOSE", "EXPUNGE", "STORE", "LOGOUT"} for call in client.calls))
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(SECRET.encode("utf-8"), path.read_bytes())
                self.assertNotIn(b"483921", path.read_bytes())

    def test_retries_and_reviewed_metadata_are_forwarded_without_dashboard_write(self):
        dashboard = json.loads(self.dashboard_before)
        dashboard["coverage"]["through"] = "2026-09-07T20:00:00+08:00"
        dashboard["messages"] = [{"id": "old-mail", "category": "教学", "summary": "已核对摘要",
                                   "attachments": [{"id": "old-file", "name": "材料表.pdf", "status": "missing"}]},
                                  {"id": "done-mail", "attachments": [{"id": "done-file", "name": "已完成.pdf", "status": "success"}]}]
        (self.root / "dashboard.json").write_text(json.dumps(dashboard), encoding="utf-8")
        self.dashboard_before = (self.root / "dashboard.json").read_bytes()
        client = self.fixture_client({})

        def collected(connection, **arguments):
            self.assertIs(client, connection)
            self.assertEqual(["old-mail"], arguments["retry_message_ids"])
            self.assertEqual("2026-09-06T20:00:00+08:00", arguments["since"])
            return {"schema_version": 1, "account": ACCOUNT, "id": "imap-offline-result", "kind": "daily",
                    "started_at": NOW, "window": {"since": arguments["since"], "through": NOW, "complete": True},
                    "messages": [{"id": "old-mail", "summary": "待整理", "category": "待整理",
                                  "attachments": [{"id": "new-file", "name": "材料表.pdf", "sha256": "a" * 64}]}],
                    "actions": [], "errors": []}

        with patch.object(cli.mail_imap, "collect", side_effect=collected):
            summary = cli.collect_workspace(self.root, at=NOW)
        message = self.read_batch(summary)["messages"][0]
        self.assertEqual("old-file", message["attachments"][0]["id"])
        self.assertEqual("已核对摘要", message["summary"])
        self.assertEqual("教学", message["category"])
        self.assert_no_cursor_or_archive_changes()
        self.assertEqual(("SHUTDOWN",), client.calls[-1])

    def test_collection_failure_is_partial_and_always_shuts_down(self):
        client = self.fixture_client({})
        with patch.object(cli.mail_imap, "collect", side_effect=cli.mail_imap.ImapCollectionError("IMAP_FOLDER_LIST_FAILED")):
            summary = cli.collect_workspace(self.root, at=NOW)
        self.assertEqual("partial", summary["status"])
        self.assertEqual(["IMAP_FOLDER_LIST_FAILED"], summary["errors"])
        self.assertEqual(("SHUTDOWN",), client.calls[-1])
        self.assert_no_cursor_or_archive_changes()

    def test_cli_hides_unexpected_exception_and_returns_failure_code(self):
        output = io.StringIO()
        with patch.object(cli, "collect_workspace", side_effect=RuntimeError(SECRET)), redirect_stdout(output):
            code = cli.main(["--root", str(self.root)])
        self.assertEqual(1, code)
        self.assertEqual({"status": "error", "error": "IMAP_COLLECTION_SETUP_OR_STAGING_FAILED"}, json.loads(output.getvalue()))
        self.assertNotIn(SECRET, output.getvalue())

    def test_cli_partial_status_uses_exit_code_two_and_safe_json(self):
        self.read_mock.side_effect = credentials.CredentialNotFound(SECRET)
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(["--root", str(self.root), "--at", NOW])
        self.assertEqual(2, code)
        result = json.loads(output.getvalue())
        self.assertEqual("partial", result["status"])
        self.assertNotIn(SECRET, output.getvalue())


if __name__ == "__main__":
    unittest.main()
