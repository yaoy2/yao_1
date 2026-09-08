"""Shared, credential-free contract for user-requested attachment filing.

The user's ``archived`` decision and the worker's filing result have separate
versions. Only the small allowlisted receipt is synchronized to the dashboard.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4


FILING_FIELDS = ("request_id", "requested_at", "updated_at", "status", "destination",
                 "saved_count", "total_count", "error_count", "error_codes")
FILING_STATUSES = frozenset({"pending", "success", "partial", "error", "cancelled"})
FILING_ERROR_CODES = frozenset({
    "SOURCE_MESSAGE_MISSING", "SOURCE_EML_MISSING", "SOURCE_EML_INVALID", "SOURCE_EML_HASH_MISMATCH",
    "SOURCE_MISSING", "SOURCE_CORRUPT", "SOURCE_NOT_FOUND", "SOURCE_AUTH_REQUIRED", "SOURCE_FETCH_FAILED",
    "SENSITIVE_SOURCE_SKIPPED", "SOURCE_ID_MISMATCH", "SOURCE_PATH_REJECTED", "SOURCE_ID_UNSEARCHABLE",
    "ATTACHMENT_INVENTORY_INCOMPLETE", "ATTACHMENT_MISSING", "ATTACHMENT_EMPTY", "ATTACHMENT_HASH_MISMATCH",
    "ATTACHMENT_READ_FAILED", "DESTINATION_UNAVAILABLE", "DESTINATION_UNSAFE", "DESTINATION_CONFLICT",
    "FILE_COPY_FAILED", "FILE_VERIFY_FAILED", "STATE_WRITE_FAILED", "MANIFEST_WRITE_FAILED", "FILING_INTERRUPTED",
})
_SHANGHAI = timezone(timedelta(hours=8))


def _moment(value):
    if not isinstance(value, str):
        raise ValueError("invalid filing timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
        return result.astimezone(_SHANGHAI)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("invalid filing timestamp") from None


def _after(at, previous=None):
    moment = _moment(at)
    if previous is not None and moment <= _moment(previous):
        moment = _moment(previous) + timedelta(microseconds=1)
    return moment.isoformat(timespec="microseconds" if moment.microsecond else "seconds")


def safe_relative_destination(value):
    """Allow pending, the configured root marker, or a legacy receipt path."""
    if not isinstance(value, str):
        raise ValueError("invalid filing destination")
    if value in {"", "."}:
        return value
    parts = value.split("/")
    if len(parts) < 2 or parts[0] != "邮件存档":
        raise ValueError("invalid filing destination")
    for part in parts:
        if (not part or part in {".", ".."} or part.endswith((" ", "."))
                or re.search(r'[<>:"\\|?*\x00-\x1f\x7f]', part)
                or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I)):
            raise ValueError("invalid filing destination")
    return value


def validate_filing(value):
    """Validate the complete public receipt; legacy mail may omit it entirely."""
    if not isinstance(value, dict) or set(value) != set(FILING_FIELDS):
        raise ValueError("invalid filing record")
    if not isinstance(value["request_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", value["request_id"]):
        raise ValueError("invalid filing request id")
    requested, updated = _moment(value["requested_at"]), _moment(value["updated_at"])
    if updated < requested:
        raise ValueError("filing update precedes its request")
    if not isinstance(value["status"], str) or value["status"] not in FILING_STATUSES:
        raise ValueError("invalid filing status")
    safe_relative_destination(value["destination"])
    for key in ("saved_count", "total_count", "error_count"):
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError("invalid filing count")
    if value["saved_count"] > value["total_count"]:
        raise ValueError("invalid filing count")
    errors = value["error_codes"]
    if (not isinstance(errors, list) or any(not isinstance(code, str) or code not in FILING_ERROR_CODES for code in errors)
            or len(errors) != len(set(errors))):
        raise ValueError("invalid filing error code")
    if value["status"] == "success" and (value["saved_count"] != value["total_count"]
                                         or value["error_count"] or errors
                                         or (value["total_count"] > 0 and not value["destination"])):
        raise ValueError("invalid successful filing receipt")
    return value


def public_filing(value):
    """Drop local details and reject unsafe values in the remaining fields."""
    if not isinstance(value, dict):
        raise ValueError("invalid filing record")
    result = {key: copy.deepcopy(value[key]) for key in FILING_FIELDS if key in value}
    return validate_filing(result)


def is_filing_requested(snapshot, message_id):
    message = next((item for item in snapshot.get("messages", []) if item.get("id") == message_id), None)
    if message is None:
        return False
    linked = [action for action in snapshot.get("actions", []) if action.get("message_id") == message_id]
    return (any(action.get("status") == "archived" for action in linked) if linked
            else message.get("triage_status") == "archived")


def _selected_messages(snapshot, message_ids):
    if isinstance(message_ids, (str, bytes)):
        raise ValueError("filing message ids must be a collection")
    ids = list(message_ids)
    if any(not isinstance(identifier, str) or not identifier.strip() for identifier in ids):
        raise ValueError("invalid filing message id")
    by_id = {message["id"]: message for message in snapshot.get("messages", [])}
    return [by_id[identifier] for identifier in dict.fromkeys(ids) if identifier in by_id]


def queue_filing(snapshot, message_ids, at):
    """Queue one new request per eligible mail, changing no user decision."""
    _moment(at)
    selected = _selected_messages(snapshot, message_ids)
    queued = []
    for message in selected:
        identifier = message["id"]
        if not is_filing_requested(snapshot, identifier):
            continue
        previous = message.get("filing")
        if previous is not None:
            validate_filing(previous)
        # CAS serializes new requests. A monotonic timestamp also distinguishes
        # two requests created within the same second from an older worker result.
        requested = _after(at, previous["requested_at"] if previous else None)
        message["filing"] = {"request_id": uuid4().hex, "requested_at": requested, "updated_at": requested,
                             "status": "pending", "destination": "", "saved_count": 0, "total_count": 0,
                             "error_count": 0, "error_codes": []}
        queued.append(identifier)
    return queued


def cancel_unrequested(snapshot, message_ids, at):
    """Cancel unfinished requests whose user decision no longer asks for filing."""
    _moment(at)
    cancelled = []
    for message in _selected_messages(snapshot, message_ids):
        filing = message.get("filing")
        if filing is None or is_filing_requested(snapshot, message["id"]):
            continue
        validate_filing(filing)
        if filing["status"] not in {"pending", "partial", "error"}:
            continue
        filing.update(status="cancelled", updated_at=_after(at, filing["updated_at"]))
        cancelled.append(message["id"])
    return cancelled


def merge_filing(local, remote):
    """Merge request versions independently of collection and user statuses.

    A cancelled request is a tombstone: only a fresh request can supersede it.
    Otherwise request time precedes result time, and an exact tie favors remote.
    """
    if local is None:
        return None if remote is None else public_filing(remote)
    if remote is None:
        return public_filing(local)
    local, remote = public_filing(local), public_filing(remote)
    if local["request_id"] == remote["request_id"]:
        cancelled = [value for value in (local, remote) if value["status"] == "cancelled"]
        if len(cancelled) == 1:
            return cancelled[0]
    local_key = (_moment(local["requested_at"]), _moment(local["updated_at"]))
    remote_key = (_moment(remote["requested_at"]), _moment(remote["updated_at"]))
    return remote if remote_key >= local_key else local
