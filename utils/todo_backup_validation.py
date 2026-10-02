"""Validate complete M14 backup snapshots before restoring or publishing them."""

import re
from datetime import date, datetime

from utils import todo_db


def validate_todo_backup(content):
    """Return parsed records, rejecting partial snapshots and ambiguous identifiers."""
    if not isinstance(content, str):
        raise ValueError("备份内容无效")
    if content.lstrip("\ufeff\r\n ").splitlines()[0:1] != ["# 待办清单备份"]:
        raise ValueError("备份标题无效")
    parts = re.split(r"^## TODO-", content, flags=re.M)
    counts = re.findall(r"^- 记录数量：(\d+)\s*$", parts[0], re.M)
    preamble = [line for line in parts[0].lstrip("\ufeff").splitlines() if line.strip()]
    if any(not (line == "# 待办清单备份" or re.fullmatch(r"- (?:生成时间：.+|记录数量：\d+)", line))
           for line in preamble):
        raise ValueError("备份标题区域无效")
    records = todo_db.parse_markdown_backup(content)
    chunks = parts[1:]
    if len(counts) != 1 or int(counts[0]) != len(records) or len(chunks) != len(records):
        raise ValueError("备份记录数量不完整")
    required_fields = {"发布日期", "截止日期", "截止时间", "状态", "归档", "完成时间", "创建时间", "更新时间"}
    for chunk in chunks:
        lines = chunk.splitlines()
        if not lines or not re.fullmatch(r"[1-9]\d*", lines[0].strip()) or "### 内容" not in lines:
            raise ValueError("备份记录边界无效")
        separator = lines.index("### 内容")
        metadata = [re.fullmatch(r"- ([^：]+)：(.*)", line) for line in lines[1:separator] if line.strip()]
        if not all(metadata):
            raise ValueError("备份记录字段无效")
        fields = {match[1]: match[2].strip() for match in metadata}
        if (len(fields) != len(metadata) or not required_fields <= fields.keys()
                or fields.keys() - required_fields - {"唯一标识"}):
            raise ValueError("备份记录字段不完整")
        if "唯一标识" in fields and not fields["唯一标识"]:
            raise ValueError("备份唯一标识无效")
        if fields["状态"] not in {"pending", "done", "deleted"} or fields["归档"] not in {"是", "否"}:
            raise ValueError("备份状态无效")
        for name in ("发布日期", "截止日期"):
            value = fields[name]
            if name == "发布日期" or value:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError("备份日期无效")
        if fields["截止时间"] and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", fields["截止时间"]):
            raise ValueError("备份截止时间无效")
        for name in ("创建时间", "更新时间"):
            datetime.fromisoformat(fields[name])
        if fields["完成时间"]:
            datetime.fromisoformat(fields["完成时间"])
    ids = [record["id"] for record in records]
    uids = [todo_db.record_uid(record) for record in records]
    if len(set(ids)) != len(ids) or len(set(uids)) != len(uids):
        raise ValueError("备份存在重复标识")
    return records
