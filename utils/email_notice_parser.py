import re
from html import escape


NOTICE_NUMBER_RE = re.compile(r"^[^\n]{0,12}通知〔\d{4}〕\d+号$")
CHINESE_DATE_RE = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$")
DEFAULT_HEADER = "成都东软学院健康医疗科技学院"


def _clean_lines(raw_text):
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
    return [line.strip() for line in text.split("\n") if line.strip()]


def _to_body_html(body_text):
    lines = [line.strip() for line in str(body_text or "").split("\n") if line.strip()]
    return "\n".join(f"<p>{escape(line)}</p>" for line in lines)


def _pop_date_and_unit(lines):
    date_value = ""
    unit = ""
    if not lines:
        return unit, date_value

    date_match = CHINESE_DATE_RE.match(lines[-1])
    if date_match:
        year, month, day = date_match.groups()
        date_value = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        lines.pop()
        if lines:
            unit = lines.pop()
    return unit, date_value


def parse_notice_text(raw_text):
    lines = _clean_lines(raw_text)
    if not lines:
        return {
            "header": DEFAULT_HEADER,
            "subject": "",
            "number": "",
            "unit": "",
            "date": "",
            "body_text": "",
            "body_html": "",
        }

    working = list(lines)
    unit, date_value = _pop_date_and_unit(working)

    subject = working.pop(0) if working else ""

    number = ""
    for index, line in enumerate(list(working)):
        if NOTICE_NUMBER_RE.match(line):
            number = line
            working.pop(index)
            break

    body_text = "\n".join(working)

    return {
        "header": DEFAULT_HEADER,
        "subject": subject,
        "number": number,
        "unit": unit,
        "date": date_value,
        "body_text": body_text,
        "body_html": _to_body_html(body_text),
    }
