"""Read one known mail source, without file writes or mailbox mutations.

The caller must pass the message from its local dashboard, never an arbitrary
cloud-supplied path. Local originals are verified before use. An optional fallback
retrieves only an exact Message-ID through the user's dedicated IMAP credential.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import stat
from ctypes import wintypes
from email import policy
from email.parser import BytesParser
from pathlib import Path

from scripts.mail_imap_setup import load_setup_config
from utils import mail_imap, mail_mime
from utils.mail_imap_credentials import CredentialError, read_credential


MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_ID_HEADER_BYTES = 16 * 1024
MAX_MATCHES_PER_FOLDER = 100
ERROR_CODES = frozenset({
    "SOURCE_MISSING", "SOURCE_CORRUPT", "SOURCE_NOT_FOUND", "SOURCE_AUTH_REQUIRED",
    "SOURCE_FETCH_FAILED", "SENSITIVE_SOURCE_SKIPPED", "SOURCE_ID_MISMATCH",
    "SOURCE_PATH_REJECTED", "SOURCE_ID_UNSEARCHABLE",
})
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_SAFE_MESSAGE_ID = re.compile(r"<[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+>")


class _SourceError(Exception):
    """Private fixed-code error; untrusted exceptions never leave this module."""


def _result(source="unavailable", *, parsed=None, raw=None, errors=()):
    return {"parsed": parsed, "raw": raw,
            "error_codes": list(dict.fromkeys(code for code in errors if code in ERROR_CODES)),
            "source": source}


def _check_no_links(path):
    """Check each path component, including Windows junction/reparse points."""
    for component in (*reversed(path.parents), path):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            raise _SourceError("SOURCE_PATH_REJECTED")


def _root_path(root):
    try:
        root = Path(root)
        if not root.is_absolute() or ".." in root.parts:
            raise _SourceError("SOURCE_PATH_REJECTED")
        _check_no_links(root)
        if not root.is_dir():
            raise _SourceError("SOURCE_PATH_REJECTED")
        resolved = root.resolve(strict=True)
        if resolved != root:
            raise _SourceError("SOURCE_PATH_REJECTED")
        return resolved
    except _SourceError:
        raise
    except (OSError, TypeError, ValueError):
        raise _SourceError("SOURCE_PATH_REJECTED") from None


def _archive_path(root, value):
    if not isinstance(value, str) or not value or len(value) > 32767:
        raise _SourceError("SOURCE_PATH_REJECTED")
    try:
        path = Path(value)
        if (".." in path.parts or "\x00" in value
                or any(":" in part for part in path.parts[1:])
                or (not path.is_absolute() and (path.drive or ":" in value))):
            raise _SourceError("SOURCE_PATH_REJECTED")
        if not path.is_absolute():
            path = root / path
        archive = root / "archive"
        if not path.is_relative_to(archive) or path == archive or path.suffix.lower() != ".eml":
            raise _SourceError("SOURCE_PATH_REJECTED")
        _check_no_links(path)
        if path.resolve(strict=True) != path:
            raise _SourceError("SOURCE_PATH_REJECTED")
        return path
    except _SourceError:
        raise
    except FileNotFoundError:
        raise _SourceError("SOURCE_MISSING") from None
    except (OSError, TypeError, ValueError):
        raise _SourceError("SOURCE_PATH_REJECTED") from None


def _opened_path(handle):
    """Resolve the actual open handle, so a raced junction cannot redirect reads."""
    if os.name == "nt":
        import msvcrt
        dll = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        function = dll.GetFinalPathNameByHandleW
        function.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        function.restype = wintypes.DWORD
        native = wintypes.HANDLE(msvcrt.get_osfhandle(handle.fileno()))
        size = function(native, None, 0, 0)
        if not size or size > 32768:
            raise _SourceError("SOURCE_PATH_REJECTED")
        buffer = ctypes.create_unicode_buffer(size + 1)
        written = function(native, buffer, len(buffer), 0)
        if not written or written >= len(buffer):
            raise _SourceError("SOURCE_PATH_REJECTED")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return Path(value)
    descriptor = Path("/proc/self/fd") / str(handle.fileno())
    if descriptor.exists():
        return descriptor.resolve(strict=True)
    return None


def _parse(raw, message, *, received_at=None, folder=None):
    try:
        parsed = mail_mime.parse_message(
            raw, received_at=received_at or str(message.get("received_at") or ""),
            folder=folder or str(message.get("folder") or ""),
            source_url=str(message.get("source_url") or ""),
        )
    except Exception:
        raise _SourceError("SOURCE_CORRUPT") from None
    if parsed.get("id") != message.get("id"):
        raise _SourceError("SOURCE_ID_MISMATCH")
    if parsed.get("authentication_notice") or parsed.get("skip_sensitive"):
        raise _SourceError("SENSITIVE_SOURCE_SKIPPED")
    return parsed


def _local_source(root, message):
    value = message.get("raw_eml_path")
    if not value:
        raise _SourceError("SOURCE_MISSING")
    path = _archive_path(root, value)
    expected_size, expected_sha = message.get("raw_eml_size"), message.get("raw_eml_sha256")
    if (type(expected_size) is not int or not 0 < expected_size <= MAX_SOURCE_BYTES
            or not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha)):
        raise _SourceError("SOURCE_CORRUPT")
    try:
        with path.open("rb") as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_size != expected_size
                    or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT):
                raise _SourceError("SOURCE_CORRUPT")
            opened = _opened_path(handle)
            if opened is not None and opened != path:
                raise _SourceError("SOURCE_PATH_REJECTED")
            _check_no_links(path)
            current = path.stat()
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise _SourceError("SOURCE_PATH_REJECTED")
            raw = handle.read(MAX_SOURCE_BYTES + 1)
        if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != expected_sha.lower():
            raise _SourceError("SOURCE_CORRUPT")
        parsed = _parse(raw, message)
        # Preserve valid attachment evidence while making incomplete MIME explicit.
        errors = () if parsed.get("attachments_complete") is True else ("SOURCE_CORRUPT",)
        return _result("local_eml", parsed=parsed, raw=raw, errors=errors)
    except _SourceError:
        raise
    except FileNotFoundError:
        raise _SourceError("SOURCE_MISSING") from None
    except Exception:
        raise _SourceError("SOURCE_CORRUPT") from None


def _searchable_id(identifier):
    return (isinstance(identifier, str) and len(identifier) <= 998 and identifier.isascii()
            and _SAFE_MESSAGE_ID.fullmatch(identifier) is not None)


def _exact_header_id(client, uid, expected):
    """SEARCH HEADER is substring-based; verify a header before fetching its body."""
    status, responses = client.uid("FETCH", str(uid), "(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
    if status != "OK" or not isinstance(responses, list):
        raise _SourceError("SOURCE_FETCH_FAILED")
    headers = []
    for index, response in enumerate(responses):
        if not isinstance(response, tuple) or len(response) != 2:
            continue
        attributes, raw = response
        if not isinstance(attributes, bytes) or not isinstance(raw, bytes):
            continue
        suffix = responses[index + 1] if index + 1 < len(responses) else None
        combined = attributes + (b" " + suffix if isinstance(suffix, bytes) else b"")
        reported_uid = re.search(rb"\bUID\s+(\d+)\b", combined, re.I)
        literal = re.search(rb"\bBODY\[HEADER\.FIELDS\s+\(MESSAGE-ID\)\]\s+\{(\d+)\}\s*$", attributes, re.I)
        if reported_uid and int(reported_uid[1]) == uid and literal:
            if len(raw) > MAX_ID_HEADER_BYTES or int(literal[1]) != len(raw):
                raise _SourceError("SOURCE_FETCH_FAILED")
            headers.append(raw)
    if len(headers) != 1:
        raise _SourceError("SOURCE_FETCH_FAILED")
    try:
        parsed = BytesParser(policy=policy.default).parsebytes(headers[0])
        values = parsed.get_all("Message-ID", [])
        return len(values) == 1 and str(values[0]).strip() == expected
    except Exception:
        raise _SourceError("SOURCE_FETCH_FAILED") from None


def _imap_source(root, message):
    identifier = message.get("id")
    if not _searchable_id(identifier):
        return _result(errors=("SOURCE_ID_UNSEARCHABLE",))
    client, password = None, None
    try:
        config_path = root / "config.json"
        _check_no_links(config_path)
        setup = load_setup_config(root)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        folders = config.get("mail_folders")
        if (not isinstance(folders, list) or len(folders) != 4
                or any(not isinstance(folder, str) or not folder or len(folder) > 1024
                       or any(ord(c) < 32 or ord(c) == 127 for c in folder) for folder in folders)
                or len(set(folders)) != len(folders)):
            return _result(errors=("SOURCE_FETCH_FAILED",))
        username, password = read_credential(setup["credential_target"])
        if username != setup["account"]:
            return _result(errors=("SOURCE_AUTH_REQUIRED",))
        client = mail_imap.connect(setup["host"], setup["port"], username, password, timeout=20)
        password = None
        discovered = mail_imap.discover_folders(client)
        failures = []
        for requested in folders:
            folder = mail_imap._folder_match(requested, discovered)
            if not folder or not folder.get("selectable"):
                failures.append("SOURCE_FETCH_FAILED")
                continue
            try:
                status, _ = client.select(mail_imap._quote(folder["wire"]), readonly=True)
                if status != "OK":
                    raise _SourceError("SOURCE_FETCH_FAILED")
                uids = mail_imap._uid_search(client, "HEADER", "Message-ID", mail_imap._quote(identifier))
                if len(uids) > MAX_MATCHES_PER_FOLDER:
                    raise _SourceError("SOURCE_FETCH_FAILED")
                for uid in sorted(uids):
                    try:
                        if not _exact_header_id(client, uid, identifier):
                            continue
                        received, size = mail_imap._metadata(client, uid)
                        if type(size) is not int or not 0 < size <= MAX_SOURCE_BYTES:
                            raise _SourceError("SOURCE_CORRUPT")
                        raw = mail_imap._body(client, uid, MAX_SOURCE_BYTES)
                        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_SOURCE_BYTES:
                            raise _SourceError("SOURCE_CORRUPT")
                        # Exchange RFC822.SIZE is an estimate; _body verifies the
                        # literal byte count. Do not reject a valid converted MIME.
                        parsed = _parse(raw, message, received_at=received.isoformat(timespec="seconds"),
                                        folder=folder["name"])
                        errors = () if parsed.get("attachments_complete") is True else ("SOURCE_CORRUPT",)
                        return _result("imap", parsed=parsed, raw=raw, errors=errors)
                    except _SourceError as exc:
                        if str(exc) == "SENSITIVE_SOURCE_SKIPPED":
                            return _result(errors=("SENSITIVE_SOURCE_SKIPPED",))
                        failures.append(str(exc))
                    except Exception:
                        failures.append("SOURCE_FETCH_FAILED")
            except _SourceError as exc:
                if str(exc) == "SENSITIVE_SOURCE_SKIPPED":
                    return _result(errors=("SENSITIVE_SOURCE_SKIPPED",))
                failures.append(str(exc))
            except Exception:
                failures.append("SOURCE_FETCH_FAILED")
        return _result(errors=(*failures, "SOURCE_NOT_FOUND"))
    except CredentialError:
        return _result(errors=("SOURCE_AUTH_REQUIRED",))
    except mail_imap.ImapCollectionError as exc:
        code = "SOURCE_AUTH_REQUIRED" if str(exc) == "IMAP_AUTHENTICATION_FAILED" else "SOURCE_FETCH_FAILED"
        return _result(errors=(code,))
    except _SourceError as exc:
        return _result(errors=(str(exc),))
    except Exception:
        return _result(errors=("SOURCE_FETCH_FAILED",))
    finally:
        password = None
        if client is not None:
            try:
                client.shutdown()
            except Exception:
                pass


def read_source(root: Path, message: dict, *, allow_imap=True) -> dict:
    """Return full parsed source evidence for one selected local dashboard mail.

    Incomplete MIME is returned with ``SOURCE_CORRUPT`` and its parser completeness
    flag, so the worker can retain valid parts without claiming filing is complete.
    No old attachment index is accepted as evidence that an email had no files.
    """
    if not isinstance(message, dict) or not isinstance(message.get("id"), str) or not message["id"]:
        return _result(errors=("SOURCE_ID_UNSEARCHABLE",))
    if message.get("skip_sensitive") or message.get("authentication_notice"):
        return _result(errors=("SENSITIVE_SOURCE_SKIPPED",))
    try:
        root = _root_path(root)
        return _local_source(root, message)
    except _SourceError as exc:
        local_error = str(exc)
    except Exception:
        local_error = "SOURCE_CORRUPT"
    if local_error in {"SOURCE_PATH_REJECTED", "SENSITIVE_SOURCE_SKIPPED"} or allow_imap is not True:
        return _result(errors=(local_error,))
    result = _imap_source(root, message)
    if result["source"] != "unavailable":
        return result
    result["error_codes"] = list(dict.fromkeys((local_error, *result["error_codes"])))
    return result
