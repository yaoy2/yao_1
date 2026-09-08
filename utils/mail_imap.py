"""Read-only IMAP collection into an isolated staging directory.

This module never persists credentials or changes mailbox flags. The caller owns
the authenticated connection and decides whether/where to ingest the batch.
"""

from __future__ import annotations

import base64
import hashlib
import imaplib
import json
import re
import ssl
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from utils.mail_mime import parse_message
from utils.mail_workspace import safe_filename


SHANGHAI = timezone(timedelta(hours=8))
MAX_MESSAGE_BYTES = 50 * 1024 * 1024
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_IMAP_ERRORS = (imaplib.IMAP4.error, OSError, EOFError, ValueError)


class ImapCollectionError(RuntimeError):
    """A fixed error code; never includes a server response or credentials."""


def connect(host, port, username, password, timeout=20):
    """Authenticate over certificate-verified TLS; keep secrets in memory only."""
    client = None
    try:
        client = imaplib.IMAP4_SSL(host, int(port), ssl_context=ssl.create_default_context(), timeout=timeout)
        client.debug = 0
        status, _ = client.login(username, password)
        if status != "OK":
            raise ImapCollectionError("IMAP_AUTHENTICATION_FAILED")
        return client
    except Exception as exc:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
        code = "IMAP_AUTHENTICATION_FAILED" if isinstance(exc, imaplib.IMAP4.error) else "IMAP_CONNECTION_FAILED"
        if isinstance(exc, ImapCollectionError):
            code = str(exc)
        raise ImapCollectionError(code) from None


def encode_modified_utf7(value: str) -> str:
    """Encode an IMAP mailbox name without relying on an optional codec."""
    result, pending = [], []

    def flush():
        if pending:
            encoded = base64.b64encode("".join(pending).encode("utf-16-be")).decode("ascii")
            result.append("&" + encoded.rstrip("=").replace("/", ",") + "-")
            pending.clear()

    for char in value:
        if " " <= char <= "~":
            flush()
            result.append("&-" if char == "&" else char)
        else:
            pending.append(char)
    flush()
    return "".join(result)


def decode_modified_utf7(value: str | bytes) -> str:
    if isinstance(value, bytes):
        value = value.decode("ascii")
    result, index = [], 0
    while index < len(value):
        char = value[index]
        if char != "&":
            if not " " <= char <= "~":
                raise ValueError("invalid mailbox encoding")
            result.append(char)
            index += 1
            continue
        end = value.find("-", index + 1)
        if end < 0:
            raise ValueError("invalid mailbox encoding")
        encoded = value[index + 1:end]
        if not encoded:
            result.append("&")
        else:
            encoded = encoded.replace(",", "/")
            decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
            result.append(decoded.decode("utf-16-be"))
        index = end + 1
    return "".join(result)


def _unquote(value: bytes) -> bytes:
    if value.startswith(b'"'):
        if not value.endswith(b'"'):
            raise ValueError("invalid IMAP quoted string")
        return re.sub(rb"\\(.)", rb"\1", value[1:-1])
    return value


def _quote(value: str) -> str:
    if any(char in value for char in ("\r", "\n", "\x00")):
        raise ValueError("invalid IMAP string")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_list_response(item) -> dict:
    """Parse the atom, quoted-string, and literal mailbox forms from LIST."""
    literal = None
    if isinstance(item, tuple) and len(item) == 2:
        item, literal = item
    if not isinstance(item, bytes):
        raise ValueError("invalid LIST response")
    match = re.fullmatch(rb'\(([^)]*)\)\s+(NIL|"(?:[^"\\]|\\.)*")\s+(.+)', item.strip(), re.I)
    if not match:
        raise ValueError("invalid LIST response")
    flags = match[1].decode("ascii").split()
    name = match[3]
    if literal is not None:
        size = re.fullmatch(rb"\{(\d+)\}", name)
        if not size or not isinstance(literal, bytes) or int(size[1]) != len(literal):
            raise ValueError("invalid LIST literal")
        name = literal
    else:
        if name.startswith(b"{"):
            raise ValueError("missing LIST literal")
        name = _unquote(name)
    wire = name.decode("ascii")
    return {"name": decode_modified_utf7(wire), "wire": wire,
            "selectable": "\\noselect" not in {flag.lower() for flag in flags},
            "delimiter": None if match[2].upper() == b"NIL" else _unquote(match[2]).decode("ascii"),
            "flags": flags}


def discover_folders(client) -> list[dict]:
    try:
        status, responses = client.list()
        if status != "OK" or not isinstance(responses, list):
            raise ValueError("LIST failed")
        folders = [parse_list_response(item) for item in responses if item not in (None, b"", b")")]
        if len({folder["wire"] for folder in folders}) != len(folders):
            raise ValueError("duplicate LIST entries")
        return folders
    except _IMAP_ERRORS:
        raise ImapCollectionError("IMAP_FOLDER_LIST_FAILED") from None


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include timezone")
    return parsed.astimezone(SHANGHAI)


def _iso_now() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def _search_date(value) -> str:
    return f"{value.day:02d}-{_MONTHS[value.month - 1]}-{value.year:04d}"


def _internaldate(raw: bytes) -> datetime:
    match = re.fullmatch(rb" ?(\d{1,2})-([A-Za-z]{3})-(\d{4}) (\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})", raw)
    if not match:
        raise ValueError("invalid INTERNALDATE")
    month = next((i for i, name in enumerate(_MONTHS, 1) if name.lower() == match[2].decode("ascii").lower()), None)
    offset = timedelta(hours=int(match[8]), minutes=int(match[9]))
    if int(match[9]) >= 60:
        raise ValueError("invalid INTERNALDATE timezone")
    if match[7] == b"-":
        offset = -offset
    return datetime(int(match[3]), month, int(match[1]), int(match[4]), int(match[5]), int(match[6]),
                    tzinfo=timezone(offset)).astimezone(SHANGHAI)


def _uid_search(client, *criteria) -> set[int]:
    status, responses = client.uid("SEARCH", None, *criteria)
    if status != "OK" or not isinstance(responses, list) or not responses:
        raise ImapCollectionError("IMAP_SEARCH_FAILED")
    found = set()
    for response in responses:
        if not isinstance(response, bytes) or not re.fullmatch(rb"\s*(?:[1-9]\d*(?:\s+[1-9]\d*)*)?\s*", response):
            raise ImapCollectionError("IMAP_SEARCH_INVALID")
        found.update(int(value) for value in response.split())
    return found


def _metadata(client, uid: int) -> tuple[datetime, int]:
    status, responses = client.uid("FETCH", str(uid), "(UID INTERNALDATE RFC822.SIZE)")
    if status != "OK" or not isinstance(responses, list):
        raise ImapCollectionError("IMAP_METADATA_FAILED")
    candidates = []
    for response in responses:
        header = response[0] if isinstance(response, tuple) else response
        if not isinstance(header, bytes):
            continue
        identifier = re.search(rb"\bUID\s+(\d+)\b", header, re.I)
        if identifier and int(identifier[1]) == uid:
            candidates.append(header)
    if len(candidates) != 1:
        raise ImapCollectionError("IMAP_METADATA_INCOMPLETE")
    header = candidates[0]
    date = re.search(rb'\bINTERNALDATE\s+"([^"]+)"', header, re.I)
    size = re.search(rb"\bRFC822.SIZE\s+(\d+)\b", header, re.I)
    if date is None or size is None:
        raise ImapCollectionError("IMAP_METADATA_INCOMPLETE")
    try:
        return _internaldate(date[1]), int(size[1])
    except (ValueError, TypeError):
        raise ImapCollectionError("IMAP_INTERNALDATE_INVALID") from None


def _body(client, uid: int, max_message_bytes: int) -> bytes:
    status, responses = client.uid("FETCH", str(uid), "(UID BODY.PEEK[])")
    if status != "OK" or not isinstance(responses, list):
        raise ImapCollectionError("IMAP_BODY_FAILED")
    candidates = []
    for index, response in enumerate(responses):
        if not isinstance(response, tuple) or len(response) != 2:
            continue
        header, raw = response
        if not isinstance(header, bytes) or not isinstance(raw, bytes):
            continue
        # FETCH attributes may be returned in any order. imaplib separates the
        # attributes following the literal into the next bytes response.
        attributes = header
        if index + 1 < len(responses) and isinstance(responses[index + 1], bytes):
            tail = responses[index + 1]
            if not re.match(rb"\s*\d+\s+\(", tail):
                attributes += b" " + tail
        identifier = re.search(rb"\bUID\s+(\d+)\b", attributes, re.I)
        literal = re.search(rb"\bBODY\[\]\s+\{(\d+)\}\s*$", header, re.I)
        if identifier and int(identifier[1]) == uid and literal:
            if len(raw) > max_message_bytes:
                raise ImapCollectionError("IMAP_MESSAGE_SIZE_LIMIT")
            # Exchange may report an estimated RFC822.SIZE before converting
            # its stored MAPI message to MIME. The literal length is exact.
            if int(literal[1]) != len(raw):
                raise ImapCollectionError("IMAP_BODY_INCOMPLETE")
            candidates.append(raw)
    if len(candidates) != 1:
        raise ImapCollectionError("IMAP_BODY_INCOMPLETE")
    return candidates[0]


def _folder_match(requested: str, discovered: list[dict]):
    exact = [folder for folder in discovered if folder["name"] == requested]
    if not exact and requested in ("收件箱", "INBOX", "inbox"):
        exact = [folder for folder in discovered if folder["wire"].upper() == "INBOX"]
    return exact[0] if len(exact) == 1 else None


def _write_message(parsed: dict, raw: bytes, staging: Path) -> dict:
    message = dict(parsed)
    directory = staging / ("message-" + hashlib.sha256(message["id"].encode("utf-8")).hexdigest())
    directory.mkdir()
    original = directory / "original.eml"
    original.write_bytes(raw)
    message["raw_eml_download_path"] = str(original)
    message["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    message["attachments"] = []
    for index, source in enumerate(parsed.get("attachments", []), 1):
        attachment = {key: value for key, value in source.items() if key != "data"}
        data = source.get("data")
        if not isinstance(data, bytes) or not data:
            message["attachments_complete"] = False
            attachment["status"] = "missing"
            attachment["error"] = source.get("error") or (
                "MIME_ATTACHMENT_EMPTY" if data == b"" else "MIME_ATTACHMENT_UNREADABLE")
            attachment.pop("download_path", None)
        else:
            target = directory / (f"{index:04d}-" + safe_filename(attachment.get("name")))
            target.write_bytes(data)
            attachment.update(download_path=str(target), size=len(data), sha256=hashlib.sha256(data).hexdigest())
        message["attachments"].append(attachment)
    message["summary"] = "待整理"
    return message


def collect(client, *, account: str, folders: list[str], since: str, through: str,
            staging_dir: Path, source_url: str, retry_message_ids: list[str] | None = None,
            max_message_bytes: int = MAX_MESSAGE_BYTES) -> dict:
    """Collect the inclusive timestamp window, plus explicitly requested retries.

    SEARCH uses enlarged UTC calendar boundaries because IMAP date searches
    ignore timezone. The final filter uses each UID's precise INTERNALDATE.
    Folder names except the documented INBOX alias are matched exactly.
    """
    start, end = _timestamp(since), _timestamp(through)
    if start > end:
        raise ValueError("collection window is reversed")
    if not folders or any(not isinstance(folder, str) or not folder for folder in folders):
        raise ValueError("explicit folders are required")
    if not isinstance(max_message_bytes, int) or max_message_bytes <= 0:
        raise ValueError("max_message_bytes must be positive")
    staging_dir = Path(staging_dir).expanduser()
    if not staging_dir.is_absolute():
        raise ValueError("staging_dir must be absolute")
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="imap-", dir=staging_dir)).resolve()
    retries = set(retry_message_ids or [])
    if any(not isinstance(identifier, str) or not identifier for identifier in retries):
        raise ValueError("retry_message_ids must be nonempty strings")
    batch = {"schema_version": 1, "id": "imap-" + uuid4().hex, "kind": "daily", "account": account,
             "started_at": _iso_now(), "finished_at": None,
             "window": {"since": start.isoformat(timespec="seconds"), "through": end.isoformat(timespec="seconds"), "complete": False},
             "messages": [], "actions": [], "errors": []}
    evidence = {"transport": "imap", "readonly": True, "staging_dir": str(staging),
                "max_message_bytes": max_message_bytes, "size_mismatches": 0, "folders": [],
                "skipped_authentication_notifications": {"count": 0, "received_at": []},
                "retry": {"requested_count": len(retries), "resolved_count": 0, "unresolved_count": len(retries)}}
    batch["collection"] = evidence

    def error(code, record=None):
        if code not in batch["errors"]:
            batch["errors"].append(code)
        if record is not None:
            record["complete"] = False
            if code not in record["error_codes"]:
                record["error_codes"].append(code)

    try:
        discovered = discover_folders(client)
    except ImapCollectionError as exc:
        error(str(exc))
        discovered = []
    search_start = _search_date(start.astimezone(timezone.utc).date() - timedelta(days=1))
    search_end = _search_date(end.astimezone(timezone.utc).date() + timedelta(days=2))
    found_retries, saved, visited = set(), {}, set()
    searchable_retries = set()
    for identifier in retries:
        if identifier.startswith("sha256:") or any(char in identifier for char in ("\r", "\n", "\x00")) or not identifier.isascii():
            error("IMAP_RETRY_ID_UNSEARCHABLE")
        else:
            searchable_retries.add(identifier)
    for requested in folders:
        record = {"requested": requested, "name": None, "searched_uids": 0, "fetched_messages": 0,
                  "outside_window": 0, "size_mismatches": 0, "complete": True, "error_codes": []}
        evidence["folders"].append(record)
        folder = _folder_match(requested, discovered)
        if folder is None:
            error("IMAP_FOLDER_NOT_FOUND", record)
            continue
        record["name"] = folder["name"]
        if not folder["selectable"]:
            error("IMAP_FOLDER_NOT_SELECTABLE", record)
            continue
        if folder["wire"] in visited:
            error("IMAP_FOLDER_DUPLICATED", record)
            continue
        visited.add(folder["wire"])
        try:
            status, _ = client.select(_quote(folder["wire"]), readonly=True)
            if status != "OK":
                raise ImapCollectionError("IMAP_FOLDER_SELECT_FAILED")
            uids = _uid_search(client, "SINCE", search_start, "BEFORE", search_end)
            retry_uids = set()
        except _IMAP_ERRORS as exc:
            error(str(exc) if isinstance(exc, ImapCollectionError) else "IMAP_FOLDER_READ_FAILED", record)
            continue
        except ImapCollectionError as exc:
            error(str(exc), record)
            continue
        for identifier in sorted(searchable_retries):
            try:
                retry_uids.update(_uid_search(client, "HEADER", "Message-ID", _quote(identifier)))
            except (_IMAP_ERRORS + (ImapCollectionError,)):
                error("IMAP_RETRY_SEARCH_FAILED", record)
        uids.update(retry_uids)
        record["searched_uids"] = len(uids)
        for uid in sorted(uids):
            try:
                received, size = _metadata(client, uid)
                inside_window = start <= received <= end
                if not inside_window and uid not in retry_uids:
                    record["outside_window"] += 1
                    continue
                if size > max_message_bytes:
                    raise ImapCollectionError("IMAP_MESSAGE_SIZE_LIMIT")
                raw = _body(client, uid, max_message_bytes)
                if len(raw) != size:
                    record["size_mismatches"] += 1
                    evidence["size_mismatches"] += 1
                record["fetched_messages"] += 1
                try:
                    parsed = parse_message(raw, received_at=received.isoformat(timespec="seconds"),
                                           folder=requested, source_url=source_url)
                except (ValueError, TypeError, KeyError):
                    raise ImapCollectionError("IMAP_MIME_PARSE_FAILED") from None
                identifier = parsed["id"]
                if not inside_window and identifier not in retries:
                    record["outside_window"] += 1
                    continue
                if parsed.get("authentication_notice"):
                    skipped = evidence["skipped_authentication_notifications"]
                    skipped["count"] += 1
                    skipped["received_at"].append(received.isoformat(timespec="seconds"))
                    if identifier in retries:
                        error("IMAP_RETRY_AUTHENTICATION_NOTICE", record)
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                if identifier in saved:
                    if saved[identifier] != digest:
                        error("IMAP_MESSAGE_ID_CONTENT_CONFLICT", record)
                    continue
                try:
                    message = _write_message(parsed, raw, staging)
                except OSError:
                    raise ImapCollectionError("IMAP_STAGING_WRITE_FAILED") from None
                if not inside_window and identifier in retries:
                    message["retry_of_existing"] = True
                batch["messages"].append(message)
                saved[identifier] = digest
                if message.get("attachments_complete") is False:
                    error("IMAP_ATTACHMENTS_INCOMPLETE", record)
                else:
                    if identifier in retries:
                        found_retries.add(identifier)
            except ImapCollectionError as exc:
                error(str(exc), record)
            except _IMAP_ERRORS:
                error("IMAP_MESSAGE_READ_FAILED", record)
            except (KeyError, TypeError, UnicodeError):
                error("IMAP_MIME_PARSE_FAILED", record)
    evidence["retry"].update(resolved_count=len(found_retries), unresolved_count=len(retries - found_retries))
    if retries - found_retries:
        error("IMAP_RETRY_NOT_COMPLETED")
    batch["finished_at"] = _iso_now()
    batch["window"]["complete"] = not batch["errors"] and all(folder["complete"] for folder in evidence["folders"])
    try:
        (staging / "evidence.json").write_text(json.dumps({"id": batch["id"], "window": batch["window"],
            "started_at": batch["started_at"], "finished_at": batch["finished_at"],
            "message_count": len(batch["messages"]), "errors": batch["errors"], "collection": evidence},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        error("IMAP_EVIDENCE_WRITE_FAILED")
        batch["window"]["complete"] = False
    return batch
