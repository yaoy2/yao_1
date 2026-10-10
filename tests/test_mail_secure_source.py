import contextlib, io, json, unittest
from unittest.mock import Mock, patch
from utils import mail_secure_source as source
from scripts import mail_secure_preview as cli
from utils.mail_notice_policy import reject_legacy_mail_io, EdgeOnlineOnlyError
from utils.mail_imap_credentials import _validate_target, CredentialError

HEADERS = b"From: Sender <sender@example.invalid>\r\nTo: reader@example.invalid\r\nSubject: Notice\r\nDate: Fri, 09 Oct 2026 10:00:00 +0800\r\nMessage-ID: <notice@example.invalid>\r\n\r\n"
START = "2026-09-09T06:00:00+00:00"
END = "2026-10-09T06:00:00+00:00"


def backend():
    b = Mock()
    b.ACCOUNT = "staff@nsu.edu.cn"
    b.CHUNK = 65536
    b.discover.return_value = [
        {"wire": "INBOX", "name": "Inbox", "flags": []},
        {"wire": "Sent", "name": "已发送邮件", "flags": ["\\sent"]},
        {"wire": "Outbox", "name": "发件箱", "flags": []},
        {"wire": "Calendar", "name": "日历", "flags": []},
    ]
    b.examine.return_value = (7, 550)
    b.clean.side_effect = lambda x: x
    b.imap_date.side_effect = lambda d: d.strftime("%d-%b-%Y")
    b.fetch_chunk.return_value = HEADERS
    b.fetch_metadata.return_value = {"received_utc": "2026-10-08T01:00:00+00:00"}
    b.read_message.return_value = {
        "Subject": "Notice",
        "Message-ID": "<notice@example.invalid>",
        "body": "x" * 220,
        "body_complete": True,
        "body_scope": "selected_inline_text_parts",
        "flags_unchanged": True,
        "non_body_parts_not_downloaded": 2,
    }
    b.connect.return_value.uid.return_value = ("OK", [b"42"])
    return b


class SecureSourceTests(unittest.TestCase):
    def test_plan_never_loads_backend(self):
        with patch.object(
            source, "_load_backend", side_effect=AssertionError("not allowed")
        ):
            result = source.plan()
        self.assertFalse(result["credentials_read"])
        self.assertFalse(result["network_used"])
        self.assertEqual(result["status"], "prepared_not_enabled")

    def test_approval_gate_precedes_import(self):
        with patch.object(source, "_load_backend") as load:
            with self.assertRaisesRegex(
                source.SecureSourceError, "SECURE_READ_APPROVAL_REQUIRED"
            ):
                source.NoticeReader()
            load.assert_not_called()

    def test_missing_optional_backend_is_reported_without_import(self):
        with (
            patch.object(source.Path, "is_file", return_value=False),
            patch.object(source.importlib.util, "spec_from_file_location") as load,
        ):
            result = source.plan()
            self.assertFalse(result["backend_exists"])
            self.assertFalse(result["credentials_read"])
            self.assertFalse(result["network_used"])
            with self.assertRaisesRegex(
                source.SecureSourceError, "SECURE_BACKEND_UNAVAILABLE"
            ):
                source._load_backend()
            load.assert_not_called()

    def test_only_inbox_and_sent_selected(self):
        b = backend()
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            self.assertEqual(set(r.folders), {"inbox", "sent"})
            with self.assertRaises(source.SecureSourceError):
                r.body("outbox", 42, 7)
            with self.assertRaises(source.SecureSourceError):
                r.body("Calendar", 42, 7)
        b.connect.return_value.disconnect.assert_called_once()

    def test_ambiguous_sent_does_not_fallback(self):
        b = backend()
        b.discover.return_value.append(
            {"wire": "AnotherSent", "name": "Sent Items", "flags": []}
        )
        with patch.object(source, "_load_backend", return_value=b):
            with self.assertRaisesRegex(
                source.SecureSourceError, "MAIL_FOLDER_SCOPE_UNCONFIRMED"
            ):
                with source.NoticeReader(approved=True):
                    pass
        b.fetch_chunk.assert_not_called()

    def test_failed_auth_not_retried_and_sanitized(self):
        b = backend()
        b.connect.side_effect = RuntimeError("synthetic-secret-server-detail")
        with patch.object(source, "_load_backend", return_value=b):
            with self.assertRaises(source.SecureSourceError) as ex:
                with source.NoticeReader(approved=True):
                    pass
        self.assertEqual(str(ex.exception), "MAIL_SOURCE_FAILED")
        self.assertEqual(b.connect.call_count, 1)

    def test_auth_failure_code_preserved_without_details(self):
        b = backend()
        b.connect.side_effect = RuntimeError("authentication_failed_no_retry")
        with patch.object(source, "_load_backend", return_value=b):
            with self.assertRaisesRegex(
                source.SecureSourceError, "MAIL_AUTHENTICATION_FAILED_NO_RETRY"
            ):
                with source.NoticeReader(approved=True):
                    pass

    def test_header_page_no_body_or_writes(self):
        b = backend()
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            d = r.header_page("inbox", START, END, span=100)
        self.assertEqual(d["next_uid"], 101)
        self.assertFalse(d["inventory_complete"])
        self.assertEqual(d["messages"][0]["source_transport"], "secure_imap")
        self.assertEqual(d["messages"][0]["folder"], "Inbox")
        self.assertNotIn("body_text", d["messages"][0])
        b.read_message.assert_not_called()
        b.fetch_chunk.assert_called_once_with(
            b.connect.return_value, 42, "HEADER", 0, 65536
        )
        b.connect.return_value.uid.assert_called_once()

    def test_final_header_page_and_fixed_uid_bound(self):
        b = backend()
        b.connect.return_value.uid.return_value = ("OK", [b"520"])
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            d = r.header_page(
                "sent", START, END, next_uid=501, upper_uid=550, uidvalidity=7
            )
        self.assertTrue(d["inventory_complete"])
        self.assertIsNone(d["next_uid"])
        b.examine.assert_called_once_with(b.connect.return_value, "Sent", 7)
        self.assertEqual(d["messages"][0]["role"], "sent")

    def test_cursor_requires_validity(self):
        b = backend()
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            with self.assertRaisesRegex(
                source.SecureSourceError, "CURSOR_IDENTITY_REQUIRED"
            ):
                r.header_page("inbox", START, END, upper_uid=500)
        b.fetch_chunk.assert_not_called()

    def test_continuation_requires_fixed_bound_before_access(self):
        b = backend()
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            with self.assertRaisesRegex(
                source.SecureSourceError, "CURSOR_IDENTITY_REQUIRED"
            ):
                r.header_page("inbox", START, END, next_uid=101)
        b.examine.assert_not_called()

    def test_cannot_skip_beyond_end_and_claim_coverage(self):
        b = backend()
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            with self.assertRaisesRegex(source.SecureSourceError, "INVALID_PAGE"):
                r.header_page(
                    "inbox", START, END, next_uid=600, upper_uid=550, uidvalidity=7
                )
        b.fetch_chunk.assert_not_called()

    def test_invalid_window_excluded_before_access(self):
        for a, z in [
            ("2026-01-01", "2026-01-02"),
            ("2026-01-01T00:00:00Z", END),
            (END, START),
            (None, END),
        ]:
            with self.subTest(a=a, z=z), self.assertRaises(source.SecureSourceError):
                source.window(a, z)

    def test_exact_end_excluded_before_header_read(self):
        b = backend()
        b.fetch_metadata.return_value = {"received_utc": END}
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            d = r.header_page("inbox", START, END)
        self.assertEqual(d["messages"], [])
        b.fetch_chunk.assert_not_called()

    def test_minutes_blocked_before_metadata_and_body(self):
        b = backend()
        b.fetch_chunk.return_value = HEADERS.replace(
            b"Subject: Notice", b"Subject: Meeting Minutes"
        )
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            d = r.body("inbox", 42, 7)
        self.assertEqual(d["status"], "excluded")
        self.assertFalse(d["body_content_read"])
        b.fetch_metadata.assert_not_called()
        b.read_message.assert_not_called()

    def test_body_is_transient_and_attachment_gap_explicit(self):
        b = backend()
        with (
            patch.object(source, "_load_backend", return_value=b),
            patch.object(
                source.Path, "write_text", side_effect=AssertionError("no files")
            ),
            source.NoticeReader(approved=True) as r,
        ):
            d = r.body("inbox", 42, 7, chars=100)
        self.assertEqual(len(d["body_text"]), 100)
        self.assertEqual(d["next_offset"], 100)
        self.assertFalse(d["attachment_content_read"])
        self.assertTrue(d["attachment_gap"])
        self.assertFalse(d["persistent_mail_cache"])
        self.assertFalse(d["automatic_todo"])
        self.assertNotEqual(d["source_transport"], "edge")

    def test_header_change_is_not_silently_accepted(self):
        b = backend()
        b.read_message.return_value["Subject"] = "Other"
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            with self.assertRaisesRegex(
                source.SecureSourceError, "MAIL_HEADERS_CHANGED"
            ):
                r.body("sent", 42, 7)

    def test_uidvalidity_error_does_not_continue(self):
        b = backend()
        b.examine.side_effect = RuntimeError("uidvalidity_changed_start_new_job")
        with (
            patch.object(source, "_load_backend", return_value=b),
            source.NoticeReader(approved=True) as r,
        ):
            with self.assertRaisesRegex(
                source.SecureSourceError, "MAIL_UIDVALIDITY_CHANGED"
            ):
                r.body("inbox", 42, 7)
        b.fetch_chunk.assert_not_called()

    def test_legacy_entrypoints_stay_blocked(self):
        with self.assertRaises(EdgeOnlineOnlyError):
            reject_legacy_mail_io()
        with self.assertRaises(CredentialError):
            _validate_target("Codex.NSUMail.IMAP.ReadOnly:staff@nsu.edu.cn")


class CommandTests(unittest.TestCase):
    def run_cli(self, args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(args)
        return rc, json.loads(out.getvalue())

    def test_default_is_offline_plan(self):
        with patch.object(
            source, "_load_backend", side_effect=AssertionError("backend")
        ):
            rc, d = self.run_cli([])
        self.assertEqual(rc, 0)
        self.assertFalse(d["network_used"])

    def test_live_cli_requires_approval(self):
        with patch.object(source, "_load_backend") as load:
            rc, d = self.run_cli(
                ["headers", "--role", "inbox", "--start", START, "--end", END]
            )
        self.assertEqual(rc, 2)
        self.assertEqual(d["code"], "SECURE_READ_APPROVAL_REQUIRED")
        load.assert_not_called()

    def test_invalid_arguments_do_not_echo_values(self):
        rc, d = self.run_cli(["--password", "synthetic-no-print"])
        self.assertEqual(rc, 2)
        self.assertNotIn("synthetic-no-print", json.dumps(d))

    def test_invalid_window_before_backend(self):
        with patch.object(source, "_load_backend") as load:
            rc, d = self.run_cli(
                [
                    "headers",
                    "--approved-read",
                    "--role",
                    "inbox",
                    "--start",
                    "bad",
                    "--end",
                    END,
                ]
            )
        self.assertEqual(rc, 2)
        load.assert_not_called()


class DecoderIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(
        source.BACKEND_PATH.is_file()
        and source.BACKEND_PATH.with_name("nsu_mail_reader.py").is_file(),
        "Optional local secure-mail backend and standalone reader are not installed",
    )
    def test_both_entries_load_same_core_and_decoder(self):
        import importlib.util

        core = source._load_backend()
        path = source.BACKEND_PATH.with_name("nsu_mail_reader.py")
        spec = importlib.util.spec_from_file_location("synthetic_standalone", path)
        standalone = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(standalone)
        self.assertEqual(
            source.Path(core.__file__).resolve(),
            source.Path(standalone.core.__file__).resolve(),
        )
        raw = "\u5586 15:00".encode("gbk")
        p = {"encoding": "8BIT", "charset": "gb2312", "subtype": "PLAIN"}
        self.assertEqual(core.decode_part(raw, p), standalone.core.decode_part(raw, p))
        self.assertEqual(core.decode_part(raw, p), "\u5586 15:00")

    @unittest.skipUnless(
        source.BACKEND_PATH.is_file(),
        "Optional local secure-mail backend is not installed",
    )
    def test_adapter_uses_real_decoder_without_network_and_keeps_pagination(self):
        core = source._load_backend()
        client = Mock()
        client.uid.return_value = ("OK", [b"1 (UID 42 FLAGS ())"])
        text = "\u5586 15:00 " * 30
        raw = text.encode("gbk")
        meta = {
            "BODYSTRUCTURE": [
                "TEXT",
                "PLAIN",
                ["CHARSET", "GB2312"],
                None,
                None,
                "8BIT",
                len(raw),
                1,
            ],
            "FLAGS": [],
            "received_utc": "2026-10-08T01:00:00+00:00",
        }
        folders = [
            {"wire": "INBOX", "name": "Inbox", "flags": []},
            {"wire": "Sent", "name": "Sent Items", "flags": ["\\sent"]},
        ]

        def chunk(client, uid, section, offset, count):
            return HEADERS if section == "HEADER" else raw[offset : offset + count]

        with (
            patch.object(source, "_load_backend", return_value=core),
            patch.object(core, "connect", return_value=client),
            patch.object(core, "discover", return_value=folders),
            patch.object(core, "examine", return_value=(7, 550)),
            patch.object(core, "fetch_metadata", return_value=meta),
            patch.object(core, "fetch_chunk", side_effect=chunk),
        ):
            with source.NoticeReader(approved=True) as reader:
                first = reader.body("sent", 42, 7, chars=100)
                last = reader.body(
                    "sent", 42, 7, offset=first["next_offset"], chars=20000
                )
        self.assertEqual(first["body_text"] + last["body_text"], text)
        self.assertIsNone(last["next_offset"])
        self.assertTrue(last["body_complete"])
        self.assertTrue(last["flags_unchanged"])
        self.assertEqual(last["body_decoding"][0]["charset"], "gbk")
        self.assertFalse(last["persistent_mail_cache"])
        self.assertFalse(last["attachment_content_read"])
        self.assertFalse(last["automatic_todo"])

    def test_specific_content_errors_do_not_masquerade_as_auth_errors(self):
        cases = {
            "body_charset_decode_failed": "MAIL_BODY_CHARSET_DECODE_FAILED",
            "invalid_body_encoding": "MAIL_BODY_TRANSFER_DECODE_FAILED",
            "unsupported_body_encoding": "MAIL_BODY_TRANSFER_ENCODING_UNSUPPORTED",
            "body_incomplete": "MAIL_BODY_INCOMPLETE",
            "text_part_too_large": "MAIL_BODY_SIZE_LIMIT",
        }
        for backend_code, expected in cases.items():
            with self.subTest(code=backend_code):
                self.assertEqual(
                    str(source._error(RuntimeError(backend_code))), expected
                )

    def test_charset_diagnostics_do_not_forward_arbitrary_payload(self):
        error = RuntimeError("body_charset_decode_failed")
        error.decode_details = {
            "declared_charset": "utf-8",
            "section": "1",
            "failure_kind": "invalid_byte_sequence",
            "input_bytes": 99,
            "error_start": 3,
            "error_end": 4,
            "body": "private-body",
            "credential": "private-value",
            "other": "private-value",
        }
        mapped = source._error(error)
        self.assertEqual(mapped.decode_details["declared_charset"], "utf-8")
        self.assertNotIn("private", json.dumps(mapped.decode_details))
        error.decode_details["declared_charset"] = "private charset payload\n"
        self.assertNotIn("declared_charset", source._error(error).decode_details)

    def test_cli_returns_content_diagnostic_without_claiming_coverage(self):
        b = backend()
        error = RuntimeError("body_charset_decode_failed")
        error.decode_details = {
            "declared_charset": "gb2312",
            "section": "1",
            "failure_kind": "invalid_byte_sequence",
            "input_bytes": 9,
            "error_start": 8,
            "error_end": 9,
        }
        b.read_message.side_effect = error
        out = io.StringIO()
        with (
            patch.object(source, "_load_backend", return_value=b),
            contextlib.redirect_stdout(out),
        ):
            rc = cli.main(
                [
                    "body",
                    "--approved-read",
                    "--role",
                    "sent",
                    "--uid",
                    "42",
                    "--uidvalidity",
                    "7",
                ]
            )
        result = json.loads(out.getvalue())
        self.assertEqual(rc, 2)
        self.assertEqual(result["code"], "MAIL_BODY_CHARSET_DECODE_FAILED")
        self.assertFalse(result["coverage_advanced"])
        self.assertEqual(result["decode_details"]["declared_charset"], "gb2312")
        self.assertNotIn("body_text", result)


if __name__ == "__main__":
    unittest.main()
