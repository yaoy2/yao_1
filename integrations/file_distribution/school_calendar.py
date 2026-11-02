"""Approved school-calendar dates; never infer a term from the computer clock."""

from datetime import date, timedelta
import re


CALENDAR_PERIOD = "2026-2027-1"
CALENDAR_SOURCE = "成都东软学院2026-2027年度第1学期校历.pdf"
TERM_START = date(2026, 9, 14)
TERM_END = date(2027, 1, 15)  # User-confirmed filing boundary, inclusive.
CALENDAR_LABEL = "2026-2027-1（2026/09/14—2027/01/15）"
WEEK_RANGES = {
    f"第{number}周": (TERM_START + timedelta(weeks=number - 1), TERM_START + timedelta(weeks=number, days=-1))
    for number in range(1, 17)
}
WEEK_RANGES.update({"考试周": (date(2027, 1, 4), date(2027, 1, 10)),
                    "总结周": (date(2027, 1, 11), TERM_END)})
_NUM = r"[0-9一二三四五六七八九十百零〇两]+"
WEEK_PATTERN = re.compile(
    rf"准备周|(?:期末)?考试周|(?:教师)?总结周|(?:教学|小学期)?第?\s*({_NUM})\s*"
    rf"(?:周\s*)?(?:([-~～至到、])\s*第?\s*({_NUM})\s*)?周"
)
_FULL_DATE = re.compile(r"(?<!\d)(20\d{2})(?:年|[-_/.])(\d{1,2})(?:月|[-_/.])(\d{1,2})(?:日|号)?(?!\d)")
_COMPACT_DATE = re.compile(r"(?<!\d)(20\d{2})([01]\d)([0-3]\d)(?!\d)")
_SHORT_DATE = re.compile(r"(?<!\d)(\d{1,2})(?:月|[-_/.])(\d{1,2})(?:日|号)?(?!\d)")
_ACADEMIC_PERIOD = re.compile(r"(?<!\d)(?:20\d{2}[-_/]20\d{2}|2\d[-_/]2\d)(?:学年(?:度)?)?(?:[-_/][123](?!\d))?")
_CLOCK = re.compile(r"(?<!\d)\d{1,2}\s*[:：]\s*\d{2}(?:\s*[:：]\s*\d{2})?(?!\d)")


def week_for_date(value: date) -> str:
    return next((label for label, (start, end) in WEEK_RANGES.items() if start <= value <= end), "")


def is_date_heading(line: str) -> bool:
    """Recognize a standalone header date, including dates in a separate table cell."""
    value = re.sub(r"\s+", "", _CLOCK.sub(" ", line))
    value = re.sub(r"(?:星期|周)[一二三四五六日天]", "", value)
    found = False
    for pattern in (_FULL_DATE, _COMPACT_DATE, _SHORT_DATE):
        found = found or bool(pattern.search(value))
        value = pattern.sub("", value)
    return found and not re.sub(r"[-~～至到、()（）]", "", value)


def _number(text: str) -> int:
    if text.isdigit():
        return int(text)
    digits = dict(zip("零〇一二三四五六七八九两", (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 2)))
    if "十" in text and text.count("十") == 1:
        left, right = text.split("十")
        if (not left or left in digits) and (not right or right in digits):
            return digits.get(left, 1) * 10 + digits.get(right, 0)
    return digits.get(text, -1)


def _date_evidence(evidence: list[str]) -> tuple[list[date], list[tuple[int, int]], str]:
    full, short = [], []
    for line in evidence:
        # Remove clock times before compacting whitespace; 14:30-15:30 is not a month/day.
        value = _CLOCK.sub(" ", line)
        value = re.sub(r"\s+", "", value)
        for pattern in (_FULL_DATE, _COMPACT_DATE):
            for match in pattern.finditer(value):
                try:
                    full.append(date(*map(int, match.groups())))
                except ValueError:
                    return [], [], f"材料日期无效：{match.group()}"
            value = pattern.sub(lambda match: " " * len(match.group()), value)
        # Mask academic-year pairs only after complete dates have been extracted.
        # A short pair such as 10-11 remains a month/day, never an academic year.
        value = _ACADEMIC_PERIOD.sub(lambda match: " " * len(match.group()), value)
        value = WEEK_PATTERN.sub(" ", value)
        for match in _SHORT_DATE.finditer(value):
            month, day = map(int, match.groups())
            try:
                date(2000, month, day)
            except ValueError:
                return [], [], f"材料月日无效：{match.group()}"
            short.append((month, day))
    return full, short, ""


def _week_evidence(evidence: list[str], *, max_week: int = 16) -> tuple[list[set[str]], str]:
    groups = []
    for line in evidence:
        value = _ACADEMIC_PERIOD.sub(" ", line)
        for match in WEEK_PATTERN.finditer(value):
            if match.group(1) is None:
                label = match.group().replace("期末", "").replace("教师", "")
                groups.append({label})
                continue
            start = _number(match.group(1))
            end = _number(match.group(3)) if match.group(3) else start
            if not (1 <= start <= end <= max_week):
                note = "校历仅编号第1—16周，之后为考试周、总结周" if max_week == 16 else "材料周次无效"
                return [], f"{note}；请核对“{match.group()}”"
            numbers = (start, end) if match.group(2) == "、" else range(start, end + 1)
            groups.append({f"第{number}周" for number in numbers})
    return groups, ""


def naming_week_label(evidence: list[str], period: str) -> str:
    """Called after calendar validation; retain the full explicit multi-week range."""
    groups, error = _week_evidence(evidence, max_week=16 if period == CALENDAR_PERIOD else 60)
    if error or len({frozenset(group) for group in groups}) > 1:
        return ""
    weeks = set().union(*groups) if groups else set()
    if not weeks and period == CALENDAR_PERIOD:
        full, short, error = _date_evidence(evidence)
        if error:
            return ""
        for month, day in short:
            for year in (2026, 2027):
                try:
                    value = date(year, month, day)
                except ValueError:
                    continue
                if TERM_START <= value <= TERM_END:
                    full.append(value)
        weeks = {week_for_date(value) for value in full}
    if not weeks or "" in weeks:
        return ""
    if len(weeks) == 1:
        return next(iter(weeks))
    if not all(re.fullmatch(r"第\d+周", label) for label in weeks):
        return ""
    numbers = sorted(int(label[1:-1]) for label in weeks)
    value = (f"{numbers[0]}—{numbers[-1]}" if numbers == list(range(numbers[0], numbers[-1] + 1))
             else "、".join(map(str, numbers)))
    return f"第{value}周"


def resolve_calendar(evidence: list[str], explicit_period: str, *,
                     calendar_period: str = CALENDAR_PERIOD) -> tuple[str, str, str]:
    """Return period, explanation, error; partial dates/weeks require a batch context."""
    if calendar_period not in ("", CALENDAR_PERIOD):
        return "", "", "尚未配置该学期校历"
    full_dates, short_dates, error = _date_evidence(evidence)
    if error:
        return "", "", error
    matching_dates = [value for value in full_dates if TERM_START <= value <= TERM_END]
    if explicit_period and explicit_period != CALENDAR_PERIOD:
        if matching_dates:
            return "", "", f"材料日期属于{CALENDAR_PERIOD}，与注明的{explicit_period}学期冲突"
        # Other explicitly stated terms keep their routes; this calendar cannot check their weeks.
        return explicit_period, "", ""
    context = explicit_period == CALENDAR_PERIOD or calendar_period == CALENDAR_PERIOD or bool(matching_dates)
    if full_dates and (matching_dates or explicit_period == CALENDAR_PERIOD) and len(matching_dates) != len(full_dates):
        return "", "", "材料日期超出已确认学期范围（2026-09-14至2027-01-15），请核对"
    if full_dates and not matching_dates and not explicit_period:
        return "", "", "材料日期不在已配置校历范围内，不能仅凭周次套入本学期"
    if not context:
        return explicit_period, "", "" if explicit_period else "缺少明确学期；仅有周次或月日时需指定本批校历"
    dates = list(full_dates)
    for month, day in short_dates:
        candidates = []
        for year in (2026, 2027):
            try:
                value = date(year, month, day)
            except ValueError:
                continue
            if TERM_START <= value <= TERM_END:
                candidates.append(value)
        if len(candidates) != 1:
            return "", "", f"月日{month}月{day}日不在本批校历范围内，请核对年份和学期"
        dates.extend(candidates)
    groups, error = _week_evidence(evidence)
    if error:
        return "", "", error
    weeks = set().union(*groups) if groups else set()
    if weeks - WEEK_RANGES.keys():
        return "", "", "准备周不在本批已确认归档日期范围内，请核对学期"
    if not explicit_period and not full_dates:
        named_years = {int(year) for line in evidence
                       for year in re.findall(r"(?<!\d)(20\d{2})年", _ACADEMIC_PERIOD.sub(" ", line))}
        inferred_years = {value.year for value in dates} or {
            endpoint.year for label in weeks for endpoint in WEEK_RANGES[label]
        }
        if named_years and not named_years.issubset(inferred_years):
            return "", "", "注明的年份与本批校历对应日期不一致，请核对年份和学期"
    date_weeks = {week_for_date(value) for value in dates}
    if len({frozenset(group) for group in groups}) > 1:
        actual = "、".join(label for label in WEEK_RANGES if label in date_weeks)
        return "", "", "文件名和正文题头的周次信息冲突" + (f"；按校历日期对应{actual}，请核对" if actual else "，请核对")
    if len(date_weeks) > 1 and not weeks:
        return "", "", "材料日期跨多个校历周，且未注明跨周范围，请核对日期"
    if weeks and date_weeks - weeks:
        actual = "、".join(label for label in WEEK_RANGES if label in date_weeks)
        return "", "", f"材料日期与标注周次冲突；按校历日期对应{actual}，请核对"
    if not explicit_period and not dates and not weeks:
        return "", "", "缺少明确学期、材料日期或周次，不能仅凭当前时间归档"
    used_weeks = date_weeks or weeks
    labels = "、".join(label for label in WEEK_RANGES if label in used_weeks)
    if dates:
        date_text = "、".join(value.isoformat() for value in sorted(set(dates)))
        reason = f"按校历核对材料日期{date_text}（{labels}）"
    elif weeks:
        reason = f"按校历核对周次：{labels}" if explicit_period else f"按本批校历{CALENDAR_PERIOD}补全学期；{labels}"
    else:
        reason = "学期明确；未提供可核对的日期或周次"
    return CALENDAR_PERIOD, reason, ""
