"""Register archived dispatches in the explicitly bound DingTalk AI table."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .dispatch import dispatch_number
from .models import PlanItem


BASE_NAME = "健康学院行政"
TABLE_NAME = "发文-2026"
REGISTER_YEAR = "2026"
TARGET_FILE = "dingtalk_target.txt"
NUMBER_FIELD = "文件编号"
TITLE_FIELD = "标题"
DATE_FIELD = "发文时间"
ATTACHMENT_FIELD = "附件"


class DingTalkError(RuntimeError):
    pass


def target_ids(url: str) -> tuple[str, str]:
    parts = urlsplit(url.strip())
    base = re.fullmatch(r"/i/nodes/([A-Za-z0-9_-]+)", parts.path)
    query = parse_qs(parts.query)
    table = parse_qs(query.get("iframeQuery", [""])[0]).get("sheetId", [""])[0]
    if (parts.scheme != "https" or parts.netloc != "alidocs.dingtalk.com" or not base
            or not re.fullmatch(r"[A-Za-z0-9_-]+", table)):
        raise DingTalkError("需要「健康学院行政 / 发文-2026」的钉钉数据表链接")
    return base[1], table


def _executable() -> Path:
    configured = os.environ.get("M20_DINGTALK_CLI", "")
    name = "dws.exe" if os.name == "nt" else "dws"
    candidates = ([Path(configured)] if configured else [
        Path.home() / ".local" / "bin" / name, Path.home() / "bin" / name,
        *(Path(entry) / name for entry in os.get_exec_path() if Path(entry).is_absolute()),
    ])
    for path in candidates:
        if path.is_absolute() and path.is_file():
            return path
    raise DingTalkError("本机未找到钉钉官方命令行 dws；登录授权后可补同步")


def _call(exe: Path, *args: str) -> dict:
    try:
        run = subprocess.run([str(exe), "--format", "json", *args], capture_output=True,
                             encoding="utf-8", errors="replace", timeout=25,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DingTalkError("无法运行钉钉命令或调用超时") from exc
    try:
        payload = json.loads(run.stdout)
    except ValueError:
        payload = {}
    if (not isinstance(payload, dict) or run.returncode or payload.get("error")
            or payload.get("success") is False or payload.get("status") in ("error", "failed")):
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        code = error.get("code") if isinstance(error, dict) else None
        suffix = f"（{code}）" if re.fullmatch(r"[\w.-]{1,64}", str(code or "")) else ""
        raise DingTalkError(f"钉钉拒绝或未确认请求{suffix}，请核对 dws 登录、组织权限及网络")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise DingTalkError("钉钉返回的数据结构无法确认")
    return data


def _entries(data: dict, key: str) -> list[dict]:
    values = data.get(key)
    if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
        raise DingTalkError("钉钉返回的数据不完整")
    return values


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "".join(_text(entry) for entry in value)
    if isinstance(value, dict):
        return _text(value.get("text"))
    return ""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DingTalkError("钉钉附件上传地址要求跳转，上传待核对")


def _put(url: str, data: bytes) -> None:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if (parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443)
            or not (host.endswith((".aliyuncs.com", ".dingtalk.com", ".alidocs.com", ".aliimg.com"))
                    or host == "dingtalk.com")):
        raise DingTalkError("钉钉附件上传地址无法验证")
    request = Request(url, data=data, method="PUT", headers={"Content-Type": "application/pdf"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=30) as response:
            if response.status not in (200, 201, 204):
                raise DingTalkError("钉钉附件上传未确认")
    except OSError as exc:
        # A signed URL contains sensitive upload credentials. Do not store its raw error.
        raise DingTalkError("钉钉附件上传失败，归档文件可重试") from exc


@dataclass(frozen=True)
class DingTalkRegister:
    executable: Path
    base_id: str
    table_id: str
    fields: dict[str, str]

    @classmethod
    def connect(cls) -> "DingTalkRegister":
        path = Path(__file__).with_name(TARGET_FILE)
        url = os.environ.get("M20_DINGTALK_TABLE_URL") or (path.read_text(encoding="utf-8-sig") if path.is_file() else "")
        base_id, table_id = target_ids(url)
        exe = _executable()
        base = _call(exe, "aitable", "base", "get", "--base-id", base_id)
        base = base.get("base", base)
        if not isinstance(base, dict) or base.get("name") != BASE_NAME:
            raise DingTalkError("钉钉应用名称与「健康学院行政」不一致")
        tables = _call(exe, "aitable", "table", "get", "--base-id", base_id)
        if not any(row.get("tableId") == table_id and row.get("name") == TABLE_NAME for row in _entries(tables, "tables")):
            raise DingTalkError("目标工作表与「发文-2026」不一致")
        args = ("--base-id", base_id, "--table-id", table_id)
        schema = _entries(_call(exe, "aitable", "field", "get", *args), "fields")
        fields = {}
        types = {NUMBER_FIELD: {"text"}, TITLE_FIELD: {"text"}, DATE_FIELD: {"date", "text"},
                 ATTACHMENT_FIELD: {"attachment"}}
        for name, allowed in types.items():
            matches = [field for field in schema if field.get("name") == name]
            if len(matches) == 1 and matches[0].get("type") in allowed and matches[0].get("fieldId"):
                fields[name] = matches[0]["fieldId"]
            elif name != DATE_FIELD:
                raise DingTalkError(f"钉钉「{name}」列不存在或类型不匹配")
        return cls(exe, base_id, table_id, fields)

    def _command(self, group, action, *args):
        return _call(self.executable, "aitable", group, action, "--base-id", self.base_id,
                     "--table-id", self.table_id, *args)

    def matching_records(self, number: str) -> list[dict]:
        matching = []
        cursor = ""
        seen = set()
        while True:
            args = ("--cursor", cursor) if cursor else ()
            page = self._command("record", "query", "--field-ids", ",".join(self.fields.values()), *args)
            for row in _entries(page, "records"):
                cells = row.get("cells")
                if not isinstance(cells, dict):
                    raise DingTalkError("钉钉记录缺少字段数据，无法查重")
                if dispatch_number(_text(cells.get(self.fields[NUMBER_FIELD]))) == number:
                    matching.append(row)
            cursor = page.get("nextCursor") or ""
            if not cursor:
                if page.get("hasMore"):
                    raise DingTalkError("钉钉查询分页不完整，无法查重")
                return matching
            if cursor in seen:
                raise DingTalkError("钉钉查询分页未能完成")
            seen.add(cursor)

    def register(self, item: PlanItem, archive: Path) -> str:
        number = item.document_number
        if item.period != REGISTER_YEAR or f"〔{REGISTER_YEAR}〕" not in number or dispatch_number(number) != number:
            raise DingTalkError("该文号不属于发文-2026登记范围")
        matches = self.matching_records(number)
        if len(matches) > 1:
            raise DingTalkError("钉钉已有多条相同文号，请先核对")
        row = matches[0] if matches else None
        existing = row["cells"] if row else {}
        attachment_id = self.fields[ATTACHMENT_FIELD]
        if existing.get(attachment_id):
            return "钉钉已有同文号和附件，保留原记录"
        record_id = row.get("recordId") if row else None
        if row and not record_id:
            raise DingTalkError("钉钉同文号记录缺少标识，无法补齐")
        data = archive.read_bytes()
        if len(data) != item.size or hashlib.sha256(data).hexdigest() != item.sha256:
            raise DingTalkError("归档 PDF 已变化，请核对原件")
        ticket = _call(self.executable, "aitable", "attachment", "upload", "--base-id", self.base_id,
                       "--file-name", archive.name, "--size", str(len(data)), "--mime-type", "application/pdf")
        if not ticket.get("uploadUrl") or not ticket.get("fileToken"):
            raise DingTalkError("钉钉未返回可用的附件上传凭证")
        _put(ticket["uploadUrl"], data)
        matches = self.matching_records(number)
        if len(matches) > 1 or (record_id and (not matches or matches[0].get("recordId") != record_id)):
            raise DingTalkError("上传期间钉钉同文号记录发生变化，请核对后重试")
        if matches:
            existing = matches[0]["cells"]
            if existing.get(attachment_id):
                return "钉钉已有同文号和附件，保留原记录"
            record_id = matches[0].get("recordId")
            if not record_id:
                raise DingTalkError("钉钉同文号记录缺少标识，无法补齐")
        cells = {attachment_id: [{"fileToken": ticket["fileToken"]}]}
        for name, value in ((NUMBER_FIELD, number.replace("〔", "[").replace("〕", "]")),
                            (TITLE_FIELD, item.document_title), (DATE_FIELD, item.document_date)):
            field_id = self.fields.get(name)
            if field_id and value and not existing.get(field_id):
                cells[field_id] = value
        payload = {"cells": cells}
        if record_id:
            payload["recordId"] = record_id
        with TemporaryDirectory(prefix="m20-dingtalk-") as temp:
            file = Path(temp) / "record.json"
            file.write_text(json.dumps([payload], ensure_ascii=False), encoding="utf-8")
            self._command("record", "update" if record_id else "create", "--records-file", str(file))
        verified = self.matching_records(number)
        attachments = verified[0]["cells"].get(attachment_id) if len(verified) == 1 else None
        if not isinstance(attachments, list) or not any(
            isinstance(value, dict) and (value.get("fileToken") == ticket["fileToken"]
                or value.get("filename", value.get("fileName")) == archive.name and value.get("size") == len(data))
            for value in attachments
        ):
            raise DingTalkError("钉钉回读未确认该文号或附件，可核对后补同步")
        return "钉钉已登记并回读确认 PDF 附件"
