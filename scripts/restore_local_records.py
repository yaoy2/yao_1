"""First-time restore from the private ledger; existing databases are never replaced."""

import importlib.util
import json
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils import github_backup_sync as sync
from utils.data_sync_validation import MANAGED_FILES, equivalent_backup, validate_backup
from utils.local_data_store import SQLITE_BACKUPS
from utils.todo_chat import local_secrets


def build_database(repo_path, content, directory):
    filename, table, module_name = SQLITE_BACKUPS[repo_path]
    spec = importlib.util.spec_from_file_location("recovery_" + module_name, ROOT / "utils" / (module_name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DB_PATH = str(directory / filename)
    module.BACKUP_MD_PATH = str(directory / (module_name + "-verified.md"))
    if module_name == "budget_db":
        module.BACKUP_XLSX_PATH = str(directory / "budget_ledger_backup.xlsx")
    records = validate_backup(repo_path, content)
    module.init_db()
    if module_name == "todo_db":
        module.import_todo_records(records)
    else:
        module.restore_synced_records(records)
    generated = Path(module.BACKUP_MD_PATH).read_text(encoding="utf-8")
    if not equivalent_backup(repo_path, content, generated):
        raise RuntimeError(f"{repo_path} 重建后与来源不一致，未安装到本机。")
    with closing(sqlite3.connect(module.DB_PATH)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("重建数据库完整性检查未通过。")
        count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if count != len(records):
        raise RuntimeError("数据库记录数量与云端备份不一致。")
    return {"database": filename, "records": count, "verified": True}


def main():
    for filename, _, _ in SQLITE_BACKUPS.values():
        if (ROOT / "data" / filename).exists():
            print("已有本机账本，首次恢复入口未执行覆盖；后续由各页面自动核对同步。")
            return 1
    stage = ROOT / ".local-backups" / datetime.now().strftime("recovery-%Y%m%d-%H%M%S-%f")
    directory = stage / "data"
    directory.mkdir(parents=True)
    secrets = local_secrets()
    snapshots, databases = {}, {}
    for repo_path in MANAGED_FILES:
        result = sync.read_file_from_github(repo_path, secrets=secrets)
        if not result.get("ok"):
            raise RuntimeError(f"{repo_path} 未能读取，未恢复到正式目录。")
        validate_backup(repo_path, result["content"])
        snapshots[repo_path] = result
        sync._atomic_text(stage / repo_path, result["content"])
        if repo_path in SQLITE_BACKUPS:
            databases[repo_path] = build_database(repo_path, result["content"], directory)
    # Validate all existing destination files before installing any snapshot.
    for repo_path, snapshot in snapshots.items():
        destination = ROOT / repo_path
        if destination.exists() and not equivalent_backup(repo_path, destination.read_text(encoding="utf-8"), snapshot["content"]):
            raise RuntimeError(f"{repo_path} 已有不同的本机资料，未覆盖。")
    for repo_path, snapshot in snapshots.items():
        destination = ROOT / repo_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if repo_path in databases:
            filename = databases[repo_path]["database"]
            target = destination.parent / filename
            # Exclusive creation prevents accidental reruns from overwriting a DB.
            with target.open("xb") as target_file, (directory / filename).open("rb") as source_file:
                shutil.copyfileobj(source_file, target_file)
        sync._atomic_text(destination, snapshot["content"])
        sync.remember_local_sync_baseline(destination, repo_path, snapshot["content"], snapshot["sha"], secrets=secrets)
    spreadsheet = directory / "budget_ledger_backup.xlsx"
    if spreadsheet.exists():
        with (ROOT / "data" / spreadsheet.name).open("xb") as target, spreadsheet.open("rb") as source:
            shutil.copyfileobj(source, target)
    manifest = {"created_at": datetime.now().isoformat(), "source_repo": sync.DEFAULT_REPO,
                "files": {path: {"sha": value["sha"]} for path, value in snapshots.items()},
                "databases": databases, "private_source_snapshot": str(stage)}
    sync._atomic_text(stage / "verification.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    for value in databases.values():
        print(f"{value['database']}: {value['records']} 条，逐条核对与完整性检查通过")
    print("已恢复十份云端备份；仅写入本机，未改动私有仓库。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"恢复停止：{exc}；来源快照已保留。")
        raise SystemExit(1)
