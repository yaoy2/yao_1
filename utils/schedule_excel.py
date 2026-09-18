"""Read the departmental summary workbook and replace the M06 semester cache.

Usage: python -m utils.schedule_excel SOURCE.xlsx --term 2026-2027-1 --output-dir data
Department/quality-teacher sheets take precedence over the council summary.
"""

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from openpyxl import load_workbook

from utils.schedule_docx import WEEKDAYS, is_physical_education, is_truncated, parse_weeks


ENTRY_PATTERN = re.compile(r"【\d+】.*?(?=【\d+】|$)", re.S)
WEEK_PATTERN = re.compile(r"\d[\d\s,，、;；周\-]*周(?:[（(][单双][）)])?")
PERIOD_PATTERN = re.compile(r"(?<!\d)(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*节")
COUNT_PATTERN = re.compile(r"(?:选课)?人数\s*[:：]\s*(\d+)")
ROOM_PATTERN = re.compile(r"^([A-Z]\d(?:-?\d){1,5})([^\d]*?实验室)?")
SHEET_CATEGORIES = {
    "医信工系": "医学信息工程系",
    "医学影像系": "医学影像技术系",
    "健服系": "健康服务与管理系",
    "健康体育部": "院内其余老师",
    "素质老师": "院内其余老师",
    "院务会": "院内其余老师",
}


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("（", "(").replace("）", ")").replace("，", ",")


def parse_summary_weeks(text: str) -> list[int]:
    parts = re.split(r"[,，、;；]", re.sub(r"\s+", "", text))
    return parse_weeks(",".join(part if "周" in part else part + "周" for part in parts))


def parse_summary_entry(raw: str, sheet: str, cell: str, day: str, term: str, previous: list[dict]) -> dict:
    text = re.sub(r"\s+", " ", re.sub(r"^【\d+】\s*", "", raw)).strip()
    teacher_match = re.match(r"([\u4e00-\u9fff]{2,4})\s+(.+)", text)
    if not teacher_match:
        raise ValueError(f"{sheet}!{cell} 无法识别教师：{raw}")
    teacher, body = teacher_match.groups()
    week_matches = list(WEEK_PATTERN.finditer(body))
    if len(week_matches) != 1:
        raise ValueError(f"{sheet}!{cell} 周次缺失或不明确：{raw}")
    week_match = week_matches[0]
    week_text = re.sub(r"\s+", "", week_match[0])
    weeks = parse_summary_weeks(week_text)
    left, right = week_match.span()
    if left and body[left - 1] == "第":
        left -= 1
    if left and body[left - 1] in "（(" and right < len(body) and body[right] in "）)":
        left, right = left - 1, right + 1
    body = (body[:left] + " " + body[right:]).strip()
    period_matches = list(PERIOD_PATTERN.finditer(body))
    if len(period_matches) > 1:
        raise ValueError(f"{sheet}!{cell} 有多个节次：{raw}")
    import_notes = []
    if period_matches:
        period_match = period_matches[0]
        start, end = int(period_match[1]), int(period_match[2] or period_match[1])
        course, tail = body[:period_match.start()].strip(), body[period_match.end():].strip()
        if not 1 <= start <= end <= 14:
            raise ValueError(f"{sheet}!{cell} 节次无效：{raw}")
    else:
        # One source entry omits periods. Use an older record only if every
        # substantive field and the worksheet's morning/afternoon/evening agree.
        course, separator, tail = body.partition(" ")
        if not separator:
            raise ValueError(f"{sheet}!{cell} 缺少节次和教室：{raw}")
        start = end = None
    counts = COUNT_PATTERN.findall(tail)
    if len(counts) > 1:
        raise ValueError(f"{sheet}!{cell} 人数不明确：{raw}")
    student_count = int(counts[0]) if counts else None
    tail = COUNT_PATTERN.sub("", tail).strip()
    room_match = ROOM_PATTERN.match(tail)
    room = ""
    if room_match:
        room = re.sub(r"\s+", "", room_match[0])
        tail = tail[room_match.end():].strip()
    classes = tail.strip()
    if classes == "班级未列":
        classes = ""
    if start is None:
        band = {3: range(1, 6), 4: range(6, 11), 5: range(11, 15)}.get(int(re.search(r"\d+", cell)[0]), range(1, 15))
        candidates = {
            (r["start_period"], r["end_period"])
            for r in previous
            if r.get("term") == term and r["teachers"] == [teacher]
            and normalized(r["course"]) == normalized(course) and r["weekday"] == day
            and r.get("weeks") == weeks and normalized(r["classroom"]) == normalized(room)
            and normalized(r["class_group"]) == normalized(classes)
            and r["start_period"] in band and r["end_period"] in band
        }
        if len(candidates) != 1:
            raise ValueError(f"{sheet}!{cell} 缺少节次，且原课表不能唯一补齐：{raw}")
        start, end = candidates.pop()
        import_notes.append(f"最新表未列节次，按原教师课表唯一匹配补为第{start}-{end}节。")
    if not course:
        raise ValueError(f"{sheet}!{cell} 课程名缺失：{raw}")
    return {
        "term": term,
        "sheet": sheet,
        "source_refs": [f"{sheet}!{cell} {re.match(r'【\d+】', raw)[0]}"],
        "weekday": day,
        "start_period": start,
        "end_period": end,
        "teachers": [teacher],
        "teacher_label": teacher,
        "course": course,
        "course_code": "",
        "credits": None,
        "week_text": week_text,
        "weeks": weeks,
        "teaching_type": "",
        "classroom": room,
        "class_group": classes,
        "student_count": student_count,
        "source_truncated": is_truncated(raw),
        "import_notes": import_notes,
        "periods_from_previous": bool(import_notes),
        "raw": raw.strip(),
    }


def record_identity(record: dict) -> tuple:
    return (
        tuple(record["teachers"]), normalized(record["course"]), record["weekday"],
        record["start_period"], record["end_period"], tuple(record["weeks"]),
        normalized(record["classroom"]), normalized(record["class_group"]), record["student_count"],
    )


def select_authoritative_records(records: list[dict]) -> tuple[list[dict], list[dict], int]:
    """Keep primary-sheet assignments, deduplicate, then supplement from council."""
    primary = [r for r in records if r["sheet"] != "院务会"]
    primary_courses = {(tuple(r["teachers"]), normalized(r["course"])) for r in primary}
    selected: dict[tuple, dict] = {}
    duplicate_count = 0
    overrides = []
    for record in primary + [r for r in records if r["sheet"] == "院务会"]:
        key = record_identity(record)
        if key in selected:
            existing = selected[key]
            existing["source_refs"] = list(dict.fromkeys(existing["source_refs"] + record["source_refs"]))
            duplicate_count += 1
            continue
        if record["sheet"] == "院务会":
            same_teacher_course = (tuple(record["teachers"]), normalized(record["course"])) in primary_courses
            same_assignment = any(
                normalized(r["course"]) == normalized(record["course"])
                and r["weekday"] == record["weekday"]
                and (r["start_period"], r["end_period"]) == (record["start_period"], record["end_period"])
                and set(r["weeks"]) & set(record["weeks"])
                and r["class_group"] and normalized(r["class_group"]) == normalized(record["class_group"])
                for r in primary
            )
            if same_teacher_course or same_assignment:
                overrides.append(record)
                continue
        selected[key] = record.copy()
    result = sorted(selected.values(), key=lambda r: (WEEKDAYS.index(r["weekday"]), r["start_period"], r["teacher_label"], r["course"], r["weeks"]))
    return result, overrides, duplicate_count


def mark_source_overlaps(records: list[dict]) -> list[dict]:
    """Expose unresolved overlaps already present in the authoritative sheets."""
    overlaps = []
    for first, second in combinations(records, 2):
        if first["teachers"] != second["teachers"] or first["weekday"] != second["weekday"]:
            continue
        weeks = sorted(set(first["weeks"]) & set(second["weeks"]))
        start = max(first["start_period"], second["start_period"])
        end = min(first["end_period"], second["end_period"])
        if not weeks or start > end:
            continue
        refs = [first["source_refs"][0], second["source_refs"][0]]
        overlaps.append({"teacher": first["teacher_label"], "weekday": first["weekday"], "periods": [start, end], "weeks": weeks, "source_refs": refs})
        for record, other in [(first, second), (second, first)]:
            record["import_notes"].append(
                f"最新分表中同一教师时段重叠：另有“{other['course']}”第{other['start_period']}-{other['end_period']}节（{other['week_text']}，{other['classroom'] or '教室未列'}）；请核对原表。"
            )
    return overlaps


def parse_summary_workbook(path: Path, term: str, previous: list[dict], *, allow_stale_titles: set[str] | None = None) -> tuple[list[dict], dict, list[dict]]:
    workbook = load_workbook(path, data_only=True)
    records = []
    periods = {}
    excluded = 0
    source_count = 0
    sheet_counts = {}
    title_notes = []
    try:
        for sheet in workbook:
            if sheet.title not in SHEET_CATEGORIES:
                raise ValueError(f"未识别工作表：{sheet.title}")
            title = str(sheet["A1"].value or "")
            year, semester = term.rsplit("-", 1)
            if year not in title or f"第{'一' if semester == '1' else '二'}学期" not in title:
                if sheet.title not in (allow_stale_titles or set()):
                    raise ValueError(f"{sheet.title} 的标题学期不符：{title}")
                title_notes.append(f"{sheet.title} 表头仍为“{title}”；按用户指定的最新版文件归入 {term}。")
            day_columns = {cell.column: str(cell.value) for cell in sheet[2] if cell.value in WEEKDAYS}
            if list(day_columns.values()) != WEEKDAYS:
                raise ValueError(f"{sheet.title} 星期列不完整")
            count = 0
            for row in sheet:
                for cell in row:
                    if cell.value is None:
                        continue
                    value = str(cell.value)
                    if cell.column == 2:
                        for number, start_hour, start_minute, end_hour, end_minute in re.findall(r"第(\d+)节\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", value):
                            time = f"{int(start_hour):02}:{start_minute}-{int(end_hour):02}:{end_minute}"
                            if number in periods and periods[number] != time:
                                raise ValueError(f"第{number}节时间在分表间不一致")
                            periods[number] = time
                    if "【" not in value:
                        continue
                    if cell.column not in day_columns:
                        raise ValueError(f"{sheet.title}!{cell.coordinate} 课程不在星期列内")
                    entries = ENTRY_PATTERN.findall(value)
                    if len(entries) != len(re.findall(r"【\d+】", value)):
                        raise ValueError(f"{sheet.title}!{cell.coordinate} 课程条目标记异常")
                    for entry in entries:
                        count += 1
                        source_count += 1
                        if is_physical_education(entry):
                            excluded += 1
                            continue
                        records.append(parse_summary_entry(entry, sheet.title, cell.coordinate, day_columns[cell.column], term, previous))
            sheet_counts[sheet.title] = count
    finally:
        workbook.close()
    if set(periods) != {str(period) for period in range(1, 15)}:
        raise ValueError("缺少完整的 14 节作息时间")
    selected, overrides, duplicates = select_authoritative_records(records)
    overlaps = mark_source_overlaps(selected)
    teachers = sorted({t for r in selected for t in r["teachers"]})
    metadata = {
        "term": term,
        "source_file": path.name,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_format": "department_summary_xlsx",
        "source_entry_count": source_count,
        "source_sheet_entries": sheet_counts,
        "source_title_notes": title_notes,
        "teacher_count": len(teachers),
        "teachers": teachers,
        "record_count": len(selected),
        "excluded_physical_education_records": excluded,
        "duplicate_records_merged": duplicates,
        "council_records_superseded": len(overrides),
        "source_priority": "以所属系部、素质老师分表为准，院务会表仅补充分表没有的课程。",
        "truncated_source_cells": len({ref.split(" ")[0] for r in selected if r["source_truncated"] for ref in r["source_refs"][:1]}),
        "truncated_records": sum(r["source_truncated"] for r in selected),
        "records_with_unknown_weeks": sum(not r["weeks"] for r in selected),
        "periods_completed_from_previous_cache": sum(r["periods_from_previous"] for r in selected),
        "source_overlap_count": len(overlaps),
        "source_overlaps": overlaps,
        "period_times": {str(p): periods[str(p)] for p in range(1, 15)},
        "category_note": "沿用既有教师分组，新教师根据最新版分表归类。",
    }
    return selected, metadata, overrides


def build_categories(records: list[dict], previous: dict[str, str]) -> dict[str, str]:
    scores = defaultdict(Counter)
    for record in records:
        for teacher in record["teachers"]:
            scores[teacher][SHEET_CATEGORIES[record["sheet"]]] += 1
    return {teacher: previous.get(teacher, scores[teacher].most_common(1)[0][0]) for teacher in sorted(scores)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--term", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path, help="Write proposed data here instead of replacing the live cache")
    parser.add_argument("--allow-stale-title", action="append", default=[], help="Explicitly accept a sheet with a stale semester title")
    args = parser.parse_args()
    previous = json.loads((args.output_dir / "schedule_cache.json").read_text(encoding="utf-8"))
    previous_categories = json.loads((args.output_dir / "teacher_category_cache.json").read_text(encoding="utf-8"))
    records, metadata, overrides = parse_summary_workbook(args.source, args.term, previous, allow_stale_titles=set(args.allow_stale_title))
    categories = build_categories(records, previous_categories)
    target = args.preview_dir or args.output_dir
    target.mkdir(parents=True, exist_ok=True)
    for name, data in [("schedule_cache.json", records), ("schedule_metadata.json", metadata), ("teacher_category_cache.json", categories)]:
        (target / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.preview_dir:
        (target / "superseded_council_records.json").write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in metadata.items() if k not in {"teachers", "period_times", "source_overlaps"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
