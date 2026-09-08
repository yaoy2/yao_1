"""Bounded, memory-only attachment text for review; never saves attachment bytes."""

from __future__ import annotations

import importlib
from io import BytesIO
from pathlib import PurePosixPath
import zipfile
from xml.etree import ElementTree

MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_PART_BYTES = 10 * 1024 * 1024
MAX_TEXT = 12000
MAX_PDF_PAGES = 60
MAX_ROWS, MAX_COLUMNS, MAX_SHEETS = 300, 40, 10
_TYPES = {"application/pdf": ".pdf", "text/plain": ".txt", "text/csv": ".csv",
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx"}


class _Unavailable(Exception):
    pass


def _zip_checked(data):
    archive = zipfile.ZipFile(BytesIO(data))
    entries = archive.infolist()
    if (len(entries) > 2000 or sum(entry.file_size for entry in entries) > MAX_ZIP_BYTES
            or any(entry.file_size > MAX_PART_BYTES for entry in entries)):
        archive.close()
        raise _Unavailable("附件解压内容超过读取上限")
    if any(entry.flag_bits & 1 for entry in entries):
        archive.close()
        raise _Unavailable("附件已加密，未解析")
    return archive


def _pdf(data):
    try:
        reader = importlib.import_module("pypdf").PdfReader(BytesIO(data), strict=True)
    except ImportError:
        raise _Unavailable("本机缺少PDF解析组件") from None
    if reader.is_encrypted and not reader.decrypt(""):
        raise _Unavailable("附件已加密，未解析")
    total, parts, count, failed = len(reader.pages), [], 0, False
    limited = total > MAX_PDF_PAGES
    for index in range(min(total, MAX_PDF_PAGES)):
        try:
            text = reader.pages[index].extract_text() or ""
        except Exception:
            failed = True
            continue
        count += len(text) + bool(parts)
        parts.append(text)
        if count > MAX_TEXT:
            limited = True
            break
    return "\n".join(parts), limited, failed


def _docx(data):
    with _zip_checked(data) as archive:
        xml = archive.read("word/document.xml")
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise _Unavailable("附件结构不安全，未解析")
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    document, parts, count = ElementTree.fromstring(xml), [], 0
    for paragraph in document.iter(namespace + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(namespace + "t"))
        count += len(text) + bool(parts)
        parts.append(text)
        if count > MAX_TEXT:
            return "\n".join(parts), True, False
    return "\n".join(parts), False, False


def _xlsx(data):
    with _zip_checked(data):
        pass
    try:
        module = importlib.import_module("openpyxl")
    except ImportError:
        raise _Unavailable("本机缺少Excel解析组件") from None
    workbook = module.load_workbook(BytesIO(data), read_only=True, data_only=True, keep_links=False)
    parts, count, limited = [], 0, len(workbook.worksheets) > MAX_SHEETS
    try:
        for sheet in workbook.worksheets[:MAX_SHEETS]:
            limited |= (sheet.max_row is None or sheet.max_column is None
                        or sheet.max_row > MAX_ROWS or sheet.max_column > MAX_COLUMNS)
            header_pending = True
            for row in sheet.iter_rows(max_row=MAX_ROWS, max_col=MAX_COLUMNS, values_only=True):
                if not any(value is not None for value in row):
                    continue
                if header_pending:
                    header = "[" + sheet.title + "]"
                    count += len(header) + bool(parts)
                    parts.append(header)
                    header_pending = False
                text = "\t".join("" if value is None else str(value) for value in row).rstrip()
                count += len(text) + bool(parts)
                parts.append(text)
                if count > MAX_TEXT:
                    return "\n".join(parts), True, False
        return "\n".join(parts), limited, False
    finally:
        workbook.close()


def _plain(data):
    encodings = ["utf-16"] if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ["utf-8-sig", "gb18030"]
    for encoding in encodings:
        try:
            return data.decode(encoding), False, False
        except UnicodeError:
            pass
    raise _Unavailable("附件文字编码无法识别")


def extract_attachment_reviews(attachments):
    """Return safe status metadata and bounded text, using no disk/network IO."""
    reviews = []
    for attachment in attachments:
        item = {"id": attachment.get("id", ""), "name": attachment.get("name", "附件"),
                "text": "", "status": "unavailable", "reason": "", "truncated": False}
        try:
            data = attachment.get("data")
            if not isinstance(data, bytes) or not data:
                raise _Unavailable("附件为空或未取得内容")
            if len(data) > MAX_ATTACHMENT_BYTES:
                raise _Unavailable("附件超过15MiB读取上限")
            suffix = PurePosixPath(str(item["name"]).replace("\\", "/")).suffix.lower()
            if suffix in {".zip", ".rar", ".7z"}:
                raise _Unavailable("暂不支持此附件格式")
            if suffix not in {".pdf", ".docx", ".xlsx", ".txt", ".csv"}:
                suffix = _TYPES.get(attachment.get("content_type"), suffix)
            parser = {".pdf": _pdf, ".docx": _docx, ".xlsx": _xlsx, ".txt": _plain, ".csv": _plain}.get(suffix)
            if parser is None:
                raise _Unavailable("暂不支持此附件格式")
            text, limited, failed = parser(data)
            limited |= len(text) > MAX_TEXT
            item.update(text=text[:MAX_TEXT], truncated=limited)
            if limited:
                item.update(status="partial", reason="附件读取范围受限，已截断或无法确认完整性")
            elif failed:
                item.update(status="partial" if text.strip() else "unavailable", reason="部分内容无法解析")
            elif text.strip():
                item.update(status="read", reason="已提取可用文本")
            else:
                item["reason"] = "未取得可提取文本，可能为扫描件或空白附件"
        except _Unavailable as exc:
            item["reason"] = str(exc)
        except Exception:
            item["reason"] = "附件解析失败，内容未完整读取"
        reviews.append(item)
    return reviews
