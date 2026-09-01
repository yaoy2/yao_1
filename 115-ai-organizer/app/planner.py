from __future__ import annotations

from typing import Any

from .classifier import classify_item
from .config import Settings
from .db import db_session, init_db, upsert_plan


def rebuild_plans(settings: Settings) -> int:
    init_db(settings.db_path)
    updated = 0
    with db_session(settings.db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, file_id, name, full_path, is_directory, extension
            FROM files
            WHERE is_directory = 0
            """
        ).fetchall()
        for row in rows:
            classification = classify_item(
                name=row["name"],
                full_path=row["full_path"],
                is_directory=False,
                extension=row["extension"],
            )
            upsert_plan(
                conn,
                {
                    "file_row_id": row["id"],
                    "file_id": row["file_id"],
                    "original_path": row["full_path"],
                    "original_name": row["name"],
                    **classification.as_dict(),
                },
            )
            updated += 1
    return updated


def plan_from_record(record: dict[str, Any]) -> dict[str, Any]:
    classification = classify_item(
        name=record.get("name") or "",
        full_path=record.get("full_path") or "",
        is_directory=bool(record.get("is_directory")),
        extension=record.get("extension") or "",
    )
    return classification.as_dict()
