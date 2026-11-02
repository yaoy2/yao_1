"""Creation-time filtering is independent of the material's archive semester."""

from datetime import date, datetime, time
import os
import re


def validate_start_date(value: str, *, today: date | None = None) -> str:
    value = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("请输入有效起始日期，格式为 YYYY-MM-DD，例如 2026-11-02。")
    try:
        day = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("起始日期不存在，请重新选择。") from error
    if day > (today or date.today()):
        raise ValueError("起始日期不能晚于今天。")
    return value


def creation_time_ns(info) -> int:
    # On Unix, ctime is metadata-change time and must never stand in for birth time.
    value = getattr(info, "st_birthtime_ns", None)
    if value is None and os.name == "nt":
        value = info.st_ctime_ns  # Windows Python versions before 3.12.
    if value is None:
        raise ValueError("无法读取本机文件创建时间，不能按创建日期筛选。")
    return value


def creation_date_bounds(start_date: str, end_time: str) -> tuple[int, int]:
    end = datetime.fromisoformat(end_time)
    if end.tzinfo is None:
        raise ValueError("日期筛选截止时间缺少时区，请重新预览。")
    day = date.fromisoformat(validate_start_date(start_date, today=end.astimezone().date()))
    start = datetime.combine(day, time.min).astimezone()
    lower = int(start.timestamp()) * 1_000_000_000
    upper = int(end.timestamp()) * 1_000_000_000 + end.microsecond * 1000
    if lower > upper:
        raise ValueError("日期筛选范围无效，请重新预览。")
    return lower, upper
