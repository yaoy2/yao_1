"""Recognize official college dispatch PDFs and extract register fields locally."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re

from .models import Decision
from .readers import MAX_FILE_BYTES, normalized


DISPATCH_KIND = "学院发文"
DISPATCH_ARCHIVE = "07_年度工作档案/{year}年/通知发文"
_PREFIX = re.compile(r"^(?:成\s*东\s*软\s*)?健\s*康\s*(?:学\s*)?院\s*发")
_NUMBER = re.compile(_PREFIX.pattern + r"\s*[\[〔【(]\s*(20\d{2})\s*[\]〕】)]\s*0*([1-9]\d*)\s*号")
_DATE = r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
_PRINT_DATE = re.compile(r"健康医疗科技学院\s*" + _DATE + r"\s*印发")
_SIGN_DATE = re.compile(r"^\s*" + _DATE + r"\s*$", re.M)
_BODY_FIELD = re.compile(r"身份证(?:号码|号)?|证件号码|学号\s*[:：]|手机号\s*[:：]|(?<!\d)\d{15,18}[Xx]?(?!\d)")
_FORMAL_END = re.compile(r"的(?:通知|决定|通报|批复|意见)")
_DISCIPLINARY = re.compile(r"(?:处分|记过|开除学籍|留校察看|严重警告).*(?:决定|通知)")


@dataclass(frozen=True)
class Dispatch:
    number: str
    year: str
    title: str
    date: str = ""


def dispatch_number(value: str) -> str:
    match = _NUMBER.match(normalized(value).strip())
    return f"成东软健康院发〔{match[1]}〕{match[2]}号" if match else ""


def is_dispatch_named(value: str) -> bool:
    return bool(_PREFIX.match(normalized(value).strip()))


def _dates(matches) -> set[str]:
    values = set()
    for match in matches:
        try:
            values.add(date(*map(int, match.groups())).isoformat())
        except ValueError:
            continue
    return values


def _filename_title(stem: str) -> str:
    title = _NUMBER.sub("", normalized(stem), count=1).strip(" -_：:")
    return re.sub(r"(?:\s*\(\d+\)|[_-]20\d{6})+$", "", title).strip(" -_")


def _read_metadata(path: Path, name_number: str) -> tuple[Dispatch | None, str]:
    if path.stat().st_size > MAX_FILE_BYTES:
        return None, "文件过大，无法提取版头"
    from pypdf import PdfReader

    with path.open("rb") as stream:
        if not stream.read(1024).lstrip().startswith(b"%PDF-"):
            return None, "文件不是有效的 PDF"
        stream.seek(0)
        reader = PdfReader(stream, strict=False)
        if reader.is_encrypted:
            return None, "PDF 已加密，无法提取版头"
        first = reader.pages[0].extract_text() or ""
        lines = [line.strip() for line in first.splitlines() if line.strip()]
        headers = [(idx, number) for idx, line in enumerate(lines[:10]) if (number := dispatch_number(line))]
        if not headers:
            return None, "PDF 版头未读到学院文号"
        index, number = headers[0]
        if len({value for _, value in headers}) > 1 or (name_number and number != name_number):
            return None, "文件名或正文出现不同文号"
        title_parts = []
        for line in lines[index + 1:index + 7]:
            if re.match(r"签发人\s*[:：]", line):
                continue
            if re.search(r"[:：]$", line) or line.startswith(("一、", "为", "根据")):
                break
            if _BODY_FIELD.search(line):
                end = _FORMAL_END.search(line)
                if end and end.end() <= _BODY_FIELD.search(line).start():
                    title_parts.append(line[:end.end()])
                break
            title_parts.append(line)
            if _FORMAL_END.search(line) and _FORMAL_END.search(line).end() == len(line):
                break
            if sum(map(len, title_parts)) > 150:
                title_parts.clear()
                break
        title = "".join(title_parts) or (_filename_title(path.stem) if name_number else "")
        year = number.split("〔", 1)[1][:4]
        issuance_dates = set()
        for index, page in enumerate(reader.pages):
            content = (page.extract_text() or "") if index else first
            printed = _dates(_PRINT_DATE.finditer(content))
            if printed:
                # Prefer the signed date immediately above the print block when both occur.
                issuance_dates.update(_dates(_SIGN_DATE.finditer(content)) or printed)
        issuance = next(iter(issuance_dates)) if len(issuance_dates) == 1 else ""
        return Dispatch(number, year, title, issuance if issuance.startswith(year) else ""), ""


def classify_dispatch(path: Path) -> Decision:
    stem = path.stem
    number = dispatch_number(stem)
    try:
        payload, limitation = _read_metadata(path, number)
    except Exception:
        payload, limitation = None, "PDF 文字层无法读取"
    if payload is None:
        # A clearly labelled scan can be confirmed individually using the filename.
        if (number and re.fullmatch(r"PDF (?:版头未读到学院文号|文字层无法读取)", limitation)
                and _filename_title(stem)):
            year = number.split("〔", 1)[1][:4]
            payload = Dispatch(number, year, _filename_title(stem))
        elif is_dispatch_named(stem):
            return Decision("review", DISPATCH_KIND, reason=limitation)
        else:
            return Decision("ignored")
    if not payload.title:
        return Decision("review", DISPATCH_KIND, reason="识别到文号，缺少发文标题", document_number=payload.number)
    if _DISCIPLINARY.search(payload.title):
        return Decision("review", DISPATCH_KIND, reason="该文号对应学生处分文件，请核对其与学院发文登记范围是否一致",
                        document_number=payload.number)
    reason = (f"{limitation}，请核对文件名信息后逐项勾选" if limitation else "已核对 PDF 正式文号")
    if not payload.date:
        reason += "；落款日期待核对"
    target_name = "" if number else payload.number + "-" + re.sub(r'[<>:"/\\|?*]', "_", payload.title) + path.suffix
    return Decision("ready", DISPATCH_KIND, payload.year, relative_dir=DISPATCH_ARCHIVE.format(year=payload.year),
                    reason=reason, target_name=target_name, manual_selection=bool(limitation), document_number=payload.number,
                    document_title=payload.title, document_date=payload.date)
