"""Classify department minutes and attendance without reading or moving files."""

import re
import unicodedata

from .models import Decision
from .school_calendar import CALENDAR_PERIOD, WEEK_PATTERN, is_date_heading, naming_week_label, resolve_calendar


_DEPARTMENTS = {
    "医学信息工程系": ("医学信息工程系",),
    "医学影像系": ("医学影像系",),
    "健康服务与管理系": ("健康服务与管理系", "健服系"),
    "健康体育部": ("健康体育部",),
}
_EXTENSIONS = {".doc", ".docx", ".pdf", ".xls", ".xlsx"}
_PARTY_FILENAME = re.compile(
    r"^健康(?:医疗科技)?学院党政联席会会议纪要[-_ ]+健康(?:医疗科技)?学院"
    r"20\d{2}-20\d{2}学年(?:度)?第[一二三123]学期(?:教学|小学期)?"
    r"第[0-9一二三四五六七八九十百零〇两]+周(?:\s*\(\d+\))?\.pdf$", re.I,
)
_TEMPLATE = re.compile(r"模板|范本|样例|示例")
_OTHER_BUSINESS = re.compile(
    r"通知|会议议程|新闻稿|新闻报道|新闻报导|通讯稿|喜报|月报|"
    r"制度|办法|规定|要求|汇报材料|考勤安排"
)
_OTHER_UNITS = re.compile(r"党政联席会|业务线会议|管理中心|学工(?:部|办)?|产业园")
_OTHER_MEETINGS = re.compile(r"党政联席会|校党委|学校党委|党总支|党支部|支委会|委员会|校长办公会")
_MINUTES = re.compile(
    r"会议纪要|例会纪要|系部例会|周工作例会|"
    r"第?[0-9一二三四五六七八九十百零〇两]+周(?:工作)?例会"
)
_YEAR_RANGE = (
    r"(?<!\d)(?P<start>\d{4}|\d{2})\s*(?:[-_/]|至|到)\s*"
    r"(?P<end>\d{4}|\d{2})(?!\d)"
)
_YEARS = re.compile(_YEAR_RANGE)
_FULL_PERIOD = re.compile(
    _YEAR_RANGE + r"\s*(?:学年(?:度)?)?\s*(?:"
    r"[-_/]\s*(?P<number>[123])(?!\d)|"
    r"[-_/]?\s*第?\s*(?P<term>[一二三123])\s*学期|(?P<small>小学期))"
)
_BARE_TERM = re.compile(r"第?\s*([一二三123])\s*学期|小学期")
_TERM_FIELD = re.compile(r"^学期\s*[:：]\s*第?\s*([一二三123])(?:\s*学期)?\s*$")
_TERM_NUMBERS = {"一": 1, "二": 2, "三": 3, "1": 1, "2": 2, "3": 3}
_BODY_START = re.compile(
    r"^(?:[一二三四五六七八九十]+[、.]|\d+[、.]|[（(][一二三四五六七八九十\d]+[）)]|"
    r"会议内容|会议主要内容|主要内容|纪要内容|讨论内容|工作要点|会议事项|"
    r"出席人员|参会人员|列席人员|缺席人员|考勤明细|附件|本周工作|下周工作)"
)
_NARRATIVE = re.compile(
    r"下(?:一|个)?学期|下(?:一|个)?学年|未来|拟|计划|讨论|布置|传达|对接|"
    r"邀请|参加|协同|配合|协作|介绍|涉及|建议|要求|提醒|部署|安排|研究|"
    r"听取|汇报|完成|推进|筹备|改进"
)
_HEADER_FIELD = re.compile(
    r"^(?:学年(?:学期)?|学期|部门|系部|单位|会议名称|材料名称|"
    r"标题|会议时间|会议日期|考勤时间|考勤日期|日期|时间|周次)\s*[:：]"
)
_IRRELEVANT_FIELD = re.compile(
    r"^(?:会议地点|地点|会议主持|主持人|主持|记录人|记录|参会|出席|列席|"
    r"应到|实到|缺席|签字|签名|制表人|填表人|会议主题|会议议题)"
)
_WEEK = WEEK_PATTERN


def _normalize(value: str) -> str:
    return re.sub(r"[‐‑‒–—−]", "-", unicodedata.normalize("NFKC", value or ""))


def _departments(value: str) -> set[str]:
    return {
        name for name, aliases in _DEPARTMENTS.items()
        if any(alias in value for alias in aliases)
    }


def _kinds(value: str) -> set[str]:
    result = set()
    if _MINUTES.search(value):
        result.add("会议纪要")
    if "考勤" in value:
        result.add("考勤记录")
    return result


def _metadata_title(value: str) -> bool:
    """A bare year/department line must not merely mention either in a sentence."""
    remaining = value
    for aliases in _DEPARTMENTS.values():
        for alias in aliases:
            remaining = remaining.replace(alias, "")
    remaining = re.sub(r"健康医疗科技学院|健康学院", "", remaining)
    remaining = _FULL_PERIOD.sub("", remaining)
    remaining = _YEARS.sub("", remaining)
    remaining = _BARE_TERM.sub("", remaining)
    remaining = _WEEK.sub("", remaining)
    remaining = re.sub(r"学年(?:度)?|教学", "", remaining)
    remaining = re.sub(r"[\s:：,，、()（）\[\]【】_\-]+", "", remaining)
    return not remaining and bool(_departments(value) or _YEARS.search(value) or _BARE_TERM.search(value))


def _heading_lines(text: str) -> list[str]:
    """Use title/metadata lines, never general discussion or participant lists."""
    result = []
    lines = [line.strip(" \t#|\ufeff") for line in _normalize(text).splitlines()]
    lines = [line for line in lines if line][:16]
    for index, line in enumerate(lines):
        if _BODY_START.match(line):
            break
        if len(line) > 180 or _IRRELEVANT_FIELD.match(line) or _NARRATIVE.search(line):
            continue
        if _HEADER_FIELD.match(line):
            result.append(line)
        elif index < 6 and not re.search(r"[。;；]", line) and (_kinds(line) or _metadata_title(line) or is_date_heading(line)):
            result.append(line)
    return result


def _academic_year(match: re.Match) -> tuple[int, int] | None:
    start_text, end_text = match.group("start", "end")
    start = int(start_text) + (2000 if len(start_text) == 2 else 0)
    end = int(end_text)
    if len(end_text) == 2:
        end += start // 100 * 100
        if end < start:
            end += 100
    return (start, end) if end == start + 1 else None


def _is_year_candidate(value: str, match: re.Match) -> bool:
    """Short years need an academic label or the complete 26-27-1 format."""
    if len(match.group("start")) == len(match.group("end")) == 4:
        return True
    before, after = value[:match.start()], value[match.end():]
    if re.match(r"\s*学年(?:度)?", after) or re.search(r"学年(?:度|学期)?\s*[:：]?\s*$", before):
        return True
    # A date such as 2026-10-28 must never supply or invalidate an academic year.
    return bool(re.match(r"\s*[-_/]\s*[123](?!\d)", after) and _academic_year(match))


def _period(evidence: list[str], calendar_period: str) -> tuple[str, str, str]:
    years = set()
    terms = set()
    invalid_year = False
    for value in evidence:
        for match in _YEARS.finditer(value):
            if not _is_year_candidate(value, match):
                continue
            year = _academic_year(match)
            if year:
                years.add(year)
            else:
                invalid_year = True
        for match in _FULL_PERIOD.finditer(value):
            if _academic_year(match):
                terms.add(3 if match.group("small") else _TERM_NUMBERS[match.group("number") or match.group("term")])
        for match in _BARE_TERM.finditer(value):
            terms.add(_TERM_NUMBERS[match.group(1)] if match.group(1) else 3)
        field = _TERM_FIELD.match(value)
        if field:
            terms.add(_TERM_NUMBERS[field.group(1)])
    if invalid_year:
        return "", "", "学年起止年份不连续，请核对"
    if len(years) > 1 or len(terms) > 1:
        return "", "", "文件名或正文题头中的学年、学期信息冲突"
    explicit = ""
    if years and terms:
        start, end = next(iter(years))
        explicit = f"{start}-{end}-{next(iter(terms))}"
    elif (years and years != {(2026, 2027)}) or (terms and terms != {1}):
        return "", "", "学年或学期未写完整，且与本批已配置校历不符，请核对"
    return resolve_calendar(evidence, explicit, calendar_period=calendar_period)


def classify_weekly(name: str, text: str = "", *, calendar_period: str = CALENDAR_PERIOD) -> Decision:
    """Route department records and the explicitly approved college joint-meeting PDFs."""
    original_filename = re.split(r"[\\/]", name)[-1]
    filename = _normalize(original_filename)
    if filename.startswith("~$"):
        return Decision("skip", reason="Office 临时文件")
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in _EXTENSIONS:
        return Decision("ignored", reason="不属于 Word、PDF 或 Excel 材料")
    title = filename[:-len(extension)]
    headings = _heading_lines(text)
    evidence = [title, *headings]
    if _PARTY_FILENAME.fullmatch(filename):
        return _classify_party(evidence, headings, calendar_period)
    if _TEMPLATE.search(title):
        return Decision("skip", reason="模板或示例，不参与分发")
    if _OTHER_BUSINESS.search(title) or _OTHER_MEETINGS.search(title):
        return Decision("ignored", reason="不属于系部例会纪要或考勤材料")

    name_kinds = _kinds(title)
    header_kinds = set().union(*(_kinds(value) for value in headings)) if headings else set()
    kinds = name_kinds | header_kinds
    if not kinds:
        return Decision("ignored", reason="未识别到系部例会纪要或考勤标记")
    if len(kinds) > 1:
        return Decision("review", reason="同时出现纪要和考勤标题，请核对材料类型")
    kind = next(iter(kinds))
    if any(_TEMPLATE.search(value) for value in headings):
        return Decision("skip", kind=kind, reason="正文题头标明模板或示例")
    if any(_OTHER_BUSINESS.search(value) or _OTHER_MEETINGS.search(value) for value in headings):
        return Decision("ignored", kind=kind, reason="正文题头属于其他会议、通知、新闻或月报等业务")

    departments = set().union(*(_departments(value) for value in evidence))
    outside = any(_OTHER_UNITS.search(value) for value in evidence)
    if not departments and outside:
        return Decision("ignored", kind=kind, reason="不属于三系一部的材料")
    if len(departments) > 1 or (departments and outside):
        return Decision("review", kind=kind, reason="文件名或正文题头涉及多个部门，请核对归属")
    if not departments:
        return Decision("review", kind=kind, reason="无法确定三系一部中的具体部门")
    department = next(iter(departments))
    period, calendar_note, error = _period(evidence, calendar_period)
    if error:
        return Decision("review", kind=kind, department=department, reason=error)
    week_label = naming_week_label(evidence, period)
    if not week_label:
        return Decision("review", kind=kind, period=period, department=department,
                        reason="无法确定统一命名所需的周次或周次信息冲突，请核对；不猜测周次")

    group = "党政联席会_系部例会" if kind == "会议纪要" else "考勤记录"
    relative_dir = f"02_学期工作/{period}/03_会议_考勤/{group}/{department}"
    week = next((match.group() for value in evidence if (match := _WEEK.search(_FULL_PERIOD.sub(" ", value)))), "")
    reason = f"学期、部门和材料类型明确；{week}" if week else "学期、部门和材料类型明确；未识别周次，按部门归档"
    if calendar_note and "材料日期" in calendar_note and not week:
        reason = "部门和材料类型明确"
    if calendar_note:
        reason += "；" + calendar_note
    original_extension = "." + original_filename.rsplit(".", 1)[-1]
    target_name = (f"{department}-会议纪要-{week_label}{original_extension}" if kind == "会议纪要"
                   else f"考勤表-{department}-{week_label}{original_extension}")
    return Decision("ready", kind, period, department, relative_dir, reason,
                    target_name=target_name, week_label=week_label)


def _classify_party(evidence: list[str], headings: list[str], calendar_period: str) -> Decision:
    kind = "学院党政联席会纪要"
    # The exact filename identifies this college's approved PDFs; other meetings stay excluded.
    if any(_TEMPLATE.search(line) or _OTHER_BUSINESS.search(line)
           or re.search(r"校党委|学校党委|党总支|党支部|支委会|委员会|校长办公会|考勤", line)
           or any(department in line and _MINUTES.search(line) for department in _DEPARTMENTS)
           for line in headings):
        return Decision("review", kind=kind, department="健康医疗科技学院", reason="正文题头与学院党政联席会纪要的统一文件名不一致，请核对材料类型")
    period, note, error = _period(evidence, calendar_period)
    if error:
        return Decision("review", kind=kind, department="健康医疗科技学院", reason=error)
    return Decision(
        "ready", kind, period, "健康医疗科技学院",
        f"02_学期工作/{period}/03_会议_考勤/党政联席会_系部例会/党政联席会",
        "学院党政联席会PDF统一命名已匹配；" + note,
    )
