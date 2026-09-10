"""Receive mail only after an explicit local or website request."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import mail_collection_request as jobs
from scripts import mail_workbench_sync as sync
from scripts.mail_imap_collect import collect_workspace
from scripts.mail_workbench import redact_review_batch
from utils import mail_workspace as workspace
from utils.mail_collection_state import COLLECTION_ERROR_CODES


def configuration(root):
    root = workspace._root_path(root)
    config = json.loads(workspace._inside(root, "config.json").read_text(encoding="utf-8-sig"))
    if config.get("collection_mode") != "manual" or config.get("collection_storage") != "on_demand":
        raise sync.MailCommandError("COLLECTION_CONFIG_INVALID")
    return root, config


@contextmanager
def collection_lock(root):
    path = workspace._inside(root, "state/manual_collection.lock")
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
            raise sync.MailCommandError("collection_already_running") from None
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _client(config):
    return sync.GithubAPI(config["private_repo"], config["private_branch"])


def _merge_remote(root, client):
    remote = client.read()
    with workspace._locked(root):
        local = workspace.load_dashboard(root)
        sync._check_identity(local, remote["snapshot"])
        merged = sync.merge_remote_states(local, remote["snapshot"])
        workspace._atomic_json(workspace._inside(root, "dashboard.json"), merged)
    return merged


def _publish(root, client):
    # Read the latest user choices and request state inside the short write lock.
    # A failed SHA write leaves the local result available for receipt-only retry.
    with workspace._locked(root):
        local = workspace.load_dashboard(root)
        remote = client.read()
        sync._check_identity(local, remote["snapshot"])
        merged = sync.merge_for_push(local, remote["snapshot"], root)
        merged["updated_at"] = workspace.now_iso()
        snapshot = workspace.public_snapshot(merged, root)
        sync._validate_snapshot(snapshot)
        version = client.write(snapshot, remote["version"])
        workspace._atomic_json(workspace._inside(root, "dashboard.json"), merged)
        sync._record_sync(root, client, "push", snapshot, version)
    return version


def _receipt_path(root, request_id):
    # request_id has already passed the shared snapshot validator.
    return workspace._inside(root, "state/manual_collection_results/" + request_id + ".json")


def _write_receipt(path, receipt, **updates):
    receipt.update(updates, updated_at=workspace.now_iso())
    workspace._atomic_json(path, receipt)


def _redact_owned_review(root, request_id, batch_id=None):
    """Clean only batches tagged by this manual execution, including after a crash."""
    clean = True
    incoming = workspace._inside(root, "incoming")
    if not incoming.is_dir():
        return True
    for path in incoming.glob("imap-*.json"):
        if not re.fullmatch(r"imap-[0-9a-f]{32}\.json", path.name) or path.is_symlink():
            continue
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            if path.stem == batch_id:
                clean = False
            continue
        if batch.get("manual_request_id") != request_id:
            if path.stem == batch_id:
                clean = False
            continue
        try:
            if redact_review_batch(root, path, batch, effective_storage_mode="on_demand") is not True:
                clean = False
        except (OSError, ValueError, TypeError):
            clean = False
    return clean


def _retry_cleanup(root):
    for path in workspace._inside(root, "state/manual_collection_results").glob("*.json"):
        if not re.fullmatch(r"[0-9a-f]{32}\.json", path.name) or path.is_symlink():
            continue
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if receipt.get("stage") != "cleanup_pending" or receipt.get("request_id") != path.stem:
            continue
        if not _redact_owned_review(root, path.stem, receipt.get("batch_id")):
            raise sync.MailCommandError("LOCAL_STATE_FAILED")
        _write_receipt(path, receipt, stage="finished")


def _finish_ready(root, client, job, path, receipt):
    counts = receipt.get("counts", {})
    jobs.progress(root, job["request_id"], job["claim_id"], phase="syncing", client=client, **counts)
    _publish(root, client)
    finished = jobs.finish(root, job["request_id"], job["claim_id"],
                           status=receipt["outcome"], error_code=receipt.get("error_code", ""),
                           client=client, **counts)
    _write_receipt(path, receipt, stage="finished")
    return finished["manual_collection"]


def _review(batch, dashboard, root):
    from utils.mail_manual_review import review_batch
    return review_batch(batch, dashboard, root)


def run_once(root, *, client=None, collector=collect_workspace, reviewer=_review):
    root, config = configuration(root)
    client = client or _client(config)
    with collection_lock(root):
        _retry_cleanup(root)
        remote = client.read()
        if remote["snapshot"] is None:
            raise sync.MailCommandError("snapshot_not_found")
        sync._validate_snapshot(remote["snapshot"])
        sync._check_identity(workspace.load_dashboard(root), remote["snapshot"])
        job = remote["snapshot"].get("manual_collection") or {}
        if not job:
            return {"status": "idle"}
        path = _receipt_path(root, job["request_id"])
        if job.get("status") not in {"pending", "running"}:
            receipt = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            if receipt.get("stage") == "cleanup_pending" and receipt.get("claim_id") == job.get("claim_id"):
                if not _redact_owned_review(root, job["request_id"], receipt.get("batch_id")):
                    raise sync.MailCommandError("LOCAL_STATE_FAILED")
                _write_receipt(path, receipt, stage="finished")
            return {"status": "idle"}
        if job["status"] == "running":
            # Another computer's running job is never stolen on a timeout.
            receipt = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            if receipt.get("claim_id") != job.get("claim_id"):
                return {"status": "waiting", "request_id": job["request_id"]}
            if receipt.get("stage") == "ready_to_sync":
                return _finish_ready(root, client, job, path, receipt)
            clean = _redact_owned_review(root, job["request_id"], receipt.get("batch_id"))
            prior_error = receipt.get("error_code", "")
            code = (prior_error if receipt.get("stage") in {"failed", "cleanup_pending"}
                    and prior_error in COLLECTION_ERROR_CODES else "WORKER_INTERRUPTED") if clean else "LOCAL_STATE_FAILED"
            result = jobs.finish(root, job["request_id"], job["claim_id"], status="error",
                                 error_code=code, client=client)
            _write_receipt(path, receipt, stage="finished" if clean else "cleanup_pending", error_code=code)
            return result["manual_collection"]
        receipt = {"request_id": job["request_id"], "claim_id": uuid4().hex, "stage": "claiming"}
        _write_receipt(path, receipt)
        claimed = jobs.claim(root, job["request_id"], client=client, claim_id=receipt["claim_id"])
        job = claimed["manual_collection"]
        _write_receipt(path, receipt, stage="collecting")
        batch = batch_path = None
        error_code = "COLLECTION_READ_FAILED"
        try:
            dashboard = _merge_remote(root, client)
            summary = collector(root, kind="daily", manual_request_id=job["request_id"])
            batch_path = Path(summary["batch_path"])
            if batch_path.is_symlink() or batch_path.resolve().parent != (root / "incoming").resolve():
                raise ValueError("invalid local batch")
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
            _write_receipt(path, receipt, batch_id=batch["id"])
            if not batch.get("messages") and batch.get("errors"):
                if any(code in batch["errors"] for code in ("IMAP_LOCAL_CREDENTIAL_REQUIRED", "IMAP_AUTHENTICATION_FAILED")):
                    error_code = "COLLECTION_AUTH_REQUIRED"
                raise ValueError("collection incomplete")
            jobs.progress(root, job["request_id"], job["claim_id"], phase="reviewing", client=client)
            _write_receipt(path, receipt, stage="reviewing")
            error_code = "REVIEW_FAILED"
            reviewed = reviewer(batch, dashboard, root)
            error_code = "INGEST_FAILED"
            # Pull again before ingest so decisions made while AI was working survive.
            _merge_remote(root, client)
            known_ids = {m["id"] for m in dashboard["messages"]}
            counts = {"message_count": len(reviewed["messages"]),
                      "new_message_count": sum(m["id"] not in known_ids for m in reviewed["messages"]),
                      "action_count": len(reviewed.get("actions", []))}
            result = workspace.ingest(root, reviewed)
            removed = redact_review_batch(root, batch_path, reviewed, effective_storage_mode=result["storage_mode"])
            if removed is not True:
                error_code = "LOCAL_STATE_FAILED"
                raise ValueError("review redaction failed")
            batch = None
            workspace.generate_report(root, "daily", reviewed["window"]["through"])
            outcome = "success" if result["status"] == "success" else "partial"
            _write_receipt(path, receipt, stage="ready_to_sync", counts=counts, outcome=outcome,
                           error_code="" if outcome == "success" else "COLLECTION_WINDOW_INCOMPLETE")
        except Exception as exc:
            allowed = {"REVIEW_UNAVAILABLE", "REVIEW_TIMEOUT", "REVIEW_FAILED", "REVIEW_OUTPUT_INVALID"}
            code = getattr(exc, "code", "")
            error_code = code if code in allowed else error_code
            clean = _redact_owned_review(root, job["request_id"], receipt.get("batch_id"))
            if batch is not None and batch_path is not None:
                try:
                    clean = (redact_review_batch(root, batch_path, batch, effective_storage_mode="on_demand") is True) and clean
                except (OSError, ValueError, TypeError):
                    clean = False
            if not clean:
                error_code = "LOCAL_STATE_FAILED"
            _write_receipt(path, receipt, stage="failed" if clean else "cleanup_pending", error_code=error_code)
            finished = jobs.finish(root, job["request_id"], job["claim_id"], status="error",
                                   error_code=error_code, client=client)
            _write_receipt(path, receipt, stage="finished" if clean else "cleanup_pending")
            return finished["manual_collection"]
        return _finish_ready(root, client, job, path, receipt)


def request_and_run(root, *, client=None):
    root, config = configuration(root)
    client = client or _client(config)
    result = jobs.request(root, client=client)
    try:
        return run_once(root, client=client)
    except sync.MailCommandError as exc:
        if exc.code == "collection_already_running":
            return result["manual_collection"]
        raise


def main(argv=None):
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--request", action="store_true", help="Explicitly request and receive mail now")
    args = parser.parse_args(argv)
    try:
        result = request_and_run(args.root) if args.request else run_once(args.root)
    except Exception as exc:
        code = getattr(exc, "code", "")
        known = {"COLLECTION_CONFIG_INVALID", "collection_already_running", "conflict", "snapshot_not_found"}
        result = {"status": "error", "error_code": code if code in known else "SYNC_FAILED"}
    if sys.stdout is not None:
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return int(result.get("status") == "error")


if __name__ == "__main__":
    raise SystemExit(main())
