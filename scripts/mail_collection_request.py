"""CAS-only manual collection controls shared by local entry and worker.

These helpers never collect mail, start AI, or accept remote execution options.
The caller holds its execution lock across claim and work. Only a confirmed
claim returns a new claim ID; a failed write never authorizes collection.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import mail_workbench_sync as sync
from utils import mail_collection_state as state
from utils import mail_workspace


def _hidden_runner(*args, **kwargs):
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(*args, **kwargs)


def _read(root, client):
    root = sync._local_root(root)
    with mail_workspace._locked(root):
        local = sync._validate_snapshot(mail_workspace.load_dashboard(root))
    if client is None:
        try:
            config = json.loads(mail_workspace._inside(root, "config.json").read_text(encoding="utf-8-sig"))
            client = sync.GithubCLI(config["private_repo"], config["private_branch"], _hidden_runner)
        except sync.MailCommandError:
            raise
        except (OSError, ValueError, KeyError, TypeError):
            raise sync.MailCommandError("collection_config_invalid") from None
    current = client.read()
    if current.get("snapshot") is None:
        raise sync.MailCommandError("snapshot_not_found")
    sync._validate_snapshot(current["snapshot"])
    sync._check_identity(local, current["snapshot"])
    if not isinstance(current.get("version"), str) or not current["version"]:
        raise sync.MailCommandError("invalid_response")
    return root, client, current


def _bundle(current):
    return {"snapshot": copy.deepcopy(current["snapshot"]), "version": current["version"],
            "source": "github", "manual_collection": copy.deepcopy(current["snapshot"]["manual_collection"])}


def _persist_confirmed(root, snapshot, version):
    try:
        with mail_workspace._locked(root):
            local = sync._validate_snapshot(mail_workspace.load_dashboard(root))
            sync._check_identity(local, snapshot)
            merged = sync.merge_remote_states(local, snapshot)
            mail_workspace._atomic_json(mail_workspace._inside(root, "dashboard.json"), merged)
    except (OSError, ValueError, RuntimeError):
        raise sync.MailCommandError("local_write_failed_after_upload", version) from None


def _write(root, client, current, value):
    amended = copy.deepcopy(current["snapshot"])
    amended["manual_collection"] = state.public_collection(value)
    amended["updated_at"] = value["updated_at"]
    snapshot = mail_workspace.public_snapshot(amended, root)
    sync._validate_snapshot(snapshot)
    version = client.write(snapshot, current["version"])
    if not isinstance(version, str) or not version:
        raise sync.MailCommandError("upload_unconfirmed")
    _persist_confirmed(root, snapshot, version)
    return _bundle({"snapshot": snapshot, "version": version})


def _requested(current, request_id):
    try:
        state._identifier(request_id)
    except state.CollectionStateError:
        raise sync.MailCommandError("invalid_collection") from None
    value = current["snapshot"].get("manual_collection")
    if value is None or value["request_id"] != request_id:
        raise sync.MailCommandError("collection_superseded")
    return value


def _transition(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except state.CollectionStateError as exc:
        raise sync.MailCommandError(exc.code) from None


def request(root, *, client=None, at=None):
    """Local manual entry queues a request, or returns the already active one."""
    root, client, current = _read(root, client)
    previous = current["snapshot"].get("manual_collection")
    if previous and previous["status"] in {"pending", "running"}:
        return {**_bundle(current), "created": False}
    value = _transition(state.new_request, at or mail_workspace.now_iso(), previous)
    return {**_write(root, client, current, value), "created": True}


def claim(root, request_id, *, claim_id=None, client=None, at=None):
    """Only the successful pending-to-running CAS grants execution ownership."""
    root, client, current = _read(root, client)
    value = _requested(current, request_id)
    claimed = _transition(state.claim_collection, value, at or mail_workspace.now_iso(), claim_id=claim_id)
    return _write(root, client, current, claimed)


def progress(root, request_id, claim_id, *, phase, client=None, at=None,
             message_count=None, new_message_count=None, action_count=None):
    root, client, current = _read(root, client)
    value = _requested(current, request_id)
    updated = _transition(state.advance_collection, value, claim_id, at or mail_workspace.now_iso(), phase=phase,
                          message_count=message_count, new_message_count=new_message_count, action_count=action_count)
    return _write(root, client, current, updated)


def finish(root, request_id, claim_id, *, status, error_code="", client=None, at=None,
           message_count=None, new_message_count=None, action_count=None):
    """Patch only this execution's result; a confirmed identical result is a no-op."""
    root, client, current = _read(root, client)
    value = _requested(current, request_id)
    if value["status"] in {"success", "partial", "error"}:
        counts = {"message_count": message_count, "new_message_count": new_message_count, "action_count": action_count}
        if (value.get("claim_id") == claim_id and value["status"] == status and value.get("error_code", "") == error_code
                and all(count is None or (type(count) is int and value.get(key, 0) == count) for key, count in counts.items())):
            # Heal a previous local-write failure using the terminal result
            # confirmed by this latest read, without another remote write.
            _persist_confirmed(root, current["snapshot"], current["version"])
            return _bundle(current)
        raise sync.MailCommandError("collection_not_running")
    updated = _transition(state.finish_collection, value, claim_id, at or mail_workspace.now_iso(), status=status,
                          error_code=error_code, message_count=message_count,
                          new_message_count=new_message_count, action_count=action_count)
    return _write(root, client, current, updated)
