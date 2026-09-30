"""Pull or push dynamic data files between local data/ and the private data repository.

Usage: python scripts/data_repo_sync.py pull|push data/xxx.json [data/yyy.md ...]
Uses GITHUB_BACKUP_TOKEN when configured, otherwise the local gh CLI login.
"""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils import github_backup_sync
from utils.todo_chat import GitHubCliSession, local_secrets


def main(argv):
    if len(argv) < 2 or argv[0] not in {"pull", "push"}:
        print(__doc__)
        return 2
    secrets, environ, session = local_secrets(), os.environ, None
    if not github_backup_sync.get_backup_sync_config(secrets, environ)["enabled"]:
        executable = shutil.which("gh")
        if not executable:
            print("请配置 GITHUB_BACKUP_TOKEN，或先登录本机 GitHub CLI。")
            return 2
        # The custom transport ignores Authorization headers and uses gh's own login.
        session = GitHubCliSession(executable)
        environ = {**os.environ, "GITHUB_BACKUP_TOKEN": "handled-by-gh-cli"}

    failed = False
    for repo_path in argv[1:]:
        repo_path = repo_path.replace("\\", "/")
        local_path = ROOT / repo_path
        if argv[0] == "pull":
            result = github_backup_sync.download_file_from_github(
                local_path, repo_path, secrets=secrets, environ=environ, session=session)
        else:
            result = github_backup_sync.sync_file_to_github(
                local_path, repo_path, f"data: sync {local_path.name}",
                secrets=secrets, environ=environ, session=session)
        print(f"{argv[0]} {repo_path}: {result}")
        failed = failed or not result.get("ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
