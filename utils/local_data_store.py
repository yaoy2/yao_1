"""Read local SQLite snapshots without initialization or changing their contents."""

import sqlite3
from contextlib import closing
from pathlib import Path

SQLITE_BACKUPS = {
    "data/budget_ledger_backup.md": ("budget.db", "expense_records", "budget_db"),
    "data/todo_items_backup.md": ("todos.db", "todo_items", "todo_db"),
    "data/web_memos_backup.md": ("web_memos.db", "web_memos", "web_memo_db"),
}


def database_backup(local_path, repo_path):
    if repo_path not in SQLITE_BACKUPS:
        return None
    filename, table, module_name = SQLITE_BACKUPS[repo_path]
    db_path = Path(local_path).parent / filename
    if not db_path.exists():
        return None
    from utils import budget_db, todo_db, web_memo_db
    module = {"budget_db": budget_db, "todo_db": todo_db, "web_memo_db": web_memo_db}[module_name]
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("本机数据库完整性检查未通过；未覆盖本机或云端。")
        rows = connection.execute(f"SELECT * FROM {table}").fetchall()
    records = [dict(row) if module_name == "budget_db" else module._record_from_row(row) for row in rows]
    return module.build_markdown_backup(records)
