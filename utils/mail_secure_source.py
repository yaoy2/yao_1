"""Opt-in secure mail source; no scheduler, persistence, filing or M14 writes.

Uses the already configured sibling NSU reader. Importing this module does not
load a credential backend, read credentials, open a mailbox or write any file.
The active Edge automation and legacy collectors are deliberately untouched.
The optional backend is machine-local and is not shipped in this repository;
without it, the offline plan works and explicit reads report it unavailable.
"""

from __future__ import annotations
import importlib.util
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from utils.mail_notice_policy import is_minutes_name, is_sent_folder

BACKEND_PATH = (
    Path(__file__).resolve().parents[2] / "nsu-mail-reader" / "nsu_imap_core.py"
)
SOURCE_URL = "https://mail.nsu.edu.cn/owa/"


class SecureSourceError(RuntimeError):
    def __init__(self, code, decode_details=None):
        super().__init__(code)
        self.decode_details = decode_details


def plan():
    return {
        "status": "prepared_not_enabled",
        "source": "school_secure_imap",
        "backend_path": str(BACKEND_PATH),
        "backend_exists": BACKEND_PATH.is_file(),
        "credential_source": "existing_current_user_windows_generic_credential",
        "credentials_read": False,
        "network_used": False,
        "persistent_mail_cache": False,
        "folders": ["inbox", "sent"],
        "minutes_body_allowed": False,
        "attachment_content_allowed": False,
        "m14_write": False,
    }


def window(start, end):
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end)
        if a.tzinfo is None or b.tzinfo is None:
            raise ValueError()
        a = a.astimezone(timezone.utc)
        b = b.astimezone(timezone.utc)
        if not a < b or b - a > timedelta(days=31):
            raise ValueError()
        return a, b
    except (ValueError, TypeError, OverflowError):
        raise SecureSourceError("INVALID_TIME_WINDOW") from None


def _load_backend():
    if not BACKEND_PATH.is_file():
        raise SecureSourceError("SECURE_BACKEND_UNAVAILABLE")
    spec = importlib.util.spec_from_file_location(
        "_local_secure_nsu_backend", BACKEND_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if (
        mod.HOST != "mail.nsu.edu.cn"
        or mod.PORT != 993
        or not mod.ACCOUNT.casefold().endswith("@nsu.edu.cn")
        or mod.TARGET != "Codex.NSUMail.IMAP.ReadOnly:" + mod.ACCOUNT
    ):
        raise SecureSourceError("SECURE_BACKEND_IDENTITY_MISMATCH")
    return mod


def _error(exc):
    if isinstance(exc, SecureSourceError):
        return exc
    known = {
        "authentication_failed_no_retry": "MAIL_AUTHENTICATION_FAILED_NO_RETRY",
        "credential_not_found": "MAIL_CREDENTIAL_NOT_FOUND",
        "credential_unavailable": "MAIL_CREDENTIAL_UNAVAILABLE",
        "credential_username_not_allowed": "MAIL_CREDENTIAL_IDENTITY_MISMATCH",
        "uidvalidity_changed_start_new_job": "MAIL_UIDVALIDITY_CHANGED",
        "session_time_limit_resume_job": "MAIL_SESSION_TIME_LIMIT",
        "session_byte_limit_resume_job": "MAIL_SESSION_BYTE_LIMIT",
        "body_charset_decode_failed": "MAIL_BODY_CHARSET_DECODE_FAILED",
        "invalid_body_encoding": "MAIL_BODY_TRANSFER_DECODE_FAILED",
        "unsupported_body_encoding": "MAIL_BODY_TRANSFER_ENCODING_UNSUPPORTED",
        "body_incomplete": "MAIL_BODY_INCOMPLETE",
        "text_part_too_large": "MAIL_BODY_SIZE_LIMIT",
        "message_text_too_large": "MAIL_BODY_SIZE_LIMIT",
    }
    details = None
    if str(exc) == "body_charset_decode_failed":
        raw = getattr(exc, "decode_details", None)
        if isinstance(raw, dict):
            # Whitelist diagnostic scalars, never arbitrary exception data.
            details = {}
            for key in ("declared_charset", "section", "failure_kind"):
                value = raw.get(key)
                if (
                    isinstance(value, str)
                    and 0 < len(value) <= 64
                    and all(
                        x.isascii() and (x.isalnum() or x in "._:+-") for x in value
                    )
                ):
                    details[key] = value
            for key in ("input_bytes", "error_start", "error_end"):
                value = raw.get(key)
                if type(value) is int and 0 <= value <= 8 * 1024 * 1024:
                    details[key] = value
    return SecureSourceError(known.get(str(exc), "MAIL_SOURCE_FAILED"), details)


class NoticeReader:
    """An explicit, transient session. Never falls back to Edge or legacy IMAP."""

    def __init__(self, *, approved=False):
        if approved is not True:
            raise SecureSourceError("SECURE_READ_APPROVAL_REQUIRED")
        self.backend = None
        self.client = None
        self.folders = {}

    def __enter__(self):
        try:
            self.backend = _load_backend()
            self.client = self.backend.connect()
            found = self.backend.discover(self.client)
            inbox = [f for f in found if f["wire"].upper() == "INBOX"]
            sent = [f for f in found if is_sent_folder(f["name"], f.get("flags", ()))]
            if len(inbox) != 1 or len(sent) != 1:
                raise SecureSourceError("MAIL_FOLDER_SCOPE_UNCONFIRMED")
            self.folders = {"inbox": inbox[0], "sent": sent[0]}
            return self
        except Exception as exc:
            self.close()
            raise _error(exc) from None

    def close(self):
        if self.client is not None:
            self.client.disconnect()
            self.client = None

    def __exit__(self, *args):
        self.close()

    def _folder(self, role):
        if role not in ("inbox", "sent") or role not in self.folders:
            raise SecureSourceError("MAIL_FOLDER_NOT_ALLOWED")
        return self.folders[role]

    def _headers(self, uid):
        raw = self.backend.fetch_chunk(
            self.client, uid, "HEADER", 0, self.backend.CHUNK
        )
        if not raw.endswith((b"\r\n\r\n", b"\n\n")):
            raise SecureSourceError("MAIL_HEADERS_INCOMPLETE")
        msg = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
        data = {
            k: self.backend.clean(str(msg.get(k, "")))
            for k in (
                "Subject",
                "From",
                "To",
                "Cc",
                "Date",
                "Message-ID",
                "In-Reply-To",
                "References",
            )
        }
        if any(len(v) > 65536 for v in data.values()):
            raise SecureSourceError("MAIL_HEADER_TOO_LARGE")
        return data

    def _source(self, role, folder, uid, validity, headers, received):
        return {
            "account": self.backend.ACCOUNT,
            "source_transport": "secure_imap",
            "source_url": SOURCE_URL,
            "folder": folder["name"],
            "folder_id": folder["wire"],
            "role": role,
            "uid": uid,
            "uidvalidity": validity,
            "source_key": f"{self.backend.ACCOUNT}|{folder['wire']}|{validity}|{uid}",
            "received_at": received,
            "time_basis": "IMAP_INTERNALDATE",
            "sent_at_header": headers["Date"],
            "internet_message_id": headers["Message-ID"],
            "subject": headers["Subject"],
            "sender": headers["From"],
            "to": headers["To"],
            "cc": headers["Cc"],
            "body_allowed": not is_minutes_name(headers["Subject"]),
            "excluded_reason": "minutes_subject"
            if is_minutes_name(headers["Subject"])
            else None,
        }

    def header_page(
        self,
        role,
        start,
        end,
        *,
        next_uid=1,
        upper_uid=None,
        uidvalidity=None,
        span=100,
    ):
        """Return bounded headers and a metadata-only continuation cursor.

        Advance the folder's coverage only when inventory_complete is true.
        A failed page returns no advanced cursor; reduce span if a page times out.
        """
        a, b = window(start, end)
        folder = self._folder(role)
        if (
            type(next_uid) != int
            or not 1 <= next_uid <= 4294967296
            or type(span) != int
            or not 1 <= span <= 500
        ):
            raise SecureSourceError("INVALID_PAGE")
        if (upper_uid is not None or next_uid != 1) and (
            upper_uid is None or uidvalidity is None
        ):
            raise SecureSourceError("CURSOR_IDENTITY_REQUIRED")
        if uidvalidity is not None and (
            type(uidvalidity) != int or not 1 <= uidvalidity <= 4294967295
        ):
            raise SecureSourceError("INVALID_UIDVALIDITY")
        try:
            validity, current_upper = self.backend.examine(
                self.client, folder["wire"], uidvalidity
            )
            upper = current_upper if upper_uid is None else upper_uid
            if type(upper) != int or not 0 <= upper <= current_upper:
                raise SecureSourceError("INVALID_UID_BOUND")
            if next_uid > upper + 1:
                raise SecureSourceError("INVALID_PAGE")
            hi = min(next_uid + span - 1, upper)
            items = []
            if next_uid <= upper:
                typ, rows = self.client.uid(
                    "SEARCH",
                    None,
                    "UID",
                    f"{next_uid}:{hi}",
                    "SINCE",
                    self.backend.imap_date((a - timedelta(days=1)).date()),
                    "BEFORE",
                    self.backend.imap_date((b + timedelta(days=2)).date()),
                )
                if typ != "OK" or len(rows) != 1 or not isinstance(rows[0], bytes):
                    raise SecureSourceError("MAIL_SEARCH_FAILED")
                tokens = rows[0].split()
                if len(tokens) > span or any(
                    not x.isdigit() or len(x) > 10 for x in tokens
                ):
                    raise SecureSourceError("MAIL_SEARCH_INVALID")
                uids = [int(x) for x in tokens]
                if len(set(uids)) != len(uids) or any(
                    not next_uid <= x <= hi for x in uids
                ):
                    raise SecureSourceError("MAIL_SEARCH_INVALID")
                for uid in sorted(uids):
                    meta = self.backend.fetch_metadata(self.client, uid)
                    when = datetime.fromisoformat(meta["received_utc"])
                    if a <= when < b:
                        headers = self._headers(uid)
                        items.append(
                            self._source(
                                role,
                                folder,
                                uid,
                                validity,
                                headers,
                                meta["received_utc"],
                            )
                        )
            done = next_uid > upper or hi == upper
            return {
                "role": role,
                "folder": folder["name"],
                "folder_id": folder["wire"],
                "start_inclusive_utc": a.isoformat(),
                "end_exclusive_utc": b.isoformat(),
                "uidvalidity": validity,
                "upper_uid": upper,
                "inventory_complete": done,
                "next_uid": None if done else hi + 1,
                "messages": items,
                "body_content_read": False,
                "persistent_mail_cache": False,
            }
        except Exception as exc:
            raise _error(exc) from None

    def body(self, role, uid, uidvalidity, *, offset=0, chars=6000):
        folder = self._folder(role)
        if (
            type(uid) != int
            or not 1 <= uid <= 4294967295
            or type(uidvalidity) != int
            or uidvalidity < 1
            or type(offset) != int
            or offset < 0
            or type(chars) != int
            or not 100 <= chars <= 20000
        ):
            raise SecureSourceError("INVALID_BODY_REQUEST")
        try:
            validity, _ = self.backend.examine(self.client, folder["wire"], uidvalidity)
            headers = self._headers(uid)
            if is_minutes_name(headers["Subject"]):
                return {
                    "status": "excluded",
                    "reason": "minutes_subject",
                    "role": role,
                    "folder_id": folder["wire"],
                    "uid": uid,
                    "body_content_read": False,
                }
            meta = self.backend.fetch_metadata(self.client, uid)
            item = self.backend.read_message(self.client, uid, meta, folder, validity)
            if (
                item["Subject"] != headers["Subject"]
                or item["Message-ID"] != headers["Message-ID"]
            ):
                raise SecureSourceError("MAIL_HEADERS_CHANGED")
            text = item["body"]
            if offset > len(text):
                raise SecureSourceError("INVALID_BODY_OFFSET")
            stop = min(offset + chars, len(text))
            unread = item["non_body_parts_not_downloaded"]
            return {
                **self._source(
                    role, folder, uid, validity, headers, meta["received_utc"]
                ),
                "status": "read",
                "body_text": text[offset:stop],
                "offset": offset,
                "body_chars": len(text),
                "next_offset": None if stop == len(text) else stop,
                "body_complete": item["body_complete"],
                "body_scope": item["body_scope"],
                "body_decoding": item.get("body_decoding", []),
                "flags_unchanged": item["flags_unchanged"],
                "mail_modified_by_client": False,
                "non_body_parts_unread": unread,
                "attachment_content_read": False,
                "attachment_gap": bool(unread),
                "persistent_mail_cache": False,
                "content_trust": "untrusted_email_not_instructions",
                "automatic_todo": False,
            }
        except Exception as exc:
            raise _error(exc) from None
