"""Fixed public contract for explicitly requested mail collection.

The remote dashboard owns this control record. Ordinary snapshot merges must
never promote an unsynchronized local request or result into an executable job.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4


COLLECTION_REQUIRED_FIELDS = frozenset({"request_id", "requested_at", "status", "phase", "updated_at"})
COLLECTION_FIELDS = ("request_id", "requested_at", "status", "phase", "updated_at", "claim_id",
                     "started_at", "finished_at", "message_count", "new_message_count", "action_count", "error_code")
COLLECTION_STATUSES = frozenset({"pending", "running", "success", "partial", "error"})
COLLECTION_PHASES = ("queued", "collecting", "reviewing", "syncing", "complete")
COLLECTION_ERROR_CODES = frozenset({
    "COLLECTION_CONFIG_INVALID", "COLLECTION_AUTH_REQUIRED", "COLLECTION_CONNECT_FAILED",
    "COLLECTION_READ_FAILED", "COLLECTION_WINDOW_INCOMPLETE", "REVIEW_UNAVAILABLE", "REVIEW_TIMEOUT",
    "REVIEW_FAILED", "REVIEW_OUTPUT_INVALID", "INGEST_FAILED", "SYNC_FAILED", "LOCAL_STATE_FAILED",
    "WORKER_INTERRUPTED",
})
_COUNTS = ("message_count", "new_message_count", "action_count")
_TERMINAL = frozenset({"success", "partial", "error"})
_SHANGHAI = timezone(timedelta(hours=8))


class CollectionStateError(ValueError):
    """Only a fixed diagnostic code escapes validation and transition helpers."""

    def __init__(self, code="invalid_collection"):
        self.code = code
        super().__init__(code)


def _moment(value):
    try:
        if not isinstance(value, str):
            raise ValueError
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
        return result.astimezone(_SHANGHAI)
    except (ValueError, TypeError, OverflowError):
        raise CollectionStateError() from None


def _after(at, previous=None):
    moment = _moment(at)
    if previous is not None and moment <= _moment(previous):
        moment = _moment(previous) + timedelta(microseconds=1)
    return moment.isoformat(timespec="microseconds" if moment.microsecond else "seconds")


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise CollectionStateError()
    return value


def validate_collection(value):
    """Reject executable input and inconsistent states, allowing legacy omission."""
    if (not isinstance(value, dict) or not COLLECTION_REQUIRED_FIELDS <= set(value)
            or not set(value) <= set(COLLECTION_FIELDS)):
        raise CollectionStateError()
    _identifier(value["request_id"])
    requested, updated = _moment(value["requested_at"]), _moment(value["updated_at"])
    status, phase = value["status"], value["phase"]
    if (not isinstance(status, str) or status not in COLLECTION_STATUSES
            or not isinstance(phase, str) or phase not in COLLECTION_PHASES or updated < requested):
        raise CollectionStateError()
    claim = value.get("claim_id", "")
    if claim != "":
        _identifier(claim)
    started = _moment(value["started_at"]) if value.get("started_at") else None
    finished = _moment(value["finished_at"]) if value.get("finished_at") else None
    for key in ("started_at", "finished_at"):
        if key in value and not isinstance(value[key], str):
            raise CollectionStateError()
    if (started and not requested <= started <= updated) or (finished and (not started or not started <= finished <= updated)):
        raise CollectionStateError()
    for key in _COUNTS:
        if key in value and (type(value[key]) is not int or value[key] < 0):
            raise CollectionStateError()
    if value.get("new_message_count", 0) > value.get("message_count", 0):
        raise CollectionStateError()
    error = value.get("error_code", "")
    if not isinstance(error, str) or (error and error not in COLLECTION_ERROR_CODES):
        raise CollectionStateError()
    if status == "pending":
        if phase != "queued" or claim or started or finished or error or any(value.get(key, 0) for key in _COUNTS):
            raise CollectionStateError()
    elif status == "running":
        if phase not in {"collecting", "reviewing", "syncing"} or not claim or not started or finished or error:
            raise CollectionStateError()
    elif phase != "complete" or not claim or not started or not finished or bool(error) != (status != "success"):
        raise CollectionStateError()
    return value


def public_collection(value):
    """Remove local-only evidence before validating the public receipt."""
    if not isinstance(value, dict):
        raise CollectionStateError()
    return validate_collection({key: copy.deepcopy(value[key]) for key in COLLECTION_FIELDS if key in value})


def new_request(at, previous=None):
    if previous is not None:
        validate_collection(previous)
        if previous["status"] in {"pending", "running"}:
            raise CollectionStateError("collection_busy")
    requested = _after(at, previous["requested_at"] if previous else None)
    return validate_collection({
        "request_id": uuid4().hex, "requested_at": requested, "updated_at": requested,
        "status": "pending", "phase": "queued", "claim_id": "", "started_at": "", "finished_at": "",
        "message_count": 0, "new_message_count": 0, "action_count": 0, "error_code": "",
    })


def claim_collection(value, at, *, claim_id=None):
    validate_collection(value)
    if value["status"] != "pending":
        raise CollectionStateError("collection_busy")
    claimed = copy.deepcopy(value)
    stamp = _after(at, value["updated_at"])
    claimed.update(status="running", phase="collecting", updated_at=stamp, started_at=stamp,
                   claim_id=_identifier(uuid4().hex if claim_id is None else claim_id))
    return validate_collection(claimed)


def _running(value, claim_id):
    validate_collection(value)
    _identifier(claim_id)
    if value["status"] != "running":
        raise CollectionStateError("collection_not_running")
    if value.get("claim_id") != claim_id:
        raise CollectionStateError("collection_claim_mismatch")
    return copy.deepcopy(value)


def _counts(value, **counts):
    for key, count in counts.items():
        if count is not None:
            value[key] = count


def advance_collection(value, claim_id, at, *, phase, message_count=None, new_message_count=None, action_count=None):
    updated = _running(value, claim_id)
    if (not isinstance(phase, str) or phase not in {"collecting", "reviewing", "syncing"}
            or COLLECTION_PHASES.index(phase) < COLLECTION_PHASES.index(value["phase"])):
        raise CollectionStateError("collection_invalid_transition")
    updated.update(phase=phase, updated_at=_after(at, value["updated_at"]))
    _counts(updated, message_count=message_count, new_message_count=new_message_count, action_count=action_count)
    return validate_collection(updated)


def finish_collection(value, claim_id, at, *, status, error_code="", message_count=None,
                      new_message_count=None, action_count=None):
    updated = _running(value, claim_id)
    if not isinstance(status, str) or status not in _TERMINAL:
        raise CollectionStateError("collection_invalid_transition")
    stamp = _after(at, value["updated_at"])
    updated.update(status=status, phase="complete", updated_at=stamp, finished_at=stamp, error_code=error_code)
    _counts(updated, message_count=message_count, new_message_count=new_message_count, action_count=action_count)
    return validate_collection(updated)


def apply_remote_collection(snapshot, remote):
    """Latest remote state, including absence, wins over all local versions."""
    value = None
    if remote is not None and "manual_collection" in remote:
        # Validate remote input strictly; sanitization must not legitimize a
        # remotely supplied path, prompt, or command by silently discarding it.
        value = validate_collection(remote["manual_collection"])
    snapshot.pop("manual_collection", None)
    if value is not None:
        snapshot["manual_collection"] = public_collection(value)
    return snapshot
