from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager, closing
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from utils.grade_workbench import GROUP_COLUMNS, STUDENT_COLUMNS, ScoreSettings, empty_groups, empty_students


BASE_DIR = Path(__file__).resolve().parents[1]
TASKS_DIR = BASE_DIR / "data" / "grade_workbench" / "tasks"


def safe_task_id(name: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", name.strip()).strip("-")
    return value[:60] or datetime.now().strftime("task-%Y%m%d-%H%M%S")


def task_dir(task_id: str) -> Path:
    return TASKS_DIR / task_id


def db_path(task_id: str) -> Path:
    return task_dir(task_id) / "task.db"


def connect(task_id: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path(task_id))
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def session(task_id: str):
    connection = connect(task_id)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def create_task(name: str, term: str, course: str) -> str:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    base = safe_task_id(name)
    task_id = base
    suffix = 2
    while task_dir(task_id).exists():
        task_id = f"{base}-{suffix}"
        suffix += 1
    path = task_dir(task_id)
    (path / "inputs").mkdir(parents=True)
    (path / "outputs").mkdir(parents=True)
    with closing(sqlite3.connect(path / "task.db")) as conn:
        with conn:
            _create_schema(conn)
            conn.executemany(
                "INSERT INTO meta(key, value) VALUES(?, ?)",
                [("name", name.strip()), ("term", term.strip()), ("course", course.strip()), ("created_at", _now())],
            )
            for key, value in ScoreSettings().to_dict().items():
                conn.execute("INSERT INTO settings(key, value) VALUES(?, ?)", (key, json.dumps(value, ensure_ascii=False)))
            _audit(conn, "创建任务", f"创建评分任务：{name.strip()}")
    return task_id


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS students(
            student_no TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            group_code TEXT NOT NULL,
            other_score REAL NOT NULL,
            coefficient REAL NOT NULL,
            individual_adjustment REAL NOT NULL,
            adjustment_reason TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS groups(
            group_code TEXT PRIMARY KEY,
            project_name TEXT NOT NULL,
            pitch_score REAL,
            report_score REAL,
            group_adjustment REAL NOT NULL,
            adjustment_reason TEXT NOT NULL,
            score_comment TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL
        );
        """
    )


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _audit(conn: sqlite3.Connection, action: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO audit_log(created_at, action, detail) VALUES(?, ?, ?)",
        (_now(), action, detail),
    )


def list_tasks() -> list[dict[str, str]]:
    if not TASKS_DIR.exists():
        return []
    tasks = []
    for path in sorted(TASKS_DIR.iterdir()):
        if not (path / "task.db").exists():
            continue
        try:
            with closing(sqlite3.connect(path / "task.db")) as conn:
                rows = dict(conn.execute("SELECT key, value FROM meta").fetchall())
            tasks.append({"task_id": path.name, **rows})
        except sqlite3.DatabaseError:
            continue
    return tasks


def load_meta(task_id: str) -> dict[str, str]:
    with session(task_id) as conn:
        return dict(conn.execute("SELECT key, value FROM meta").fetchall())


def load_settings(task_id: str) -> ScoreSettings:
    with session(task_id) as conn:
        values = {key: json.loads(value) for key, value in conn.execute("SELECT key, value FROM settings")}
    return ScoreSettings.from_dict(values)


def save_settings(task_id: str, settings: ScoreSettings) -> None:
    with session(task_id) as conn:
        for key, value in settings.to_dict().items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
        _audit(conn, "保存规则", "更新成绩权重、取整、上下限或统一调整。")


def load_students(task_id: str) -> pd.DataFrame:
    with session(task_id) as conn:
        rows = conn.execute("SELECT * FROM students ORDER BY class_name, student_no").fetchall()
    return pd.DataFrame([dict(row) for row in rows], columns=STUDENT_COLUMNS) if rows else empty_students()


def save_students(task_id: str, students: pd.DataFrame, action: str = "保存学生数据") -> None:
    records = students[STUDENT_COLUMNS].where(pd.notna(students), None).to_dict("records")
    with session(task_id) as conn:
        conn.execute("DELETE FROM students")
        conn.executemany(
            """INSERT INTO students(student_no,name,class_name,group_code,other_score,coefficient,individual_adjustment,adjustment_reason)
            VALUES(:student_no,:name,:class_name,:group_code,:other_score,:coefficient,:individual_adjustment,:adjustment_reason)""",
            records,
        )
        _audit(conn, action, f"保存 {len(records)} 名学生记录。")


def load_groups(task_id: str) -> pd.DataFrame:
    with session(task_id) as conn:
        rows = conn.execute("SELECT * FROM groups ORDER BY group_code").fetchall()
    return pd.DataFrame([dict(row) for row in rows], columns=GROUP_COLUMNS) if rows else empty_groups()


def save_groups(task_id: str, groups: pd.DataFrame, action: str = "保存小组评分") -> None:
    records = groups[GROUP_COLUMNS].where(pd.notna(groups), None).to_dict("records")
    with session(task_id) as conn:
        conn.execute("DELETE FROM groups")
        conn.executemany(
            """INSERT INTO groups(group_code,project_name,pitch_score,report_score,group_adjustment,adjustment_reason,score_comment)
            VALUES(:group_code,:project_name,:pitch_score,:report_score,:group_adjustment,:adjustment_reason,:score_comment)""",
            records,
        )
        _audit(conn, action, f"保存 {len(records)} 个小组记录；原始分与调整分分列保存。")


def load_audit(task_id: str, limit: int = 300) -> pd.DataFrame:
    with session(task_id) as conn:
        rows = conn.execute(
            "SELECT created_at, action, detail FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def output_dir(task_id: str) -> Path:
    path = task_dir(task_id) / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_input_file(task_id: str, file_name: str, content: bytes) -> Path:
    safe_name = Path(file_name).name
    destination = task_dir(task_id) / "inputs" / safe_name
    if destination.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = destination.with_name(f"{destination.stem}_{stamp}{destination.suffix}")
    destination.write_bytes(content)
    with session(task_id) as conn:
        _audit(conn, "保存源文件", f"只读保存输入文件：{destination.name}")
    return destination
