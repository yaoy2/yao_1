"""Guarded private-data sync. Usage: python scripts/data_repo_sync.py pull|push|status --all
or supply specific data/... paths. Code Git commands never include these files.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils import github_backup_sync as sync
from utils.data_sync_validation import MANAGED_FILES, equivalent_backup, validate_backup, would_drop_records
from utils.todo_chat import local_secrets
from utils.local_data_store import SQLITE_BACKUPS, database_backup


def checked_path(repo_path):
    repo_path = sync._normalized_path(repo_path)
    if repo_path not in MANAGED_FILES:
        raise ValueError("此入口只同步已登记的私有账本；新文件须先登记校验和隐私规则。")
    local = ROOT / repo_path
    if not local.resolve().is_relative_to((ROOT / "data").resolve()):
        raise ValueError("文件位置超出本机 data 目录。")
    return repo_path, local


def prepare(action, paths, secrets, environ):
    items = []
    for value in paths:
        repo_path, local = checked_path(value)
        remote = sync.read_file_from_github(repo_path, secrets, environ)
        if not remote.get("ok"):
            raise RuntimeError(f"{repo_path} 无法读取云端，未改动本机或远端。")
        validate_backup(repo_path, remote["content"])
        baseline = sync.get_local_sync_baseline(local, repo_path, secrets, environ)
        content = local.read_text(encoding="utf-8") if local.exists() else None
        database_content = database_backup(local, repo_path)
        if database_content is not None:
            if action == "pull":
                # Pages reconcile the DB against the OLD baseline. Advancing the MD
                # baseline alone would misidentify an old DB as new local edits.
                items.append((repo_path, local, remote, content, None))
                continue
            if content is None or not equivalent_backup(repo_path, content, database_content):
                raise RuntimeError(f"{repo_path} 与本机数据库不一致，未上传；请打开对应模块核对。")
        if content is not None:
            validate_backup(repo_path, content)
        same_remote = content is not None and equivalent_backup(repo_path, content, remote["content"])
        same_base = (content is not None and baseline is not None
                     and equivalent_backup(repo_path, content, baseline["content"]))
        if action == "pull" and content is not None and not same_remote and not same_base:
            raise RuntimeError(f"{repo_path} 有本机独有修改，拉取已停止；记录保持原样，请在对应模块核对。")
        if action == "push" and not same_remote:
            if content is None or baseline is None:
                raise RuntimeError(f"{repo_path} 缺少本机文件或同步基线，未上传。")
            if baseline["sha"] != remote["sha"]:
                raise RuntimeError(f"{repo_path} 云端已更新，未上传；请先在对应模块合并。")
            # UI deletion uses a checked snapshot; the bulk command must never silently erase records.
            before, after = validate_backup(repo_path, baseline["content"]), validate_backup(repo_path, content)
            if would_drop_records(repo_path, before, after):
                raise RuntimeError(f"{repo_path} 存在记录被移除，批量上传已停止；请在对应模块确认删除。")
        items.append((repo_path, local, remote, content, same_remote))
    return items


def main(argv):
    if len(argv) < 2 or argv[0] not in {"pull", "push", "status"}:
        print(__doc__)
        return 2
    action = argv[0]
    paths = list(MANAGED_FILES) if argv[1:] == ["--all"] else argv[1:]
    if len(set(paths)) != len(paths):
        print("请勿重复指定数据文件。")
        return 2
    try:
        secrets, environ = local_secrets(), os.environ
        items = prepare(action, paths, secrets, environ)
        backup = ROOT / ".local-backups" / datetime.now().strftime("sync-%Y%m%d-%H%M%S-%f")
        for repo_path, local, remote, content, same_remote in items:
            if same_remote is None:
                print(f"{repo_path}: 云端已核对，本机数据库和基线已保留，由对应页面自动合并")
                continue
            if action == "status":
                print(f"{repo_path}: {'已同步' if same_remote else '待核对'}")
                continue
            current = local.read_text(encoding="utf-8") if local.exists() else None
            if current != content:
                raise RuntimeError(f"{repo_path} 在核对期间被本机修改，本次停止同步，已保留新改动。")
            if action == "pull":
                if content is not None and content != remote["content"]:
                    sync._atomic_text(backup / repo_path, content)
                sync._atomic_text(local, remote["content"])
                sync.remember_local_sync_baseline(local, repo_path, remote["content"], remote["sha"], secrets, environ)
            elif same_remote:
                sync.remember_local_sync_baseline(local, repo_path, remote["content"], remote["sha"], secrets, environ)
            else:
                result = sync.sync_file_to_github(local, repo_path, f"data: sync {local.name}",
                                                 secrets, environ, expected_sha=remote["sha"])
                if not result.get("ok"):
                    raise RuntimeError(f"{repo_path} 上传未成功。")
            print(f"{repo_path}: 已核对{'并拉取' if action == 'pull' else '并同步'}")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"同步停止：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
