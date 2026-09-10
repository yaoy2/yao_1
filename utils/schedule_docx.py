"""Import the teaching system's teacher timetables without guessing omitted text.

Usage: python -m utils.schedule_docx SOURCE.docx --term 2026-2027-1 --output-dir data
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五"]
TITLE_PATTERN = re.compile(
    r"(?P<year>\d{4}-\d{4})学年第(?P<semester>[12])学期\s+"
    r"(?P<teacher>[^\[\]]+)\[[^\]]+\]\s*课表"
)
COURSE_PATTERN = re.compile(r"^(?P<course>.+?)\[(?P<code>\d+)\]\s*(?P<tail>.*)$")
CREDITS_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)学分$")
SESSION_PATTERN = re.compile(r"^(.+?周(?:[（(][单双][）)])?)\[([^\]]+)\]\s*(.*)$")
COUNT_PATTERN = re.compile(r"^选课人数\s*[:：]\s*(\d+)(?:\.{3}|…)?$")
PHYSICAL_EDUCATION_PATTERN = re.compile(r"体育|\bPhysical\s+Education\b", re.I)


def is_truncated(text: str) -> bool:
    return "..." in text or "…" in text


def parse_weeks(text: str) -> list[int]:
    """Expand disjoint ranges and odd/even markers; reject unrecognized notation."""
    weeks = set()
    for part in re.split(r"[,，、]", text):
        match = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*周(?:[（(]([单双])[）)])?\s*", part)
        if not match:
            raise ValueError(f"无法识别周次：{text}")
        start, end = int(match[1]), int(match[2] or match[1])
        if not 1 <= start <= end <= 53:
            raise ValueError(f"周次范围无效：{text}")
        for week in range(start, end + 1):
            if match[3] is None or week % 2 == (1 if match[3] == "单" else 0):
                weeks.add(week)
    return sorted(weeks)


def parse_course_cell(text: str) -> list[dict]:
    """Keep each course and its week/room pairing, including truncated courses."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    starts = [i for i, line in enumerate(lines) if COURSE_PATTERN.fullmatch(line)]
    if not starts or starts[0] != 0:
        raise ValueError(f"单元格缺少课程标题：{text}")
    records = []
    for start, end in zip(starts, starts[1:] + [len(lines)]):
        block = lines[start:end]
        raw = "\n".join(block)
        truncated = is_truncated(raw)
        head = COURSE_PATTERN.fullmatch(block[0])
        credits = CREDITS_PATTERN.fullmatch(head["tail"])
        if credits is None and not is_truncated(head["tail"]):
            raise ValueError(f"无法识别课程学分：{block[0]}")
        sessions = defaultdict(list)
        student_count = None
        class_lines = []
        for line in block[1:]:
            session = SESSION_PATTERN.fullmatch(line)
            count = COUNT_PATTERN.fullmatch(line)
            if session and student_count is None:
                week_text, teaching_type, room = session.groups()
                parse_weeks(week_text)
                # An ellipsis is missing source information, never a classroom.
                room = room.rstrip(".…").strip()
                sessions[(teaching_type, room)].append(week_text)
            elif count and student_count is None:
                student_count = int(count[1])
            elif student_count is not None:
                class_lines.append(line)
            else:
                raise ValueError(f"无法识别课程内容：{line}")
        if not truncated and (not sessions or student_count is None):
            raise ValueError(f"课程信息不完整：{raw}")
        if not sessions:
            sessions[("", "")] = []
        for (teaching_type, room), week_texts in sessions.items():
            records.append(
                {
                    "course": head["course"].strip(),
                    "course_code": head["code"],
                    "credits": float(credits[1]) if credits else None,
                    "week_text": "、".join(dict.fromkeys(week_texts)),
                    "weeks": sorted({week for value in week_texts for week in parse_weeks(value)}),
                    "teaching_type": teaching_type,
                    "classroom": room,
                    "class_group": "\n".join(class_lines),
                    "student_count": student_count,
                    "source_truncated": truncated,
                    "raw": raw,
                }
            )
    return records


def is_physical_education(course: str) -> bool:
    return bool(PHYSICAL_EDUCATION_PATTERN.search(course))


def parse_teacher_timetable(path: Path, expected_term: str) -> tuple[list[dict], dict]:
    document = Document(path)
    records = []
    teachers = []
    teacher = None
    period_times = {}
    source_cells = 0
    occupied_period_cells = 0
    printed_at = ""
    for element in document.element.body:
        if element.tag.endswith("}p"):
            text = Paragraph(element, document).text
            match = TITLE_PATTERN.search(text)
            if match:
                term = f"{match['year']}-{match['semester']}"
                if term != expected_term:
                    raise ValueError(f"课表学期 {term} 与目标学期 {expected_term} 不符")
                if teacher is not None:
                    raise ValueError(f"教师 {teacher} 缺少课表")
                teacher = match["teacher"].strip()
            printed = re.search(r"打印时间[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", text)
            if printed:
                printed_at = printed[1]
        elif element.tag.endswith("}tbl"):
            if teacher is None or teacher in teachers:
                raise ValueError("课表缺少教师标题，或教师重复")
            table = Table(element, document)
            if [cell.text.strip() for cell in table.rows[0].cells] != ["节次/星期", *WEEKDAYS]:
                raise ValueError(f"{teacher} 的课表列格式不符合预期")
            teachers.append(teacher)
            cells = {}
            for expected_period, row in enumerate(table.rows[1:], 1):
                if len(row.cells) != len(WEEKDAYS) + 1:
                    raise ValueError(f"{teacher} 的课表存在异常跨列合并")
                period_match = re.fullmatch(r"第(\d+)节\s*\(([^)]+)\)", row.cells[0].text.strip())
                if not period_match or int(period_match[1]) != expected_period:
                    raise ValueError(f"{teacher} 的节次不连续或格式不符")
                period, time_text = int(period_match[1]), period_match[2]
                if period in period_times and period_times[period] != time_text:
                    raise ValueError(f"第 {period} 节的上课时间不一致")
                period_times[period] = time_text
                for day, cell in zip(WEEKDAYS, row.cells[1:]):
                    if not cell.text.strip():
                        continue
                    occupied_period_cells += 1
                    # python-docx resolves vertical merges to the same XML cell.
                    key = (day, cell._tc)
                    if key not in cells:
                        cells[key] = {"text": cell.text.strip(), "periods": []}
                    cells[key]["periods"].append(period)
            for (day, _xml_cell), cell in cells.items():
                source_cells += 1
                periods = cell["periods"]
                if periods != list(range(periods[0], periods[-1] + 1)):
                    raise ValueError(f"{teacher} 的合并单元格节次不连续")
                for course in parse_course_cell(cell["text"]):
                    records.append(
                        {
                            "term": expected_term,
                            "sheet": f"{path.name} · {teacher}",
                            "source_table": len(teachers),
                            "weekday": day,
                            "start_period": periods[0],
                            "end_period": periods[-1],
                            "teachers": [teacher],
                            "teacher_label": teacher,
                            **course,
                        }
                    )
            teacher = None
    if teacher is not None or not records:
        raise ValueError("课表为空，或有教师缺少课表")
    excluded_count = sum(is_physical_education(rec["course"]) for rec in records)
    records = [rec for rec in records if not is_physical_education(rec["course"])]
    retained_teachers = sorted({teacher for rec in records for teacher in rec["teachers"]})
    records.sort(key=lambda rec: (WEEKDAYS.index(rec["weekday"]), rec["start_period"], rec["teacher_label"], rec["course"], rec["week_text"]))
    metadata = {
        "term": expected_term,
        "source_file": path.name,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_printed_at": printed_at,
        "source_teacher_count": len(teachers),
        "teacher_count": len(retained_teachers),
        "teachers": retained_teachers,
        "record_count": len(records),
        "excluded_physical_education_records": excluded_count,
        "source_course_cells": source_cells,
        "source_occupied_period_cells": occupied_period_cells,
        "truncated_source_cells": len({
            (rec["source_table"], rec["weekday"], rec["start_period"], rec["end_period"])
            for rec in records if rec["source_truncated"]
        }),
        "truncated_records": sum(rec["source_truncated"] for rec in records),
        "records_with_unknown_weeks": sum(not rec["weeks"] for rec in records),
        "period_times": period_times,
    }
    return records, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--term", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    records, metadata = parse_teacher_timetable(args.source, args.term)
    category_path = args.output_dir / "teacher_category_cache.json"
    previous_categories = json.loads(category_path.read_text(encoding="utf-8")) if category_path.exists() else {}
    categories = {teacher: previous_categories.get(teacher, "院内其余老师") for teacher in metadata["teachers"]}
    metadata["category_note"] = "沿用 M06 既有教师分组，新教师暂列院内其余老师。"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in [
        ("schedule_cache.json", records),
        ("schedule_metadata.json", metadata),
        ("teacher_category_cache.json", categories),
    ]:
        (args.output_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in metadata.items() if key not in {"teachers", "period_times"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
