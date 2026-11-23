"""Recognize college articles by their titles, openings and accompanying photos."""

from pathlib import Path
import re

from .models import Decision
from .readers import normalized, read_document_text
from .school_calendar import CALENDAR_PERIOD


NEWS_DIRECTORY = f"{CALENDAR_PERIOD}-新闻"
WORD_EXTENSIONS = {".doc", ".docx"}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
_ARCHIVE = re.compile(r"^\d{2}_|^\d{4}-\d{4}-[123].*新闻|^(?:新闻word|品牌新闻|月报)$", re.I)
_MARKER = re.compile(r"新闻[稿报道]|新闻报导|通讯稿|喜报|教师风采|学生风采|斩获佳绩|取得佳绩|荣获|获评")
_UNIT = re.compile(r"学院|[我本]院|我校|健服系|医学.{1,6}系|健康.{1,6}[系部]|师生|代表队|教职工")
_EVENT = re.compile(r"开展|召开|举行|举办|组织|参加|出席|受邀|走进|走访|赴|夺得|收获|获.{0,18}奖|进行时|现场选拔|接受专项指导")
_LEAD = re.compile(r"近日|日前|当天|当日|活动现场|在此期间|(?:\d{4}\s*年\s*)?\d{1,2}\s*月\s*\d{1,2}\s*[日号]|20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}")
_RECORD = re.compile(r"会议纪要|例会纪要|会议记录|考勤[表记录明细情况统计]|签到[表册]|签到记录|出勤[表记录]|月报")
_FORM = re.compile(
    r"模板|范本|样例|示例|会议议程|活动议程|报销|发票|合同|审批(?:表|单)?|申报(?:书|表)|"
    r"申请(?:书|表)|报价单|报名表|统计表|汇总表|人员名单|材料清单|工作总结|工作计划|"
    r"^(?:关于.{1,100}(?:通知|公示)|通知|公示)|(?:通知|公示|实施方案|活动方案|策划书|申请书|汇报材料|主持词|发言稿|讲话稿)$"
)
_RECORD_FIELD = re.compile(r"^(会议时间|会议地点|主持人|记录人|参会人员|出席人员|应到|实到|缺席)\s*:")
_DRAFT_NOTICE = re.compile(r"^(?:各(?:位|系部|部门|单位|老师|班级)|全体(?:师生|教师|教职工)).{0,40}:")
_COPY_SUFFIX = re.compile(r"\s*\(\d+\)$")


def is_news_word(path: Path) -> bool:
    return not path.name.startswith((".", "~$")) and path.suffix.lower() in WORD_EXTENSIONS


def is_news_directory_name(name: str) -> bool:
    return not name.startswith((".", "~$")) and not _ARCHIVE.search(normalized(name))


def is_record_name(name: str) -> bool:
    return bool(_RECORD.search(normalized(name)))


def _title(value: str) -> str:
    return _COPY_SUFFIX.sub("", normalized(value).strip())


def _headline(value: str) -> bool:
    return bool(_MARKER.search(value) or (_UNIT.search(value) and _EVENT.search(value)))


def _document(path: Path) -> tuple[bool, bool, bool]:
    """Return whether it is another material, has article evidence, or has a possible headline."""
    name = _title(path.stem)
    if is_record_name(name) or _FORM.search(name) or name.endswith(("考勤", "签到")):
        return True, False, False
    text, _ = read_document_text(path)
    lines = [value for line in text.splitlines() if (value := _title(line))][:12]
    # A title can wrap over several paragraphs. Limit exclusions to title-like lines and form fields.
    titles = [line for line in lines[:3] if len(line) <= 110 and not re.search(r"[。；;]", line) and not _LEAD.match(line)]
    fields = {match[1] for line in lines if (match := _RECORD_FIELD.match(line))}
    if (any(is_record_name(line) or _FORM.search(line) or line.endswith(("考勤", "签到")) for line in titles)
            or len(fields) >= 2 or any(_DRAFT_NOTICE.match(line) for line in lines[:3])):
        return True, False, False
    headline = _headline(name) or _headline("".join(titles))
    opening = [line for line in lines[:6] if re.search(r"[，,。]", line) and _LEAD.search(line)]
    narrative = any(_EVENT.search(line) and (_UNIT.search(line) or headline) for line in opening)
    explicit = bool(_MARKER.search(name) or any(_MARKER.search(line) for line in titles))
    return False, explicit or narrative, headline or bool(opening and _EVENT.search("".join(opening)))


def _news(reason: str, *, manual: bool = False) -> Decision:
    return Decision("ready", "学院新闻", CALENDAR_PERIOD, relative_dir=NEWS_DIRECTORY,
                    reason=reason, manual_selection=manual)


def classify_news_file(path: Path) -> Decision:
    excluded, evidence, headline = _document(path)
    if not excluded:
        if evidence:
            return _news("稿名、标题或正文导语具有新闻特征；保留 Word 原名")
        if headline:
            return _news("标题像新闻，正文线索不足；确认后可单独勾选", manual=True)
    return Decision("ignored")


def classify_news_folder(path: Path, files: list[Path]) -> Decision:
    words = [file for file in files if is_news_word(file)]
    if not words:
        return Decision("ignored")
    name = _title(path.name)
    photos = sum(file.suffix.lower() in PHOTO_EXTENSIONS for file in files)
    documents = [_document(word) for word in words]
    plausible = _headline(name) or photos or any(evidence or headline for _, evidence, headline in documents)
    if not plausible:
        return Decision("ignored")
    if (is_record_name(name) or _FORM.search(name) or name.endswith(("考勤", "签到"))
            or any(excluded for excluded, _, _ in documents)
            or any(is_record_name(file.stem) or _FORM.search(_title(file.stem)) for file in files)):
        if all(excluded for excluded, _, _ in documents):
            return Decision("ignored")
        return Decision("review", "学院新闻", reason="文件夹混有纪要、考勤、通知或其他业务材料；请分开后重新预览")
    attachments = [file for file in files if file not in words and file.suffix.lower() not in PHOTO_EXTENSIONS
                   and file.name.casefold() not in {"thumbs.db", "desktop.ini", ".ds_store"}]
    composition = f"{len(words)} 份 Word、{photos} 张照片"
    if not attachments and (any(evidence for _, evidence, _ in documents)
                            or (photos and (_headline(name) or any(headline for _, _, headline in documents)))):
        return _news(f"新闻文件夹（{composition}）；整包保留原名和内部结构")
    detail = "；另有其他附件" if attachments else ""
    return _news(f"疑似新闻文件夹（{composition}{detail}）；确认后可单独勾选整包归档", manual=True)
