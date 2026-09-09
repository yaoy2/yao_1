"""Receive website filing requests on the designated Windows computer.

The website stores requests only. This process saves attachment bytes using
local configuration and acknowledges only verified files through a SHA guard.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import mail_workbench_sync as sync
from utils import mail_workspace
from utils.mail_filing import export_message
from utils.mail_filing_state import is_filing_requested, public_filing


def _hidden_runner(*args, **kwargs):
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(*args, **kwargs)


def configuration(root):
    root = mail_workspace._root_path(root)
    config = json.loads(mail_workspace._inside(root, "config.json").read_text(encoding="utf-8"))
    filing = config.get("filing") or {}
    if filing.get("enabled") is not True:
        raise sync.MailCommandError("filing_disabled")
    destination = Path(filing.get("destination_root", ""))
    if not destination.is_absolute() or not destination.is_dir():
        raise sync.MailCommandError("filing_destination_unavailable")
    return root, config, destination


def _write_worker_state(root, result, interval=None):
    data = {"pid": os.getpid(), "checked_at": mail_workspace.now_iso(),
            "poll_seconds": interval, **result}
    mail_workspace._atomic_json(mail_workspace._inside(root, "state/filing_worker.json"), data)


def run_cycle(root):
    """Poll explicit user requests; idle cycles never connect to the mailbox."""
    from scripts.mail_manual_collect import run_once as receive_once
    try:
        collection = receive_once(root)
    except sync.MailCommandError as exc:
        collection = {"status": "busy" if exc.code == "collection_already_running" else "error",
                      "error_code": exc.code if exc.code in {
                          "collection_already_running", "COLLECTION_CONFIG_INVALID"} else "SYNC_FAILED"}
    except Exception:
        collection = {"status": "error", "error_code": "SYNC_FAILED"}
    try:
        filing = run_once(root)
    except sync.MailCommandError as exc:
        filing = {"status": "error", "error_code": exc.code}
    except Exception:
        filing = {"status": "error", "error_code": "filing_operation_failed"}
    return {**filing, "manual_collection": collection}


def run_once(root, *, client=None, exporter=export_message):
    root, config, destination = configuration(root)
    client = client or sync.GithubCLI(config["private_repo"], config["private_branch"], _hidden_runner)
    remote = client.read()
    if remote["snapshot"] is None:
        raise sync.MailCommandError("snapshot_not_found")
    with mail_workspace._locked(root):
        original = mail_workspace.load_dashboard(root)
        sync._check_identity(original, remote["snapshot"])
        local = sync.merge_remote_states(original, remote["snapshot"])
        if local != original:
            mail_workspace._atomic_json(mail_workspace._inside(root, "dashboard.json"), local)
    by_id = {message["id"]: message for message in local["messages"]}
    queued = [message for message in remote["snapshot"]["messages"]
              if (message.get("filing") or {}).get("status") == "pending"
              and is_filing_requested(remote["snapshot"], message["id"])]
    result = {"status": "idle", "queued_count": len(queued), "processed_count": 0,
              "acknowledged_count": 0, "saved_count": 0, "failed_count": 0}
    if not queued:
        return result
    completed = {}
    for request in queued[:10]:
        filing = request["filing"]
        message = by_id.get(request["id"])
        if message is None:
            outcome = {"status": "error", "destination": "", "saved_count": 0,
                       "total_count": len(request.get("attachments", [])), "error_count": 1,
                       "error_codes": ["SOURCE_MESSAGE_MISSING"], "files": []}
        else:
            outcome = exporter(root, destination, message, allow_imap=True)
        receipt = {"message_id": request["id"], "request_id": filing["request_id"],
                   "checked_at": mail_workspace.now_iso(), **outcome}
        # Fixed hex request IDs are validated by the shared snapshot validator.
        receipt_path = "state/filing_results/" + filing["request_id"] + ".json"
        mail_workspace._atomic_json(mail_workspace._inside(root, receipt_path), receipt)
        updated_at = max(mail_workspace.parse_time(mail_workspace.now_iso()),
                         mail_workspace.parse_time(filing["requested_at"])).isoformat()
        updated = {**filing, **{key: value for key, value in outcome.items() if key != "files"},
                   "updated_at": updated_at}
        completed[request["id"]] = public_filing(updated)
        result["processed_count"] += 1
        result["saved_count"] += outcome["saved_count"]
        result["failed_count"] += outcome["status"] != "success"
    # The user may have changed other mail, cancelled, or requested a new run
    # during copying. Start from that latest snapshot and patch matching jobs.
    latest = client.read()
    if latest["snapshot"] is None:
        raise sync.MailCommandError("snapshot_not_found")
    sync._check_identity(local, latest["snapshot"])
    amended = copy.deepcopy(latest["snapshot"])
    for message in amended["messages"]:
        outcome = completed.get(message["id"])
        current = message.get("filing") or {}
        if (outcome and current.get("status") == "pending"
                and current.get("request_id") == outcome["request_id"]
                and is_filing_requested(amended, message["id"])):
            message["filing"] = outcome
            result["acknowledged_count"] += 1
    if result["acknowledged_count"]:
        amended["updated_at"] = mail_workspace.now_iso()
        # Enforce the allowlist even if an unrelated remote record has extra
        # fields; raw mail and local paths are never forwarded by this worker.
        snapshot = mail_workspace.public_snapshot(amended, root)
        sync._validate_snapshot(snapshot)
        client.write(snapshot, latest["version"])
        with mail_workspace._locked(root):
            current_local = mail_workspace.load_dashboard(root)
            merged = sync.merge_remote_states(current_local, snapshot)
            mail_workspace._atomic_json(mail_workspace._inside(root, "dashboard.json"), merged)
    result["status"] = "processed" if result["acknowledged_count"] else "superseded"
    return result


@contextmanager
def receiver_lock(root):
    """One worker per workspace, released by Windows after process exit."""
    path = mail_workspace._inside(root, "state/filing_receiver.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise sync.MailCommandError("receiver_already_running") from None
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main(argv=None):
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        if not 15 <= args.interval <= 3600:
            raise sync.MailCommandError("invalid_poll_interval")
        # Receiving a manual request does not depend on an attachment folder.
        root = mail_workspace._root_path(args.root)
        with receiver_lock(root):
            while True:
                try:
                    result = run_cycle(root)
                except sync.MailCommandError as exc:
                    result = {"status": "error", "error_code": exc.code}
                except Exception:
                    result = {"status": "error", "error_code": "filing_operation_failed"}
                _write_worker_state(root, result, args.interval if args.watch else None)
                if sys.stdout is not None:
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                if not args.watch:
                    return int(result["status"] == "error")
                time.sleep(args.interval)
    except sync.MailCommandError as exc:
        if sys.stdout is not None:
            print(json.dumps({"status": "error", "error_code": exc.code}))
        return int(exc.code != "receiver_already_running")
    except Exception:
        if sys.stdout is not None:
            print(json.dumps({"status": "error", "error_code": "filing_setup_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
