import copy
import hashlib
import json
import os
import stat
import tempfile
import unittest
from email import policy
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils import mail_filing_source as source
from utils import mail_imap
from utils.mail_imap_credentials import CredentialNotFound


MESSAGE_ID = "<selected-mail@example.edu>"
OTHER_ID = "<other-mail@example.edu>"
ACCOUNT = "staff@example.edu"
SECRET = "fake-only-credential-marker"
BODY_MARKER = "private-body-marker"
FOLDERS = ["INBOX", "mark", "工作存档", "制度文件"]


def mail_bytes(identifier=MESSAGE_ID, *, attachment=True, subject="Selected notice"):
    message = EmailMessage()
    message["Message-ID"] = identifier
    message["Date"] = "Tue, 08 Sep 2026 09:00:00 +0800"
    message["From"] = "department@example.edu"
    message["Subject"] = subject
    message.set_content(BODY_MARKER)
    if attachment:
        message.add_attachment(b"verified-complete-attachment", maintype="application", subtype="pdf", filename="notice.pdf")
    return message.as_bytes(policy=policy.SMTP)


class FakeIMAP:
    """Only the permitted read-only operations are implemented."""

    def __init__(self, folders=None):
        self.folders = folders or {name: {} for name in FOLDERS}
        self.selected = None
        self.calls = []
        self.closed = False

    def list(self):
        self.calls.append(("LIST",))
        return "OK", [b'(\\HasNoChildren) "/" ' + mail_imap._quote(mail_imap.encode_modified_utf7(name)).encode("ascii")
                      for name in self.folders]

    def select(self, wire, readonly=False):
        self.calls.append(("SELECT", wire, readonly))
        assert readonly is True
        self.selected = mail_imap.decode_modified_utf7(wire.strip('"'))
        return "OK", [str(len(self.folders[self.selected])).encode()]

    def uid(self, command, *args):
        self.calls.append((command, *args))
        if command == "SEARCH":
            assert args == (None, "HEADER", "Message-ID", mail_imap._quote(MESSAGE_ID))
            return "OK", [b" ".join(str(uid).encode() for uid in self.folders[self.selected])]
        assert command == "FETCH"
        uid, query = int(args[0]), args[1]
        entry = self.folders[self.selected][uid]
        raw = entry["raw"]
        if query == "(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])":
            header = b"Message-ID: " + entry.get("header_id", MESSAGE_ID).encode() + b"\r\n\r\n"
            return "OK", [(f"1 (UID {uid} BODY[HEADER.FIELDS (MESSAGE-ID)] {{{len(header)}}}".encode(), header), b")"]
        if query == "(UID INTERNALDATE RFC822.SIZE)":
            size = entry.get("size", len(raw))
            return "OK", [f'1 (UID {uid} INTERNALDATE "08-Sep-2026 09:00:00 +0800" RFC822.SIZE {size})'.encode()]
        assert query == "(UID BODY.PEEK[])"
        return "OK", [(f"1 (UID {uid} BODY[] {{{len(raw)}}}".encode(), raw), b")"]

    def shutdown(self):
        self.closed = True
        self.calls.append(("SHUTDOWN",))


class MailFilingSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "workspace"
        self.root.mkdir()
        (self.root / "archive").mkdir()
        self.raw = mail_bytes()
        self.message = {"id": MESSAGE_ID, "received_at": "2026-09-08T09:00:00+08:00",
                        "folder": "INBOX", "attachments": []}
        config = {"account": ACCOUNT, "mail_folders": FOLDERS,
                  "imap": {"host": "mail.example.edu", "port": 993, "ssl": True,
                           "credential_target": f"CodexMailWorkbench/IMAP/mail.example.edu/{ACCOUNT}"}}
        (self.root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        self.credential_patch = patch.object(source, "read_credential", return_value=(ACCOUNT, SECRET))
        self.credential = self.credential_patch.start()
        self.addCleanup(self.credential_patch.stop)
        self.connect_patch = patch.object(source.mail_imap, "connect", side_effect=AssertionError("unexpected network access"))
        self.connect = self.connect_patch.start()
        self.addCleanup(self.connect_patch.stop)

    def store_raw(self, raw=None):
        raw = self.raw if raw is None else raw
        path = self.root / "archive" / "original.eml"
        path.write_bytes(raw)
        self.message.update(raw_eml_path="archive/original.eml", raw_eml_sha256=hashlib.sha256(raw).hexdigest(),
                            raw_eml_size=len(raw))
        return path

    def online_client(self, entries, folder="INBOX"):
        fake = FakeIMAP({name: entries if name == folder else {} for name in FOLDERS})
        self.connect.side_effect = None
        self.connect.return_value = fake
        return fake

    def assert_no_secret_in_errors(self, result):
        text = json.dumps(result["error_codes"])
        self.assertNotIn(SECRET, text)
        self.assertNotIn(BODY_MARKER, text)
        self.assertTrue(set(result["error_codes"]).issubset(source.ERROR_CODES))

    def test_verified_local_eml_returns_exact_full_source_without_network_or_writes(self):
        self.store_raw()
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = source.read_source(self.root, self.message)
        self.assertEqual("local_eml", result["source"])
        self.assertEqual(self.raw, result["raw"])
        self.assertEqual([], result["error_codes"])
        self.assertTrue(result["parsed"]["attachments_complete"])
        self.assertEqual(b"verified-complete-attachment", result["parsed"]["attachments"][0]["data"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.connect.assert_not_called()
        self.credential.assert_not_called()

    def test_absolute_local_path_inside_archive_is_allowed(self):
        self.message["raw_eml_path"] = str(self.store_raw())
        self.assertEqual("local_eml", source.read_source(self.root, self.message)["source"])

    def test_missing_original_does_not_trust_old_empty_attachment_index(self):
        result = source.read_source(self.root, self.message, allow_imap=False)
        self.assertEqual("unavailable", result["source"])
        self.assertEqual(["SOURCE_MISSING"], result["error_codes"])
        self.assertIsNone(result["parsed"])
        self.connect.assert_not_called()

    def test_local_digest_size_and_limits_are_checked(self):
        self.store_raw()
        for field, bad in [("raw_eml_sha256", "0" * 64), ("raw_eml_size", len(self.raw) + 1),
                           ("raw_eml_size", 0), ("raw_eml_size", source.MAX_SOURCE_BYTES + 1),
                           ("raw_eml_size", True)]:
            with self.subTest(field=field, bad=bad):
                message = {**self.message, field: bad}
                result = source.read_source(self.root, message, allow_imap=False)
                self.assertEqual(["SOURCE_CORRUPT"], result["error_codes"])
                self.assertIsNone(result["raw"])

    def test_exact_local_message_id_must_match(self):
        self.store_raw(mail_bytes(OTHER_ID))
        result = source.read_source(self.root, self.message, allow_imap=False)
        self.assertEqual(["SOURCE_ID_MISMATCH"], result["error_codes"])
        self.assertIsNone(result["raw"])

    def test_synthetic_id_can_use_verified_local_source_but_cannot_search_imap(self):
        raw = b"From: department@example.edu\r\nSubject: Notice\r\n\r\nplain text\r\n"
        self.store_raw(raw)
        self.message["id"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        self.assertEqual("local_eml", source.read_source(self.root, self.message)["source"])
        self.message.pop("raw_eml_path")
        result = source.read_source(self.root, self.message)
        self.assertIn("SOURCE_ID_UNSEARCHABLE", result["error_codes"])
        self.credential.assert_not_called()

    def test_unsafe_paths_are_rejected_without_online_fallback(self):
        self.store_raw()
        for bad in [str(self.root.parent / "secret.eml"), "../secret.eml", "archive/../secret.eml",
                    "archive/original.eml:stream", "config.json", "archive/config.env", "archive"]:
            with self.subTest(path=bad):
                result = source.read_source(self.root, {**self.message, "raw_eml_path": bad})
                self.assertEqual(["SOURCE_PATH_REJECTED"], result["error_codes"])
        self.credential.assert_not_called()

    def test_reparse_attribute_on_ancestor_is_rejected(self):
        self.store_raw()
        original_lstat = Path.lstat
        archive = self.root / "archive"

        def fake_lstat(path, *args, **kwargs):
            value = original_lstat(path, *args, **kwargs)
            if path == archive:
                return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=source._REPARSE_POINT)
            return value

        with patch.object(Path, "lstat", fake_lstat):
            result = source.read_source(self.root, self.message)
        self.assertEqual(["SOURCE_PATH_REJECTED"], result["error_codes"])
        self.credential.assert_not_called()

    def test_symlink_flag_on_source_is_rejected(self):
        path = self.store_raw()
        original_lstat = Path.lstat

        def fake_lstat(target, *args, **kwargs):
            value = original_lstat(target, *args, **kwargs)
            if target == path:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
            return value

        with patch.object(Path, "lstat", fake_lstat):
            result = source.read_source(self.root, self.message)
        self.assertEqual(["SOURCE_PATH_REJECTED"], result["error_codes"])

    def test_raced_handle_redirect_is_rejected_before_reading(self):
        self.store_raw()
        with patch.object(source, "_opened_path", return_value=self.root.parent / "elsewhere.eml"):
            result = source.read_source(self.root, self.message)
        self.assertEqual(["SOURCE_PATH_REJECTED"], result["error_codes"])
        self.assertIsNone(result["raw"])

    def test_sensitive_source_never_returns_raw_or_attachments(self):
        self.store_raw(mail_bytes(subject="邮箱验证码"))
        result = source.read_source(self.root, self.message)
        self.assertEqual(["SENSITIVE_SOURCE_SKIPPED"], result["error_codes"])
        self.assertIsNone(result["raw"])
        self.assertIsNone(result["parsed"])
        self.credential.assert_not_called()

    def test_incomplete_mime_is_explicit_and_not_claimed_as_zero_attachment_success(self):
        raw = (b"Message-ID: " + MESSAGE_ID.encode() + b"\r\nMIME-Version: 1.0\r\n"
               b'Content-Type: multipart/mixed; boundary="missing"\r\n\r\ntruncated MIME')
        self.store_raw(raw)
        result = source.read_source(self.root, self.message)
        self.assertEqual(["SOURCE_CORRUPT"], result["error_codes"])
        self.assertFalse(result["parsed"]["attachments_complete"])

    def test_online_fallback_searches_only_selected_id_in_configured_folders(self):
        client = self.online_client({42: {"raw": self.raw}}, folder="工作存档")
        result = source.read_source(self.root, self.message)
        self.assertEqual("imap", result["source"])
        self.assertEqual([], result["error_codes"])
        self.assertEqual(self.raw, result["raw"])
        self.assertTrue(client.closed)
        searches = [call for call in client.calls if call[0] == "SEARCH"]
        self.assertEqual(3, len(searches))
        self.assertTrue(all(call == ("SEARCH", None, "HEADER", "Message-ID", f'"{MESSAGE_ID}"') for call in searches))
        self.assertEqual(1, sum(call[0] == "FETCH" and call[2] == "(UID BODY.PEEK[])" for call in client.calls))
        self.assertFalse(any(call[0] in {"STORE", "MOVE", "EXPUNGE", "CLOSE", "APPEND", "DELETE"} for call in client.calls))
        self.connect.assert_called_once_with("mail.example.edu", 993, ACCOUNT, SECRET, timeout=20)

    def test_online_search_substring_hit_does_not_fetch_unrelated_body(self):
        client = self.online_client({1: {"raw": mail_bytes(OTHER_ID), "header_id": OTHER_ID},
                                     2: {"raw": self.raw}})
        result = source.read_source(self.root, self.message)
        self.assertEqual("imap", result["source"])
        bodies = [call for call in client.calls if call[0] == "FETCH" and call[2] == "(UID BODY.PEEK[])"]
        self.assertEqual([("FETCH", "2", "(UID BODY.PEEK[])")], bodies)

    def test_exact_header_but_wrong_body_id_is_rejected_and_next_match_checked(self):
        client = self.online_client({1: {"raw": mail_bytes(OTHER_ID)}, 2: {"raw": self.raw}})
        result = source.read_source(self.root, self.message)
        self.assertEqual(self.raw, result["raw"])
        self.assertEqual([], result["error_codes"])
        self.assertTrue(client.closed)

    def test_corrupt_local_can_recover_online_without_carrying_resolved_error(self):
        self.store_raw()
        self.message["raw_eml_sha256"] = "0" * 64
        self.online_client({1: {"raw": self.raw, "size": len(self.raw) + 77}})
        result = source.read_source(self.root, self.message)
        self.assertEqual("imap", result["source"])
        self.assertEqual([], result["error_codes"])

    def test_nonexistent_exact_id_returns_not_found_and_reads_no_bodies(self):
        client = self.online_client({})
        result = source.read_source(self.root, self.message)
        self.assertEqual("unavailable", result["source"])
        self.assertIn("SOURCE_NOT_FOUND", result["error_codes"])
        self.assertFalse(any(call[0] == "FETCH" for call in client.calls))
        self.assertEqual(4, sum(call[0] == "SEARCH" for call in client.calls))

    def test_unsafe_or_synthetic_online_ids_do_not_read_credentials(self):
        for identifier in ["sha256:" + "a" * 64, "<bad\r\nID@example.edu>", "<missing-at>",
                           '<injected"@example.edu>', "<a b@example.edu>"]:
            with self.subTest(identifier=identifier):
                result = source.read_source(self.root, {**self.message, "id": identifier})
                self.assertIn("SOURCE_ID_UNSEARCHABLE", result["error_codes"])
        self.credential.assert_not_called()

    def test_missing_or_mismatched_saved_account_requires_user_authentication(self):
        self.credential.side_effect = CredentialNotFound(SECRET)
        result = source.read_source(self.root, self.message)
        self.assertIn("SOURCE_AUTH_REQUIRED", result["error_codes"])
        self.assert_no_secret_in_errors(result)
        self.credential.side_effect = None
        self.credential.return_value = ("other@example.edu", SECRET)
        result = source.read_source(self.root, self.message)
        self.assertIn("SOURCE_AUTH_REQUIRED", result["error_codes"])
        self.connect.assert_not_called()

    def test_network_exception_is_sanitized_and_connection_is_closed(self):
        client = self.online_client({1: {"raw": self.raw}})
        client.uid = Mock(side_effect=RuntimeError(SECRET + BODY_MARKER))
        result = source.read_source(self.root, self.message)
        self.assertIn("SOURCE_FETCH_FAILED", result["error_codes"])
        self.assert_no_secret_in_errors(result)
        self.assertTrue(client.closed)

    def test_oversized_metadata_does_not_fetch_body(self):
        client = self.online_client({1: {"raw": self.raw, "size": source.MAX_SOURCE_BYTES + 1}})
        result = source.read_source(self.root, self.message)
        self.assertIn("SOURCE_CORRUPT", result["error_codes"])
        self.assertFalse(any(call[0] == "FETCH" and call[2] == "(UID BODY.PEEK[])" for call in client.calls))

    def test_online_sensitive_raw_is_not_exposed(self):
        client = self.online_client({1: {"raw": mail_bytes(subject="Password reset")}})
        result = source.read_source(self.root, self.message)
        self.assertIn("SENSITIVE_SOURCE_SKIPPED", result["error_codes"])
        self.assertIsNone(result["parsed"])
        self.assertIsNone(result["raw"])
        self.assertTrue(client.closed)


if __name__ == "__main__":
    unittest.main()
