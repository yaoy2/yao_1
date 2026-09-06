"""Synchronize the local mail index through the already authenticated gh CLI.

Original mail and attachment bytes stay local. Only a whitelisted dashboard is
sent to an independently verified private repository. No credential is read by
this script, and raw gh output is never printed.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils import mail_private_sync, mail_workspace


DEFAULT_REPO = "yaoy2/mail-workbench-data"
DEFAULT_BRANCH = "main"
SYNC_STATE_PATH = "state/github_sync.json"
STATUS_FIELDS = ("status", "completed_at", "updated_at")
COLLECTIONS = ("messages", "actions", "runs", "reports")
_EARLIEST = datetime.min.replace(tzinfo=timezone.utc)


class MailCommandError(RuntimeError):
    """An error code safe for logs; optional version marks a confirmed upload."""

    def __init__(self, code, version=None):
        self.code = code
        self.version = version
        super().__init__(code)


def _validate_target(repo, branch):
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise MailCommandError("invalid_repo")
    if repo.casefold() == "yaoy2/yao_1":
        raise MailCommandError("public_repo_forbidden")
    if not isinstance(branch, str) or not branch.strip() or any(ord(char) < 32 or ord(char) == 127 for char in branch):
        raise MailCommandError("invalid_branch")


def _parse_response(completed):
    """Parse only the HTTP status and JSON body from gh's --include output."""
    try:
        output = completed.stdout.decode("utf-8").replace("\r\n", "\n")
        header, separator, body = output.partition("\n\n")
        status_line = header.splitlines()[0]
        match = re.fullmatch(r"HTTP/\S+\s+(\d{3})(?:\s+.*)?", status_line)
        if not separator or not match:
            raise ValueError
        status = int(match.group(1))
    except (AttributeError, UnicodeError, IndexError, ValueError):
        raise MailCommandError("gh_failed" if completed.returncode else "invalid_response") from None
    # Failed API calls still have a useful HTTP status, but their bodies can
    # contain private values and are deliberately neither parsed nor surfaced.
    if status not in (200, 201):
        return status, None
    if completed.returncode:
        raise MailCommandError("gh_failed")
    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError
    except (ValueError, TypeError):
        raise MailCommandError("invalid_response") from None
    return status, data


class GithubCLI:
    def __init__(self, repo=DEFAULT_REPO, branch=DEFAULT_BRANCH, runner=None):
        _validate_target(repo, branch)
        self.repo = repo
        self.branch = branch
        self.runner = subprocess.run if runner is None else runner

    def _api(self, method, endpoint, payload=None):
        command = ["gh", "api", endpoint, "--hostname", "github.com", "--method", method, "--include",
                   "--header", "Accept: application/vnd.github+json",
                   "--header", "X-GitHub-Api-Version: 2022-11-28"]
        raw = None
        if payload is not None:
            command.extend(["--input", "-"])
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            completed = self.runner(
                command, input=raw, capture_output=True, text=False, shell=False,
                check=False, timeout=35,
            )
        except FileNotFoundError:
            raise MailCommandError("gh_not_found") from None
        except subprocess.TimeoutExpired:
            raise MailCommandError("gh_timeout") from None
        except Exception:
            raise MailCommandError("gh_failed") from None
        return _parse_response(completed)

    @staticmethod
    def _require(status, accepted, stage):
        if status in accepted:
            return
        if status == 401:
            raise MailCommandError("unauthorized")
        if status == 403:
            raise MailCommandError("forbidden")
        if stage == "put" and status in (409, 422):
            raise MailCommandError("conflict")
        if status == 404:
            raise MailCommandError("repo_not_found" if stage == "repo" else "snapshot_not_found")
        raise MailCommandError("remote_error")

    def read(self):
        status, metadata = self._api("GET", f"repos/{self.repo}")
        self._require(status, {200}, "repo")
        if metadata.get("private") is not True:
            raise MailCommandError("public_repo_forbidden")
        # gh follows server redirects; a renamed/transferred repository must
        # not silently become the mail data destination.
        if str(metadata.get("full_name", "")).casefold() != self.repo.casefold():
            raise MailCommandError("repository_mismatch")
        query = urlencode({"ref": self.branch})
        status, content = self._api("GET", f"repos/{self.repo}/contents/dashboard.json?{query}")
        if status == 404:
            return {"snapshot": None, "version": None}
        self._require(status, {200}, "get")
        version = content.get("sha")
        if not isinstance(version, str) or not version or content.get("encoding") != "base64" or not isinstance(content.get("content"), str):
            raise MailCommandError("invalid_response")
        try:
            raw = base64.b64decode("".join(content["content"].split()), validate=True).decode("utf-8-sig")
            snapshot = json.loads(raw)
        except (ValueError, TypeError, UnicodeError):
            raise MailCommandError("invalid_snapshot") from None
        _validate_snapshot(snapshot)
        return {"snapshot": snapshot, "version": version}

    def write(self, snapshot, version):
        payload = {
            "message": "mail: synchronize dashboard index",
            "branch": self.branch,
            "content": base64.b64encode(
                (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            ).decode("ascii"),
        }
        if version is not None:
            payload["sha"] = version
        status, response = self._api("PUT", f"repos/{self.repo}/contents/dashboard.json", payload)
        self._require(status, {200, 201}, "put")
        content = response.get("content")
        new_version = content.get("sha") if isinstance(content, dict) else None
        if not isinstance(new_version, str) or not new_version:
            raise MailCommandError("upload_unconfirmed")
        return new_version


def _validate_snapshot(data):
    try:
        mail_private_sync._validate_snapshot(data)
        for collection in COLLECTIONS:
            seen = set()
            for row in data[collection]:
                identifier = row.get("id")
                if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
                    raise ValueError
                seen.add(identifier)
        for row in data["runs"]:
            for key in ("started_at", "finished_at"):
                if row.get(key):
                    mail_workspace.parse_time(row[key])
        for row in data["reports"]:
            for key in ("generated_at", "period_start", "period_end"):
                if row.get(key):
                    mail_workspace.parse_time(row[key])
    except (mail_private_sync.MailSyncError, ValueError, TypeError, KeyError):
        raise MailCommandError("invalid_snapshot") from None
    return data


def _moment(row, *keys):
    for key in keys:
        if row.get(key):
            try:
                return mail_workspace.parse_time(row[key])
            except (ValueError, TypeError):
                raise MailCommandError("invalid_snapshot") from None
    return _EARLIEST


def _check_identity(local, remote):
    if remote is not None and (local["account"] != remote["account"] or local["timezone"] != remote["timezone"]):
        raise MailCommandError("workspace_mismatch")


def _status_winner(local, remote):
    return remote if _moment(remote, "updated_at") >= _moment(local, "updated_at") else local


def _merge_status(local_action, remote_action):
    winner = _status_winner(local_action, remote_action)
    for key in STATUS_FIELDS:
        local_action[key] = copy.deepcopy(winner.get(key))


def _merge_message_triage(local_message, remote_message):
    """Merge user decisions independently from collection metadata timestamps."""
    candidates = [row for row in (local_message, remote_message) if "triage_status" in row]
    if not candidates:
        return
    winner = candidates[0]
    if len(candidates) == 2 and _moment(candidates[1], "triage_updated_at") >= _moment(winner, "triage_updated_at"):
        winner = candidates[1]
    for key in mail_workspace.MESSAGE_TRIAGE_FIELDS:
        local_message[key] = copy.deepcopy(winner[key])


def merge_remote_states(local, remote):
    """Pull status fields only; unknown remote records wait for a full push merge."""
    _check_identity(local, remote)
    result = copy.deepcopy(local)
    if remote is None:
        return result
    actions = {row["id"]: row for row in remote["actions"]}
    for action in result["actions"]:
        if action["id"] in actions:
            _merge_status(action, actions[action["id"]])
    messages = {row["id"]: row for row in remote["messages"]}
    for message in result["messages"]:
        if message["id"] in messages:
            _merge_message_triage(message, messages[message["id"]])
    if result != local:
        result["updated_at"] = mail_workspace.now_iso()
    return result


def _merge_messages(local, remote):
    merged = {row["id"]: copy.deepcopy(row) for row in remote}
    for row in local:
        previous = merged.get(row["id"], {})
        combined = {**previous, **copy.deepcopy(row)}
        _merge_message_triage(combined, previous)
        attachments = {item["id"]: copy.deepcopy(item) for item in previous.get("attachments", [])}
        attachments.update({item["id"]: copy.deepcopy(item) for item in row.get("attachments", [])})
        combined["attachments"] = list(attachments.values())
        merged[row["id"]] = combined
    return list(merged.values())


def _merge_latest(local, remote, keys):
    merged = {row["id"]: copy.deepcopy(row) for row in remote}
    for row in local:
        previous = merged.get(row["id"])
        if previous is None or _moment(row, *keys) > _moment(previous, *keys):
            merged[row["id"]] = copy.deepcopy(row)
    return list(merged.values())


def merge_for_push(local, remote, root):
    """Preserve the union of IDs and keep all local-only source data local."""
    _check_identity(local, remote)
    if remote is None:
        return copy.deepcopy(local)
    # Treat the remote index as untrusted input; neither arbitrary fields nor
    # raw bodies should be imported or forwarded to the next remote version.
    remote = mail_workspace.public_snapshot(remote, root)
    result = copy.deepcopy(local)
    result["messages"] = _merge_messages(local["messages"], remote["messages"])
    messages = {row["id"]: row for row in result["messages"]}
    remote_actioned = {row.get("message_id") for row in remote["actions"]}
    actions = {row["id"]: copy.deepcopy(row) for row in remote["actions"]}
    for row in local["actions"]:
        previous = actions.get(row["id"])
        combined = {**(previous or {}), **copy.deepcopy(row)}
        if previous is not None:
            _merge_status(combined, previous)
        elif row.get("message_id") not in remote_actioned:
            message = messages.get(row.get("message_id"), {})
            if (message.get("triage_status") in {"no_action", "out_of_scope"}
                    and _moment(message, "triage_updated_at") >= _moment(row, "updated_at")):
                # The web user may exempt this mail after local extraction but
                # before its first upload. Preserve that newer explicit choice.
                combined.update(status=message["triage_status"], completed_at=None,
                                updated_at=message["triage_updated_at"])
        actions[row["id"]] = combined
    result["actions"] = list(actions.values())
    result["runs"] = _merge_latest(local["runs"], remote["runs"], ("finished_at", "started_at"))
    result["reports"] = _merge_latest(local["reports"], remote["reports"], ("generated_at", "period_end"))
    # Local coverage records verified collection progress, not synchronization.
    result["coverage"] = copy.deepcopy(local["coverage"])
    return result


def _counts(snapshot):
    return {name[:-1] + "_count": len(snapshot[name]) if snapshot else 0 for name in COLLECTIONS}


def _result(client, status, snapshot, version):
    return {"status": status, "repo": client.repo, "branch": client.branch,
            "private": True, "version": version, **_counts(snapshot)}


def _record_sync(root, client, operation, snapshot, version, status="success"):
    state = {"schema_version": 1, "operation": operation, "status": status,
             "repo": client.repo, "branch": client.branch, "version": version,
             "synced_at": mail_workspace.now_iso(), **_counts(snapshot)}
    mail_workspace._atomic_json(mail_workspace._inside(root, SYNC_STATE_PATH), state)


def _local_root(root):
    try:
        path = mail_workspace._root_path(root)
        if not path.is_dir():
            raise ValueError
    except (OSError, ValueError, TypeError):
        raise MailCommandError("invalid_root") from None
    return path


def synchronize(root, operation, repo=DEFAULT_REPO, branch=DEFAULT_BRANCH, runner=None):
    if operation not in {"pull", "push", "status"}:
        raise MailCommandError("invalid_operation")
    root = _local_root(root)
    client = GithubCLI(repo, branch, runner)
    if operation == "status":
        remote = client.read()
        return _result(client, "ready" if remote["snapshot"] else "empty", remote["snapshot"], remote["version"])
    try:
        # Use the archive module's OS lock for the full read/merge/write cycle,
        # so an ingestion or report cannot be overwritten while gh is running.
        with mail_workspace._locked(root):
            local = _validate_snapshot(mail_workspace.load_dashboard(root))
            remote = client.read()
            _check_identity(local, remote["snapshot"])
            if operation == "pull":
                if remote["snapshot"] is None:
                    _record_sync(root, client, operation, local, None, "empty")
                    return _result(client, "empty", local, None)
                merged = merge_remote_states(local, remote["snapshot"])
                if merged != local:
                    mail_workspace._atomic_json(mail_workspace._inside(root, "dashboard.json"), merged)
                _record_sync(root, client, operation, merged, remote["version"])
                return _result(client, "pulled", merged, remote["version"])
            merged = merge_for_push(local, remote["snapshot"], root)
            merged["updated_at"] = mail_workspace.now_iso()
            snapshot = mail_workspace.public_snapshot(merged, root)
            _validate_snapshot(snapshot)
            version = client.write(snapshot, remote["version"])
            try:
                mail_workspace._atomic_json(mail_workspace._inside(root, "dashboard.json"), merged)
                _record_sync(root, client, operation, snapshot, version)
            except (OSError, ValueError, RuntimeError):
                raise MailCommandError("local_write_failed_after_upload", version) from None
            return _result(client, "pushed", snapshot, version)
    except MailCommandError:
        raise
    except RuntimeError:
        raise MailCommandError("workspace_busy") from None
    except (OSError, ValueError, TypeError, KeyError):
        raise MailCommandError("local_data_error") from None


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Sync a mail index with a verified private GitHub repository through gh.")
    parser.add_argument("--root", required=True, help="Explicit absolute local archive directory")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("command", choices=("pull", "push", "status"))
    args = parser.parse_args(argv)
    try:
        result = synchronize(args.root, args.command, args.repo, args.branch)
    except MailCommandError as error:
        result = {"status": "error", "error_code": error.code}
        if error.version:
            result["version"] = error.version
        print(json.dumps(result, ensure_ascii=False))
        return 1
    except Exception:
        # Never print arbitrary exceptions: paths, input mail and gh diagnostics
        # are unsuitable for automation logs and can contain private material.
        print(json.dumps({"status": "error", "error_code": "operation_failed"}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
