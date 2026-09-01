from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT NOT NULL DEFAULT '',
    parent_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    full_path TEXT NOT NULL UNIQUE,
    is_directory INTEGER NOT NULL DEFAULT 0,
    extension TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    duration REAL,
    width INTEGER,
    height INTEGER,
    media_type TEXT,
    hash_sha1 TEXT,
    file_id_source TEXT NOT NULL DEFAULT 'missing',
    extra_json TEXT NOT NULL DEFAULT '{}',
    scan_time TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_files_native_id
ON files(file_id)
WHERE file_id != '' AND file_id_source = 'native';

CREATE TABLE IF NOT EXISTS organize_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_row_id INTEGER NOT NULL UNIQUE,
    file_id TEXT,
    original_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    category TEXT NOT NULL,
    suggested_name TEXT,
    suggested_path TEXT,
    reason TEXT,
    confidence TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    execute_status TEXT NOT NULL DEFAULT 'not_executed',
    updated_at TEXT NOT NULL,
    FOREIGN KEY(file_row_id) REFERENCES files(id)
);

CREATE TABLE IF NOT EXISTS operation_logs (
    operation_id TEXT PRIMARY KEY,
    file_id TEXT,
    operation TEXT NOT NULL,
    old_path TEXT,
    new_path TEXT,
    old_name TEXT,
    new_name TEXT,
    time TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    scan_dir TEXT NOT NULL,
    max_depth INTEGER,
    max_files INTEGER,
    folder_count INTEGER DEFAULT 0,
    file_count INTEGER DEFAULT 0,
    total_size INTEGER DEFAULT 0,
    native_file_id_found INTEGER DEFAULT 0,
    status TEXT,
    error TEXT
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def db_session(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_file(conn: sqlite3.Connection, record: dict[str, Any]) -> int:
    payload = {
        "file_id": record.get("file_id") or "",
        "parent_id": record.get("parent_id") or "",
        "name": record["name"],
        "full_path": record["full_path"],
        "is_directory": 1 if record.get("is_directory") else 0,
        "extension": record.get("extension") or "",
        "size": int(record.get("size") or 0),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "duration": record.get("duration"),
        "width": record.get("width"),
        "height": record.get("height"),
        "media_type": record.get("media_type"),
        "hash_sha1": record.get("hash_sha1"),
        "file_id_source": record.get("file_id_source") or "missing",
        "extra_json": record.get("extra_json")
        if isinstance(record.get("extra_json"), str)
        else json.dumps(record.get("extra_json") or {}, ensure_ascii=False),
        "scan_time": record.get("scan_time") or utc_now(),
    }
    if payload["file_id"] and payload["file_id_source"] == "native":
        existing = conn.execute(
            "SELECT id FROM files WHERE file_id = ? AND file_id_source = 'native'",
            (payload["file_id"],),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE files SET
                    parent_id = :parent_id,
                    name = :name,
                    full_path = :full_path,
                    is_directory = :is_directory,
                    extension = :extension,
                    size = :size,
                    created_at = :created_at,
                    updated_at = :updated_at,
                    duration = :duration,
                    width = :width,
                    height = :height,
                    media_type = :media_type,
                    hash_sha1 = :hash_sha1,
                    extra_json = :extra_json,
                    scan_time = :scan_time
                WHERE id = :existing_id
                """,
                {**payload, "existing_id": int(existing["id"])},
            )
            return int(existing["id"])
    conn.execute(
        """
        INSERT INTO files (
            file_id, parent_id, name, full_path, is_directory, extension, size,
            created_at, updated_at, duration, width, height, media_type,
            hash_sha1, file_id_source, extra_json, scan_time
        ) VALUES (
            :file_id, :parent_id, :name, :full_path, :is_directory, :extension, :size,
            :created_at, :updated_at, :duration, :width, :height, :media_type,
            :hash_sha1, :file_id_source, :extra_json, :scan_time
        )
        ON CONFLICT(full_path) DO UPDATE SET
            file_id = excluded.file_id,
            parent_id = excluded.parent_id,
            name = excluded.name,
            is_directory = excluded.is_directory,
            extension = excluded.extension,
            size = excluded.size,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at,
            duration = excluded.duration,
            width = excluded.width,
            height = excluded.height,
            media_type = excluded.media_type,
            hash_sha1 = excluded.hash_sha1,
            file_id_source = excluded.file_id_source,
            extra_json = excluded.extra_json,
            scan_time = excluded.scan_time
        """,
        payload,
    )
    row = conn.execute(
        "SELECT id FROM files WHERE full_path = ?", (payload["full_path"],)
    ).fetchone()
    return int(row["id"])


def upsert_plan(conn: sqlite3.Connection, record: dict[str, Any]) -> int:
    payload = {
        "file_row_id": record["file_row_id"],
        "file_id": record.get("file_id") or "",
        "original_path": record["original_path"],
        "original_name": record["original_name"],
        "category": record["category"],
        "suggested_name": record.get("suggested_name") or "",
        "suggested_path": record.get("suggested_path") or "",
        "reason": record.get("reason") or "",
        "confidence": record["confidence"],
        "updated_at": utc_now(),
    }
    conn.execute(
        """
        INSERT INTO organize_plans (
            file_row_id, file_id, original_path, original_name, category,
            suggested_name, suggested_path, reason, confidence, approved,
            execute_status, updated_at
        ) VALUES (
            :file_row_id, :file_id, :original_path, :original_name, :category,
            :suggested_name, :suggested_path, :reason, :confidence, 0,
            'not_executed', :updated_at
        )
        ON CONFLICT(file_row_id) DO UPDATE SET
            file_id = excluded.file_id,
            original_path = excluded.original_path,
            original_name = excluded.original_name,
            category = excluded.category,
            suggested_name = excluded.suggested_name,
            suggested_path = excluded.suggested_path,
            reason = excluded.reason,
            confidence = excluded.confidence,
            updated_at = excluded.updated_at
        """,
        payload,
    )
    row = conn.execute(
        "SELECT id FROM organize_plans WHERE file_row_id = ?",
        (payload["file_row_id"],),
    ).fetchone()
    return int(row["id"])


def set_plan_approved(conn: sqlite3.Connection, plan_ids: Iterable[int], approved: bool) -> int:
    ids = [int(item) for item in plan_ids]
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"""
        UPDATE organize_plans
        SET approved = ?, updated_at = ?
        WHERE id IN ({placeholders})
        """,
        [1 if approved else 0, utc_now(), *ids],
    )
    return conn.execute("SELECT changes()").fetchone()[0]


def set_plan_execute_status(
    conn: sqlite3.Connection, plan_id: int, status: str
) -> None:
    conn.execute(
        """
        UPDATE organize_plans
        SET execute_status = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, utc_now(), int(plan_id)),
    )


def add_operation_log(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO operation_logs (
            operation_id, file_id, operation, old_path, new_path,
            old_name, new_name, time, status, error
        ) VALUES (
            :operation_id, :file_id, :operation, :old_path, :new_path,
            :old_name, :new_name, :time, :status, :error
        )
        """,
        {
            "operation_id": record["operation_id"],
            "file_id": record.get("file_id") or "",
            "operation": record["operation"],
            "old_path": record.get("old_path") or "",
            "new_path": record.get("new_path") or "",
            "old_name": record.get("old_name") or "",
            "new_name": record.get("new_name") or "",
            "time": record.get("time") or utc_now(),
            "status": record.get("status") or "blocked",
            "error": record.get("error") or "",
        },
    )


def start_scan_run(conn: sqlite3.Connection, scan_dir: str, max_depth: int, max_files: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO scan_runs (started_at, scan_dir, max_depth, max_files, status)
        VALUES (?, ?, ?, ?, 'running')
        """,
        (utc_now(), scan_dir, max_depth, max_files),
    )
    return int(cursor.lastrowid)


def finish_scan_run(conn: sqlite3.Connection, run_id: int, summary: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE scan_runs
        SET finished_at = ?, folder_count = ?, file_count = ?, total_size = ?,
            native_file_id_found = ?, status = ?, error = ?
        WHERE id = ?
        """,
        (
            utc_now(),
            int(summary.get("folder_count") or 0),
            int(summary.get("file_count") or 0),
            int(summary.get("total_size") or 0),
            1 if summary.get("native_file_id_found") else 0,
            summary.get("status") or "ok",
            summary.get("error") or "",
            run_id,
        ),
    )


def file_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    current = conn.execute(
        """
        SELECT started_at FROM scan_runs
        WHERE status = 'ok'
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    snapshot_start = current["started_at"] if current else ""
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_items,
            SUM(CASE WHEN is_directory = 1 THEN 1 ELSE 0 END) AS folder_count,
            SUM(CASE WHEN is_directory = 0 THEN 1 ELSE 0 END) AS file_count,
            SUM(CASE WHEN is_directory = 0 THEN size ELSE 0 END) AS total_size,
            MAX(scan_time) AS last_scan_time
        FROM files
        WHERE scan_time >= ?
        """,
        (snapshot_start,),
    ).fetchone()
    pending = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM organize_plans p JOIN files f ON f.id = p.file_row_id
        WHERE p.category = '待识别' AND f.scan_time >= ?
        """,
        (snapshot_start,),
    ).fetchone()
    categories = {
        item["category"]: item["n"]
        for item in conn.execute(
            """
            SELECT p.category, COUNT(*) AS n
            FROM organize_plans p JOIN files f ON f.id = p.file_row_id
            WHERE f.scan_time >= ?
            GROUP BY p.category
            """,
            (snapshot_start,),
        )
    }
    latest = conn.execute(
        """
        SELECT scan_dir, max_files, folder_count, file_count, total_size,
               native_file_id_found, started_at, finished_at, status, error
        FROM scan_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return {
        "total_items": int(row["total_items"] or 0),
        "folder_count": int(row["folder_count"] or 0),
        "file_count": int(row["file_count"] or 0),
        "total_size": int(row["total_size"] or 0),
        "last_scan_time": row["last_scan_time"],
        "pending_count": int(pending["n"] or 0),
        "categories": categories,
        "latest_run": dict(latest) if latest else None,
    }


def list_plans(
    conn: sqlite3.Connection,
    category: str = "",
    confidence: str = "",
    keyword: str = "",
    approved: str = "",
) -> list[dict[str, Any]]:
    current = conn.execute(
        "SELECT started_at FROM scan_runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    snapshot_start = current["started_at"] if current else ""
    clauses = ["f.scan_time >= ?"]
    params: list[Any] = [snapshot_start]
    if category:
        clauses.append("p.category = ?")
        params.append(category)
    if confidence:
        clauses.append("p.confidence = ?")
        params.append(confidence)
    if keyword:
        clauses.append("(p.original_name LIKE ? OR p.original_path LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like])
    if approved == "approved":
        clauses.append("p.approved = 1")
    elif approved == "pending":
        clauses.append("p.approved = 0")
    sql = f"""
        SELECT p.*, f.full_path, f.size, f.extension, f.file_id_source, f.is_directory
        FROM organize_plans p
        JOIN files f ON f.id = p.file_row_id
        WHERE {' AND '.join(clauses)}
        ORDER BY p.id DESC
    """
    return [dict(row) for row in conn.execute(sql, params)]
