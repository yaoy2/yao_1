"""Bounded, read-only extraction; never invokes Office, macros, or remote links."""

from dataclasses import dataclass
from pathlib import Path
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import ZipFile


MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_XML_BYTES = 24 * 1024 * 1024
MAX_CELLS = 100_000
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub("[‐‑‒–—−－]", "-", text).replace("\u3000", " ")


def col_number(address: str) -> int:
    number = 0
    for letter in re.match(r"[A-Z]+", address).group():
        number = number * 26 + ord(letter) - 64
    return number


def row_number(address: str) -> int:
    return int(re.search(r"\d+$", address).group())


@dataclass
class Sheet:
    name: str
    cells: dict[str, str]
    hidden: bool = False
    merged_ranges: tuple[str, ...] = ()

    def header_cells(self) -> dict[str, str]:
        return {address: text for address, text in self.cells.items() if row_number(address) <= 5}


def _xml(archive: ZipFile, member: str) -> ET.Element:
    info = archive.getinfo(member)
    if info.file_size > MAX_XML_BYTES:
        raise ValueError("文档内部内容过大，保留原处待核对")
    return ET.fromstring(archive.read(member))


def read_workbook(path: Path) -> list[Sheet]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("文件超过100 MiB，保留原处待核对")
    with ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(node.itertext()) for node in _xml(archive, "xl/sharedStrings.xml").findall(S + "si")]
        relationships = {}
        for node in _xml(archive, "xl/_rels/workbook.xml.rels"):
            if node.get("TargetMode") == "External":
                continue
            target = node.get("Target", "")
            member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if not member.startswith("xl/") or ".." in member.split("/"):
                raise ValueError("工作表路径异常")
            relationships[node.get("Id")] = member
        sheets = []
        for node in _xml(archive, "xl/workbook.xml").findall(S + "sheets/" + S + "sheet"):
            member = relationships.get(node.get(R + "id"))
            if not member:
                continue
            cells = {}
            document = _xml(archive, member)
            for cell in document.iter(S + "c"):
                address = cell.get("r", "")
                if not re.fullmatch(r"[A-Z]+[1-9]\d*", address):
                    continue
                kind = cell.get("t", "")
                raw = cell.findtext(S + "v", default="")
                if kind == "s":
                    value = shared[int(raw)] if raw else ""
                elif kind == "inlineStr":
                    value = "".join(n.text or "" for n in cell.iter(S + "t"))
                else:
                    value = raw
                if value.strip():
                    cells[address] = normalized(value).strip()
                if len(cells) > MAX_CELLS:
                    raise ValueError("工作表内容过多，保留原处待核对")
            merged_ranges = tuple(
                cell.get("ref", "") for cell in document.findall(S + "mergeCells/" + S + "mergeCell")
                if re.fullmatch(r"[A-Z]+[1-9]\d*:[A-Z]+[1-9]\d*", cell.get("ref", ""))
            )
            sheets.append(Sheet(node.get("name", ""), cells, node.get("state", "visible") != "visible", merged_ranges))
        return sheets


def read_document_text(path: Path) -> tuple[str, str]:
    """Return text and a short limitation. A missing reader never guesses metadata."""
    if path.stat().st_size > MAX_FILE_BYTES:
        return "", "文件超过100 MiB，未提取正文"
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            with ZipFile(path) as archive:
                document = _xml(archive, "word/document.xml")
                paragraphs = ["".join(n.text or "" for n in p.iter(W + "t")) for p in document.iter(W + "p")]
            return "\n".join(paragraphs)[:20_000], ""
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                return "", "当前程序缺少PDF文字读取组件"
            reader = PdfReader(path, strict=False)
            if reader.is_encrypted:
                return "", "PDF已加密，未读取正文"
            text = "\n".join(page.extract_text() or "" for page in reader.pages[:2])[:20_000]
            return text, "" if text.strip() else "扫描PDF未提取到文字"
        if suffix == ".xlsx":
            sheets = read_workbook(path)
            text = "\n".join(text for sheet in sheets if not sheet.hidden for text in sheet.header_cells().values())
            return text[:20_000], ""
        if suffix in {".doc", ".xls"}:
            return "", "旧版Office文件仅按完整文件名判断，缺少信息时请另存为docx/xlsx"
        return "", "不支持读取此类型正文"
    except Exception as exc:
        return "", f"无法读取正文（{type(exc).__name__}），未改动原文件"
