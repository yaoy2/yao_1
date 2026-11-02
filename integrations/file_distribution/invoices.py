"""Recognize invoice documents locally before choosing an existing annual folder."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile

from .models import Decision
from .readers import MAX_FILE_BYTES, _xml, normalized, read_document_text, read_workbook


INVOICE_HINT = re.compile(r"发票|dzfp_", re.I)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
SUPPORTING_DOCUMENT = re.compile(r"通知|说明|须知|申请|清单|汇总|统计|台账|条款|模板|示例|样例|合同|验真|查验|开票信息|开票资料")
INVOICE_TITLE = re.compile(r"电子(?:普通|专用)?发票|增值税(?:电子)?(?:普通|专用)?发票|通用机打发票|医疗(?:门诊|住院)?收费(?:电子)?票据")
DATE = re.compile(r"(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})(?:日|号)?")


def read_image_text(path: Path) -> tuple[str, str]:
    """Use installed Windows OCR only; an unavailable reader leaves the file in place."""
    if os.name != "nt":
        return "", "图片需要本机 Windows 文字识别，当前系统不支持"
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = Path(__file__).with_name("invoice_ocr.ps1")
    try:
        result = subprocess.run(
            [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-File", str(script), "-LiteralPath", str(path.absolute())],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            return "", "本机图片文字识别不可用或图片无法读取，请人工核对"
        text = json.loads(result.stdout).get("text", "")
        return str(text)[:20_000], "" if str(text).strip() else "图片未识别到文字"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return "", "本机图片文字识别未完成，请人工核对"


def read_invoice_text(path: Path) -> tuple[str, str]:
    if path.stat().st_size > MAX_FILE_BYTES:
        return "", "文件超过100 MiB，未读取票面"
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return read_image_text(path)
    if suffix == ".pdf":
        return read_document_text(path)
    if suffix == ".ofd":
        try:
            with ZipFile(path) as archive:
                pages = sorted(name for name in archive.namelist()
                               if "/Pages/" in name and name.endswith("/Content.xml"))[:2]
                text = "\n".join(node.text or "" for name in pages for node in _xml(archive, name).iter()
                                 if node.tag.rsplit("}", 1)[-1] == "TextCode")[:20_000]
            return text, "" if text.strip() else "OFD未提取到票面文字"
        except Exception:
            return "", "OFD票面无法读取，请人工核对"
    if suffix in {".zip", ".rar", ".7z"}:
        return "", "压缩包不是单张发票，请先展开后核对票据，整包保留原处"
    return "", "此类型暂不能核对票面，文件名含发票不代表文件就是发票"


def _invoice_evidence(text: str, limitation: str = "") -> Decision:
    if not text.strip():
        return Decision("review", kind="发票待核对", reason=limitation or "未读取到可核对的票面")
    compact = re.sub(r"\s+", "", normalized(text))
    checks = (
        INVOICE_TITLE.search(compact[:180]),
        re.search(r"发票号码|发票代码|票据号码|票据代码", compact),
        re.search(r"开票日期|开票时间|收费日期", compact),
        re.search(r"购买方|销售方|纳税人识别号|统一社会信用代码|交款人|患者", compact),
        re.search(r"价税合计|金额合计|合计金额|合计", compact),
        re.search(r"\d{8,24}", compact),
        re.search(r"[¥￥]\d|\d+\.\d{2}(?!\d)", compact),
    )
    if not all(checks):
        return Decision("review", kind="发票待核对", reason="票面缺少可相互核对的发票抬头、号码、开票日期或金额；相关截图和材料保留原处")
    years = {year for year, month, day in DATE.findall(compact)
             if 1 <= int(month) <= 12 and 1 <= int(day) <= 31}
    if len(years) != 1:
        return Decision("review", kind="发票", reason="票面年份缺失或出现多个年份，无法确定归档年度")
    return Decision("ready", kind="发票", period=years.pop(),
                    reason="已核对票面抬头、号码、日期及金额，归入现有年度发票目录")


def _is_invoice_index(path: Path) -> bool:
    """A ZIP may retain its invoice list, but not arbitrary unrelated workbooks."""
    sheets = [sheet for sheet in read_workbook(path) if not sheet.hidden]
    if not sheets:
        return False
    for sheet in sheets:
        headers = {re.sub(r"\s+", "", value) for value in sheet.header_cells().values()}
        if not (headers & {"发票号码", "发票号"} and headers & {"金额", "发票金额", "价税合计"}
                and headers & {"开票日期", "开票时间"}):
            return False
    return True


def _invoice_archive(path: Path) -> Decision:
    review = Decision("review", kind="发票压缩包", reason="压缩包含无法确认的文件，整包保留原处待核对")
    if path.stat().st_size > MAX_FILE_BYTES:
        return review
    try:
        with ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="m20-invoices-", suffix="-可删") as directory:
            files = [item for item in archive.infolist() if not item.is_dir()]
            if not files or len(files) > 50 or sum(item.file_size for item in files) > MAX_FILE_BYTES:
                return review
            years, count = set(), 0
            for index, item in enumerate(files):
                suffix = Path(item.filename).suffix.lower()
                if item.flag_bits & 1 or suffix not in IMAGE_SUFFIXES | {".pdf", ".ofd", ".xlsx"}:
                    return review
                # Never extract archive member paths; use bounded, disposable local copies.
                temporary = Path(directory) / f"invoice-{index}{suffix}"
                temporary.write_bytes(archive.read(item))
                if suffix == ".xlsx":
                    if not _is_invoice_index(temporary):
                        return review
                    continue
                decision = _invoice_evidence(*read_invoice_text(temporary))
                if decision.status != "ready":
                    return review
                years.add(decision.period)
                count += 1
            if not count or len(years) != 1:
                return Decision("review", kind="发票压缩包", reason="压缩包未确认有效票据或包含多个年份，保留原处待核对")
            return Decision("ready", kind="发票压缩包", period=years.pop(),
                            reason=f"已逐份核对包内{count}张同年度发票及配套清单，整包归档且保留原始内容")
    except Exception:
        return review


def classify_invoice(path: Path, root: Path) -> Decision:
    if not INVOICE_HINT.search(path.name):
        return Decision("ignored")
    if path.name.startswith("~$"):
        return Decision("skip", reason="临时锁定文件不分发")
    if path.suffix.lower() == ".zip":
        decision = _invoice_archive(path)
    elif SUPPORTING_DOCUMENT.search(path.stem):
        return Decision("skip", kind="发票相关材料", reason="名称属于说明、清单或其他配套材料，不按发票自动归档")
    else:
        decision = _invoice_evidence(*read_invoice_text(path))
    if decision.status != "ready":
        return decision
    year = decision.period
    relative = Path("07_年度工作档案") / f"{year}年" / "财务" / f"{year}年发票"
    if not (root / relative).is_dir():
        return Decision("review", kind=decision.kind, period=year,
                        reason=f"未找到现有的{year}年发票文件夹，不另建或猜测目标")
    return Decision("ready", kind=decision.kind, period=year, relative_dir=relative.as_posix(), reason=decision.reason)
