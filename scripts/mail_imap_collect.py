"""Stage a read-only IMAP batch using the user's dedicated local credential.

No ingest or remote upload occurs here. The task reviews mail evidence and adds
grounded summaries/actions before passing this batch to mail_workbench.py.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import unicodedata
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.mail_imap_setup import load_setup_config
from utils import mail_imap
from utils.mail_imap_credentials import CredentialError, read_credential
from utils.mail_workspace import _atomic_json, _inside, load_dashboard, now_iso, parse_time


def collection_window(config, dashboard, *, at=None, since=None):
    end = parse_time(at or now_iso())
    first = parse_time(config["collection_start"])
    old = dashboard.get("coverage", {}).get("through")
    start = max(first, parse_time(old) - timedelta(days=1)) if old else first
    if since is not None:
        start = parse_time(since)
        if start < first:
            raise ValueError("collection start precedes configured boundary")
    if start > end:
        raise ValueError("collection window is reversed")
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def reconcile_existing(batch, dashboard):
    """Retain existing attachment identities only when evidence matches uniquely."""
    existing = {m["id"]: m for m in dashboard["messages"]}
    for message in batch["messages"]:
        old = existing.get(message["id"])
        if not old:
            continue
        # Existing human-reviewed descriptions remain until this task revises them.
        for field in ("category", "summary"):
            message[field] = old.get(field, message.get(field, ""))
        incoming = message.get("attachments", [])
        previous_attachments = old.get("attachments", [])
        used = set()
        matched = set()
        # Resolve content identities for the whole batch before any name fallback.
        for index, attachment in enumerate(incoming):
            sha = attachment.get("sha256")
            candidates = [a for a in previous_attachments if sha and a.get("sha256") == sha]
            if len(candidates) == 1 and sum(a.get("sha256") == sha for a in incoming) == 1:
                attachment["id"] = candidates[0]["id"]
                used.add(attachment["id"])
                matched.add(index)
        for index, attachment in enumerate(incoming):
            if index in matched:
                continue
            name = " ".join(unicodedata.normalize("NFC", attachment["name"]).split())
            matches = [a for a in previous_attachments
                       if " ".join(unicodedata.normalize("NFC", a["name"]).split()) == name]
            if sum(" ".join(unicodedata.normalize("NFC", a["name"]).split()) == name for a in incoming) != 1:
                matches = []
            matches = [a for a in matches if a["id"] not in used]
            if len(matches) == 1:
                attachment["id"] = matches[0]["id"]
                used.add(attachment["id"])
        ids = [a["id"] for a in incoming]
        if len(ids) != len(set(ids)):
            raise ValueError("attachment identity conflict")
    return batch


def collect_workspace(root, *, kind="daily", at=None, since=None, manual_request_id=None):
    if manual_request_id is not None and not re.fullmatch(r"[0-9a-f]{32}", manual_request_id):
        raise ValueError("invalid manual request identity")
    setup = load_setup_config(root)
    root = setup["root"]
    config = json.loads(_inside(root, "config.json").read_text(encoding="utf-8"))
    dashboard = load_dashboard(root)
    if config["account"] != dashboard["account"]:
        raise ValueError("workspace account mismatch")
    start, end = collection_window(config, dashboard, at=at, since=since)
    folders = config["mail_folders"]
    if not isinstance(folders, list) or not folders or any(not isinstance(x, str) or not x for x in folders):
        raise ValueError("invalid folder configuration")
    storage_mode = config.get("collection_storage", "full")
    if not isinstance(storage_mode, str) or storage_mode not in {"full", "on_demand"}:
        raise ValueError("invalid collection storage configuration")
    batch = {"schema_version": 1, "account": setup["account"], "id": "imap-" + uuid4().hex,
             "kind": kind, "started_at": now_iso(), "window": {"since": start, "through": end, "complete": False},
             "messages": [], "actions": [], "errors": [], "storage_mode": storage_mode}
    retries = ([m["id"] for m in dashboard["messages"]
                if any(a.get("status") != "success" for a in m.get("attachments", []))]
               if storage_mode == "full" else [])
    incoming = _inside(root, "incoming")
    incoming.mkdir(exist_ok=True)
    client, password = None, None
    try:
        username, password = read_credential(setup["credential_target"])
        if username != setup["account"]:
            raise CredentialError("stored_account_mismatch")
        client = mail_imap.connect(setup["host"], setup["port"], username, password)
        password = None
        batch = mail_imap.collect(client, account=setup["account"], folders=folders,
                                  since=start, through=end, staging_dir=incoming,
                                  source_url=config["source_url"], retry_message_ids=retries,
                                  storage_mode=storage_mode)
        batch["kind"] = kind
        batch["storage_mode"] = storage_mode
        reconcile_existing(batch, dashboard)
    except CredentialError:
        batch["errors"].append("IMAP_LOCAL_CREDENTIAL_REQUIRED")
    except mail_imap.ImapCollectionError as exc:
        batch["errors"].append(str(exc))
    finally:
        password = None
        if client is not None:
            try:
                client.shutdown()
            except Exception:
                pass
    batch["finished_at"] = now_iso()
    if manual_request_id is not None:
        # Identifies only this user-requested transient batch after a crash.
        batch["manual_request_id"] = manual_request_id
    path = _inside(root, "incoming/" + batch["id"] + ".json")
    _atomic_json(path, batch)
    summary = {"status": "staged" if batch["window"]["complete"] else "partial",
               "storage_mode": storage_mode,
               "batch_path": str(path), "window": copy.deepcopy(batch["window"]),
               "message_count": len(batch["messages"]),
               "attachment_count": sum(len(m.get("attachments", [])) for m in batch["messages"]),
               "error_count": len(batch["errors"]), "errors": batch["errors"],
               "checked_at": batch["finished_at"]}
    if manual_request_id is not None:
        summary["manual_request_id"] = manual_request_id
    _atomic_json(_inside(root, "state/imap_collection.json"), summary)
    return summary


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--kind", choices=("daily", "morning", "weekly"), default="daily")
    parser.add_argument("--at")
    parser.add_argument("--since")
    args = parser.parse_args(argv)
    try:
        result = collect_workspace(args.root, kind=args.kind, at=args.at, since=args.since)
    except Exception:
        print(json.dumps({"status": "error", "error": "IMAP_COLLECTION_SETUP_OR_STAGING_FAILED"}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "staged" else 2


if __name__ == "__main__":
    raise SystemExit(main())
