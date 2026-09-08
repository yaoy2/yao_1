import hashlib
import json
import ssl
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

from utils import mail_imap as imap


def make_message(identifier="<test@example.edu>", subject="Administrative notice", body="Please review the attached form.", attachment=False):
    message = EmailMessage()
    message["Message-ID"] = identifier
    message["From"] = "Office <office@example.edu>"
    message["Subject"] = subject
    message.set_content(body)
    if attachment:
        message.add_attachment(b"form contents", maintype="application", subtype="octet-stream", filename="表格.docx")
    return message.as_bytes()


class FakeImap:
    """A server that returns oversized date-search candidates deliberately."""

    def __init__(self, messages=None, folders=None):
        self.messages = messages or {"INBOX": {}}
        self.folders = folders or [b'(\\HasNoChildren) "/" "INBOX"']
        self.calls = []
        self.selected = None
        self.failure = {}
        self.truncate = set()
        self.partial = set()
        self.size_overrides = {}

    def list(self):
        self.calls.append(("LIST",))
        return "OK", self.folders

    def select(self, name, readonly=False):
        self.calls.append(("SELECT", name, readonly))
        self.selected = imap._unquote(name.encode("ascii")).decode("ascii")
        return "OK", [str(len(self.messages.get(self.selected, {}))).encode()]

    def uid(self, command, *args):
        self.calls.append((command,) + args)
        messages = self.messages[self.selected]
        if command == "SEARCH":
            if self.failure.get("search"):
                return "NO", [b"server text should not be retained"]
            if args[1] == "HEADER":
                identifier = imap._unquote(args[3].encode("ascii"))
                selected = [uid for uid, (raw, date) in messages.items() if identifier in raw]
            else:
                selected = list(messages)
            # Split and reorder results to ensure there is no page/sequence assumption.
            selected.reverse()
            return "OK", [" ".join(str(uid) for uid in selected[::2]).encode(),
                          " ".join(str(uid) for uid in selected[1::2]).encode()]
        if command != "FETCH":
            raise AssertionError("unexpected mutating IMAP command")
        uid = int(args[0])
        if uid in self.failure:
            return "NO", [b"private server error"]
        raw, date = messages[uid]
        if "BODY.PEEK[]" not in args[1]:
            size = self.size_overrides.get(uid, len(raw))
            return "OK", [f'1 (UID {uid} RFC822.SIZE {size} INTERNALDATE "{date}")'.encode()]
        payload = raw[:-1] if uid in self.truncate else raw
        part = "<0>" if uid in self.partial else ""
        return "OK", [(f"1 (UID {uid} BODY[]{part} {{{len(raw)}}}".encode(), payload), b")"]


class ImapCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.date = "08-Sep-2026 12:00:00 +0800"

    def collect(self, client, **overrides):
        arguments = {"account": "sample@example.edu", "folders": ["收件箱"],
                     "since": "2026-09-08T00:00:00+08:00", "through": "2026-09-08T20:00:00+08:00",
                     "staging_dir": self.base, "source_url": "https://mail.nsu.edu.cn/owa/"}
        arguments.update(overrides)
        return imap.collect(client, **arguments)

    def test_verified_tls_and_authentication_error_redaction(self):
        with patch.object(imap.imaplib, "IMAP4_SSL") as constructor:
            client = constructor.return_value
            client.login.return_value = ("OK", [b"authenticated"])
            self.assertIs(client, imap.connect("mail.example.edu", 993, "account", "secret"))
            context = constructor.call_args.kwargs["ssl_context"]
            self.assertTrue(context.check_hostname)
            self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)
            self.assertEqual(20, constructor.call_args.kwargs["timeout"])
        with patch.object(imap.imaplib, "IMAP4_SSL") as constructor:
            constructor.return_value.login.side_effect = imap.imaplib.IMAP4.error("private password and server content")
            with self.assertRaisesRegex(imap.ImapCollectionError, "^IMAP_AUTHENTICATION_FAILED$"):
                imap.connect("mail.example.edu", 993, "account", "secret")
            constructor.return_value.logout.assert_called_once()

    def test_all_uids_are_peeked_readonly_and_files_are_real(self):
        messages = {uid: (make_message(f"<{uid}@example.edu>", attachment=True), self.date) for uid in (1, 7, 40, 101, 300)}
        client = FakeImap({"INBOX": messages})
        batch = self.collect(client)
        self.assertTrue(batch["window"]["complete"])
        self.assertEqual(5, len(batch["messages"]))
        self.assertEqual([], batch["actions"])
        selected = [call for call in client.calls if call[0] == "SELECT"]
        self.assertEqual([("SELECT", '"INBOX"', True)], selected)
        fetched = [call for call in client.calls if call[0] == "FETCH" and "BODY" in call[2]]
        self.assertEqual({"1", "7", "40", "101", "300"}, {call[1] for call in fetched})
        self.assertTrue(all(call[2] == "(UID BODY.PEEK[])" for call in fetched))
        for message in batch["messages"]:
            raw_path = Path(message["raw_eml_download_path"])
            self.assertTrue(raw_path.is_relative_to(self.base))
            self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(), message["raw_sha256"])
            self.assertEqual("待整理", message["summary"])
            self.assertEqual(b"form contents", Path(message["attachments"][0]["download_path"]).read_bytes())
        json.dumps(batch)  # No undecoded bytes or unserializable metadata escape staging.

    def test_exact_date_filter_uses_internaldate_and_both_boundaries(self):
        dates = {1: "07-Sep-2026 23:59:59 +0800", 2: "08-Sep-2026 00:00:00 +0800",
                 3: "08-Sep-2026 12:00:00 +0000", 4: "08-Sep-2026 20:00:01 +0800",
                 5: "07-Sep-2026 23:00:00 -0700"}
        client = FakeImap({"INBOX": {uid: (make_message(f"<{uid}@example.edu>"), date) for uid, date in dates.items()}})
        batch = self.collect(client)
        self.assertTrue(batch["window"]["complete"])
        self.assertEqual({"<2@example.edu>", "<3@example.edu>", "<5@example.edu>"}, {m["id"] for m in batch["messages"]})
        search = next(call for call in client.calls if call[0] == "SEARCH")
        self.assertEqual(("SEARCH", None, "SINCE", "06-Sep-2026", "BEFORE", "10-Sep-2026"), search)
        self.assertEqual(3, sum(call[0] == "FETCH" and "BODY.PEEK" in call[2] for call in client.calls))

    def test_failure_keeps_other_messages_and_marks_window_incomplete(self):
        client = FakeImap({"INBOX": {uid: (make_message(f"<{uid}@example.edu>"), self.date) for uid in (1, 2, 3)}})
        client.failure[2] = True
        batch = self.collect(client)
        self.assertFalse(batch["window"]["complete"])
        self.assertEqual(2, len(batch["messages"]))
        self.assertIn("IMAP_METADATA_FAILED", batch["errors"])
        self.assertNotIn("private server", json.dumps(batch))

    def test_truncated_or_partial_body_never_counts_as_complete(self):
        for mode in ("truncate", "partial"):
            with self.subTest(mode=mode):
                client = FakeImap({"INBOX": {1: (make_message(), self.date)}})
                getattr(client, mode).add(1)
                batch = self.collect(client)
                self.assertFalse(batch["window"]["complete"])
                self.assertIn("IMAP_BODY_INCOMPLETE", batch["errors"])
                self.assertEqual([], batch["messages"])

    def test_size_limit_does_not_download_body(self):
        client = FakeImap({"INBOX": {1: (make_message(), self.date)}})
        batch = self.collect(client, max_message_bytes=50)
        self.assertFalse(batch["window"]["complete"])
        self.assertIn("IMAP_MESSAGE_SIZE_LIMIT", batch["errors"])
        self.assertFalse(any(call[0] == "FETCH" and "BODY" in call[2] for call in client.calls))

    def test_estimated_rfc822_size_mismatch_preserves_complete_verified_literal(self):
        for difference in (-25, 25):
            with self.subTest(difference=difference):
                raw = make_message()
                client = FakeImap({"INBOX": {1: (raw, self.date)}})
                client.size_overrides[1] = len(raw) + difference
                batch = self.collect(client)
                self.assertTrue(batch["window"]["complete"])
                self.assertEqual([], batch["errors"])
                self.assertEqual(1, batch["collection"]["size_mismatches"])
                self.assertEqual(1, batch["collection"]["folders"][0]["size_mismatches"])
                self.assertEqual(raw, Path(batch["messages"][0]["raw_eml_download_path"]).read_bytes())

    def test_actual_body_size_limit_is_enforced_when_estimate_is_too_small(self):
        client = FakeImap({"INBOX": {1: (make_message(), self.date)}})
        client.size_overrides[1] = 10
        with patch.object(imap, "parse_message") as parser:
            batch = self.collect(client, max_message_bytes=50)
        self.assertFalse(batch["window"]["complete"])
        self.assertEqual(["IMAP_MESSAGE_SIZE_LIMIT"], batch["errors"])
        self.assertEqual([], batch["messages"])
        parser.assert_not_called()
        self.assertEqual([], list(Path(batch["collection"]["staging_dir"]).rglob("*.eml")))

    def test_uid_after_body_literal_is_accepted(self):
        raw = make_message()
        client = FakeImap({"INBOX": {1: (raw, self.date)}})
        original = client.uid

        def reordered(command, *args):
            if command == "FETCH" and "BODY.PEEK" in args[1]:
                return "OK", [(f"1 (BODY[] {{{len(raw)}}}".encode(), raw), b" UID 1)"]
            return original(command, *args)

        client.uid = reordered
        self.assertTrue(self.collect(client)["window"]["complete"])

    def test_mime_error_is_redacted_and_blocks_completion(self):
        client = FakeImap({"INBOX": {1: (make_message(), self.date)}})
        with patch.object(imap, "parse_message", side_effect=ValueError("sensitive raw content")):
            batch = self.collect(client)
        self.assertFalse(batch["window"]["complete"])
        self.assertEqual(["IMAP_MIME_PARSE_FAILED"], batch["errors"])
        self.assertEqual([], list(Path(batch["collection"]["staging_dir"]).rglob("*.eml")))

    def test_retry_search_failure_does_not_discard_regular_messages(self):
        client = FakeImap({"INBOX": {1: (make_message(), self.date)}})
        original = client.uid

        def failed_retry(command, *args):
            if command == "SEARCH" and args[1] == "HEADER":
                return "NO", [b"not available"]
            return original(command, *args)

        client.uid = failed_retry
        batch = self.collect(client, retry_message_ids=["<missing@example.edu>"])
        self.assertFalse(batch["window"]["complete"])
        self.assertEqual(1, len(batch["messages"]))
        self.assertIn("IMAP_RETRY_SEARCH_FAILED", batch["errors"])

    def test_empty_verified_mailbox_is_complete_but_search_failure_is_not(self):
        client = FakeImap()
        self.assertTrue(self.collect(client)["window"]["complete"])
        client.failure["search"] = True
        batch = self.collect(client)
        self.assertFalse(batch["window"]["complete"])
        self.assertIn("IMAP_SEARCH_FAILED", batch["errors"])

    def test_missing_and_nonselectable_folders_do_not_get_guessed(self):
        client = FakeImap(folders=[b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "MARK"',
                                   f'(\\Noselect) "/" "{imap.encode_modified_utf7("工作存档")}"'.encode()])
        batch = self.collect(client, folders=["收件箱", "mark", "工作存档", "制度文件"])
        self.assertFalse(batch["window"]["complete"])
        self.assertEqual(1, len([call for call in client.calls if call[0] == "SELECT"]))
        self.assertIn("IMAP_FOLDER_NOT_FOUND", batch["errors"])
        self.assertIn("IMAP_FOLDER_NOT_SELECTABLE", batch["errors"])

    def test_unicode_folder_is_selected_using_encoded_exact_name(self):
        wire = imap.encode_modified_utf7("工作存档")
        client = FakeImap({wire: {1: (make_message(), self.date)}},
                          [f'(\\HasNoChildren) "/" "{wire}"'.encode()])
        batch = self.collect(client, folders=["工作存档"])
        self.assertTrue(batch["window"]["complete"])
        self.assertIn(("SELECT", '"' + wire + '"', True), client.calls)

    def test_authentication_notice_is_not_persisted(self):
        raw = make_message(subject="Your verification code is 123456", body="Your one-time password is 123456.", attachment=True)
        client = FakeImap({"INBOX": {1: (raw, self.date)}})
        batch = self.collect(client)
        self.assertTrue(batch["window"]["complete"])
        self.assertEqual([], batch["messages"])
        self.assertEqual({"count": 1, "received_at": ["2026-09-08T12:00:00+08:00"]},
                         batch["collection"]["skipped_authentication_notifications"])
        files = list(Path(batch["collection"]["staging_dir"]).rglob("*"))
        self.assertEqual(["evidence.json"], [path.name for path in files])
        self.assertNotIn("123456", files[0].read_text(encoding="utf-8"))

    def test_explicit_old_retry_is_collected_and_missing_retry_blocks_complete(self):
        client = FakeImap({"INBOX": {1: (make_message("<old@example.edu>", attachment=True), "01-Sep-2026 12:00:00 +0800")}})
        batch = self.collect(client, retry_message_ids=["<old@example.edu>"])
        self.assertTrue(batch["window"]["complete"])
        self.assertTrue(batch["messages"][0]["retry_of_existing"])
        self.assertEqual(1, batch["collection"]["retry"]["resolved_count"])
        missing = self.collect(client, retry_message_ids=["<missing@example.edu>"])
        self.assertFalse(missing["window"]["complete"])
        self.assertIn("IMAP_RETRY_NOT_COMPLETED", missing["errors"])
        self.assertEqual([], missing["messages"])

    def test_unsearchable_hashed_retry_is_explicitly_incomplete(self):
        batch = self.collect(FakeImap(), retry_message_ids=["sha256:" + "a" * 64])
        self.assertFalse(batch["window"]["complete"])
        self.assertIn("IMAP_RETRY_ID_UNSEARCHABLE", batch["errors"])

    def test_identical_cross_folder_copy_is_deduplicated(self):
        raw = make_message()
        client = FakeImap({"INBOX": {1: (raw, self.date)}, "mark": {4: (raw, self.date)}},
                          [b'() "/" "INBOX"', b'() "/" "mark"'])
        batch = self.collect(client, folders=["收件箱", "mark"])
        self.assertTrue(batch["window"]["complete"])
        self.assertEqual(1, len(batch["messages"]))

    def test_same_message_id_with_different_content_is_incomplete(self):
        client = FakeImap({"INBOX": {1: (make_message(), self.date), 2: (make_message(body="Changed body"), self.date)}})
        batch = self.collect(client)
        self.assertFalse(batch["window"]["complete"])
        self.assertIn("IMAP_MESSAGE_ID_CONTENT_CONFLICT", batch["errors"])

    def test_incomplete_attachments_cannot_resolve_retry(self):
        client = FakeImap({"INBOX": {1: (make_message(), self.date)}})
        parsed = {"id": "<test@example.edu>", "attachments_complete": False, "attachments": []}
        with patch.object(imap, "parse_message", return_value=parsed):
            batch = self.collect(client, retry_message_ids=[parsed["id"]])
        self.assertFalse(batch["window"]["complete"])
        self.assertIn("IMAP_ATTACHMENTS_INCOMPLETE", batch["errors"])
        self.assertEqual(0, batch["collection"]["retry"]["resolved_count"])

    def test_empty_mime_attachment_stays_missing_without_empty_staged_file(self):
        message = EmailMessage()
        message["Message-ID"] = "<empty-attachment@example.edu>"
        message["Subject"] = "Submit the form"
        message.set_content("Attached is the form.")
        message.add_attachment(b"", maintype="application", subtype="octet-stream", filename="empty.xlsx")
        client = FakeImap({"INBOX": {1: (message.as_bytes(), self.date)}})
        batch = self.collect(client, retry_message_ids=["<empty-attachment@example.edu>"])
        self.assertFalse(batch["window"]["complete"])
        self.assertIn("IMAP_ATTACHMENTS_INCOMPLETE", batch["errors"])
        self.assertEqual(0, batch["collection"]["retry"]["resolved_count"])
        collected = batch["messages"][0]
        self.assertFalse(collected["attachments_complete"])
        self.assertEqual(1, collected["expected_attachment_count"])
        attachment = collected["attachments"][0]
        self.assertEqual("missing", attachment["status"])
        self.assertEqual("MIME_ATTACHMENT_EMPTY", attachment["error"])
        self.assertEqual(0, attachment["size"])
        self.assertNotIn("download_path", attachment)
        self.assertEqual(["original.eml"], [path.name for path in Path(collected["raw_eml_download_path"]).parent.iterdir()])


class FolderEncodingTests(unittest.TestCase):
    def test_modified_utf7_roundtrip(self):
        for name in ("INBOX", "收件箱", "工作存档", "制度文件", "项目 & 表格/2026", "emoji 😀"):
            with self.subTest(name=name):
                wire = imap.encode_modified_utf7(name)
                self.assertTrue(wire.isascii())
                self.assertEqual(name, imap.decode_modified_utf7(wire))
        self.assertEqual("&U,BTFw-", imap.encode_modified_utf7("台北"))
        self.assertEqual("&-", imap.encode_modified_utf7("&"))

    def test_list_atom_quoted_and_literal(self):
        self.assertEqual("INBOX", imap.parse_list_response(b'(\\Inbox) NIL INBOX')["name"])
        self.assertEqual('Work "folder"', imap.parse_list_response(b'() "/" "Work \\"folder\\""')["name"])
        wire = imap.encode_modified_utf7("制度文件").encode()
        parsed = imap.parse_list_response((f'(\\Noselect) "/" {{{len(wire)}}}'.encode(), wire))
        self.assertEqual("制度文件", parsed["name"])
        self.assertFalse(parsed["selectable"])

    def test_malformed_folder_list_is_a_fixed_error(self):
        for item in (b"bad LIST body", b'() "/" "&invalid"', (b'() "/" {99}', b"short")):
            with self.subTest(item=item):
                with self.assertRaisesRegex(imap.ImapCollectionError, "^IMAP_FOLDER_LIST_FAILED$"):
                    imap.discover_folders(FakeImap(folders=[item]))


if __name__ == "__main__":
    unittest.main()
