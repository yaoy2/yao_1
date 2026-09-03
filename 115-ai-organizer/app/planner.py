from __future__ import annotations

from typing import Any

from .classifier import classify_item
from .config import Settings
from .db import db_session, init_db, upsert_plan
from .series import SERIES_CATEGORY, cluster_series, series_key, time_bucket

# 只有这些分类的视频参与系列聚类；电影/动漫/电视剧已有明确去处。
CLUSTERABLE_CATEGORIES = {"待识别", "普通视频", "其他"}


def _join_path(*parts: str) -> str:
    cleaned = [p.strip("/").strip() for p in parts if p and p.strip("/").strip()]
    return "/" + "/".join(cleaned)


def rebuild_plans(settings: Settings) -> int:
    init_db(settings.db_path)
    updated = 0
    with db_session(settings.db_path) as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, file_id, name, full_path, is_directory, extension, created_at
                FROM files
                WHERE is_directory = 0
                """
            ).fetchall()
        ]
        plan_by_row = {}
        for row in rows:
            classification = classify_item(
                name=row["name"],
                full_path=row["full_path"],
                is_directory=False,
                extension=row["extension"],
            )
            plan_by_row[row["id"]] = {
                "file_row_id": row["id"],
                "file_id": row["file_id"],
                "original_path": row["full_path"],
                "original_name": row["name"],
                "created_at": row["created_at"],
                "category": classification.category,
                **{
                    k: v
                    for k, v in classification.as_dict().items()
                    if k != "category"
                },
            }

        # 第二遍：同系列视频归集到一个文件夹（不改名，只归集）。
        cluster_rows = [
            r for r in rows if plan_by_row[r["id"]]["category"] in CLUSTERABLE_CATEGORIES
        ]
        grouped_ids = set()
        group_by_key = {}
        for group in cluster_series(cluster_rows):
            group_by_key.setdefault(group.key, group)
            confidence = "high" if group.same_parent or len(group.file_row_ids) >= 4 else "medium"
            reason = (
                f"与另外 {len(group.file_row_ids) - 1} 个文件名同源（"
                f"{'同一目录' if group.same_parent else '跨目录'}），"
                f"归入系列文件夹 /{SERIES_CATEGORY}/{group.display_name}/。"
            )
            for row_id in group.file_row_ids:
                plan = plan_by_row[row_id]
                plan["category"] = SERIES_CATEGORY
                plan["suggested_path"] = _join_path(
                    SERIES_CATEGORY, group.display_name, plan["original_name"]
                )
                plan["suggested_name"] = plan["original_name"]
                plan["confidence"] = confidence
                plan["reason"] = reason
                grouped_ids.add(row_id)

        # 第二遍半：图片文件名能对上视频系列的，跟随系列；对不上的进 /图片/。
        for row in rows:
            plan = plan_by_row[row["id"]]
            if plan["category"] != "图片":
                continue
            group = group_by_key.get(series_key(row["name"]))
            if group is None:
                continue
            plan["suggested_path"] = _join_path(
                SERIES_CATEGORY, group.display_name, plan["original_name"]
            )
            plan["confidence"] = "medium"
            plan["reason"] = (
                f"文件名与视频系列 /{SERIES_CATEGORY}/{group.display_name}/ 同源，"
                "跟随该系列一起归集；否则图片默认不移动。"
            )

        # 第三遍：剩余待识别按 115 添加时间月份兜底归集。
        for plan in plan_by_row.values():
            if plan["category"] != "待识别" or plan["file_row_id"] in grouped_ids:
                continue
            bucket = time_bucket(plan.get("created_at"))
            if not bucket:
                continue
            plan["suggested_path"] = _join_path(
                "按时间归集", bucket, plan["original_name"]
            )
            plan["confidence"] = "low"
            plan["reason"] = (
                f"文件名特征不足，按 115 添加时间 {bucket} 兜底归集；"
                "建议人工核对后再批准。"
            )

        for plan in plan_by_row.values():
            plan.pop("created_at", None)
            upsert_plan(conn, plan)
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
