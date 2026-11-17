"""M34 work playbooks, editable flow nodes and immutable historical snapshots."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import re
import uuid


REPO_PATH = "data/work_guides.json"
MAX_DOCUMENT_BYTES = 900_000
STATUSES = ("准备中", "办理中", "已提交", "已完成", "待确认")
GUIDE_FIELDS = {
    "title": "工作名称", "category": "分类", "frequency": "办理频率",
    "summary": "工作简介", "trigger": "什么时候开始", "contacts": "对接单位与联系人",
    "requirements": "通用要求", "pitfalls": "踩坑与检查提醒", "sources": "要求出处与材料位置",
    "verified_on": "最近核对日期",
}
STEP_FIELDS = {
    "title": "节点名称", "action": "做什么", "contacts": "对接谁", "materials": "用什么材料",
    "output": "留下什么 / 完成标志", "pitfalls": "本步易错点", "sources": "依据与材料位置",
    "next_label": "进入下一步的条件", "branch_to": "分支目标", "branch_label": "分支条件",
}
RECORD_FIELDS = {
    "period": "年度 / 批次", "title": "记录标题", "status": "办理状态", "handled_on": "办理日期",
    "contacts": "本次对接单位与联系人", "changes": "当年要求与变化", "actual_steps": "实际办理经过",
    "materials": "最终提交版与材料位置", "receipt": "提交与接收回执", "pitfalls": "本次踩坑与原因",
    "next_tips": "下次提前准备什么", "sources": "当年通知与确认依据", "notes": "其他备注",
}


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def empty_document():
    return {"schema_version": 1, "revision": 0, "updated_at": now(), "guides": []}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _identifier(value):
    return type(value) is str and bool(re.fullmatch(r"[a-f0-9]{32}", value))


def _date(value, label):
    if not value:
        return
    try:
        _require(date.fromisoformat(value).isoformat() == value, f"{label}请填写 YYYY-MM-DD。")
    except (TypeError, ValueError):
        raise ValueError(f"{label}请填写有效的 YYYY-MM-DD。") from None


def _entity(item, fields, extra, required):
    _require(type(item) is dict and set(item) == set(fields) | set(extra) | {"id", "created_at", "updated_at"},
             "记录字段不完整或版本不兼容，未改动原始内容。")
    _require(_identifier(item["id"]), "记录编号无效。")
    for field, label in fields.items():
        _require(type(item[field]) is str and len(item[field]) <= 30000, f"{label}应为文字，且不超过三万字。")
    for field in required:
        _require(bool(item[field].strip()), f"请填写{fields[field]}。")
    for field in ("created_at", "updated_at"):
        try:
            _require(type(item[field]) is str and datetime.fromisoformat(item[field]).tzinfo is not None,
                     "记录时间无效。")
        except (TypeError, ValueError):
            raise ValueError("记录时间无效。") from None


def _guide(guide, with_records=True):
    _entity(guide, GUIDE_FIELDS, {"archived", "steps", *(["records"] if with_records else [])}, {"title"})
    _require(type(guide["archived"]) is bool, "工作归档状态无效。")
    _date(guide["verified_on"], "最近核对日期")
    _require(type(guide["steps"]) is list and len(guide["steps"]) <= 200, "单项工作最多保存200个节点。")
    ids = set()
    active_ids = {s.get("id") for s in guide["steps"] if type(s) is dict and s.get("enabled") is True
                  and _identifier(s.get("id"))}
    for step in guide["steps"]:
        _entity(step, STEP_FIELDS, {"enabled", "continue_next"}, {"title"})
        _require(step["id"] not in ids, "流程节点编号重复。")
        ids.add(step["id"])
        _require(type(step["enabled"]) is bool and type(step["continue_next"]) is bool, "节点状态无效。")
        if step["branch_to"]:
            _require(step["branch_to"] in active_ids, "分支目标已停用或不存在，请先调整相关分支。")
            _require(bool(step["branch_label"].strip()), "请选择分支的触发条件。")
        else:
            _require(not step["branch_label"], "填写分支条件时，请同时选择转到哪个节点。")
    if not with_records:
        return
    _require(type(guide["records"]) is list and len(guide["records"]) <= 2000, "历年记录数量超出范围。")
    record_ids = set()
    for record in guide["records"]:
        _entity(record, RECORD_FIELDS, {"guide_snapshot"}, {"period", "title", "status"})
        _require(record["id"] not in record_ids and record["status"] in STATUSES, "记录编号重复或状态无效。")
        record_ids.add(record["id"])
        _date(record["handled_on"], "办理日期")
        _guide(record["guide_snapshot"], with_records=False)
        _require(record["guide_snapshot"]["id"] == guide["id"], "历史快照与所属工作不一致。")


def validate_document(document):
    _require(type(document) is dict and set(document) == {"schema_version", "revision", "updated_at", "guides"},
             "工作指南结构无效。")
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1, "指南版本不兼容。")
    _require(type(document["revision"]) is int and document["revision"] >= 0, "指南修订号无效。")
    _require(type(document["updated_at"]) is str, "指南更新时间无效。")
    try:
        _require(datetime.fromisoformat(document["updated_at"]).tzinfo is not None, "指南更新时间无效。")
    except (TypeError, ValueError):
        raise ValueError("指南更新时间无效。") from None
    _require(type(document["guides"]) is list and len(document["guides"]) <= 500, "最多保存500项工作。")
    ids = set()
    for guide in document["guides"]:
        _guide(guide)
        _require(guide["id"] not in ids, "工作编号重复。")
        ids.add(guide["id"])
    _require(len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")) <= MAX_DOCUMENT_BYTES,
             "内容已达到本版保存容量，请先导出备份，再联系维护者扩容。")
    return document


def serialize(document):
    validate_document(document)
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _new(fields):
    stamp = now()
    return {"id": uuid.uuid4().hex, **dict.fromkeys(fields, ""), "created_at": stamp, "updated_at": stamp}


def _edit(item, changes, fields, flags=()):
    _require(set(changes) <= set(fields) | set(flags), "不能修改系统编号或历史快照。")
    for key, value in changes.items():
        if key in flags:
            _require(type(value) is bool, "状态值无效。")
            item[key] = value
        else:
            _require(type(value) is str, f"{fields[key]}请填写文字。")
            item[key] = value.strip()
    item["updated_at"] = now()


def get_guide(document, guide_id):
    guide = next((g for g in document["guides"] if g["id"] == guide_id), None)
    _require(guide is not None, "这项工作已变化，请刷新后重试。")
    return guide


def _commit(document):
    document["revision"] += 1
    document["updated_at"] = now()
    return validate_document(document)


def update_guide(document, changes, guide_id=None):
    draft = deepcopy(validate_document(document))
    if guide_id is None:
        guide = {**_new(GUIDE_FIELDS), "archived": False, "steps": [], "records": []}
        draft["guides"].append(guide)
    else:
        guide = get_guide(draft, guide_id)
    _edit(guide, changes, GUIDE_FIELDS, ("archived",))
    return _commit(draft), guide["id"]


def update_step(document, guide_id, changes, step_id=None):
    draft = deepcopy(validate_document(document))
    guide = get_guide(draft, guide_id)
    if step_id is None:
        step = {**_new(STEP_FIELDS), "enabled": True, "continue_next": True}
        guide["steps"].append(step)
    else:
        step = next((s for s in guide["steps"] if s["id"] == step_id), None)
        _require(step is not None, "节点已变化，请刷新后重试。")
    _edit(step, changes, STEP_FIELDS, ("enabled", "continue_next"))
    guide["updated_at"] = now()
    return _commit(draft), step["id"]


def move_step(document, guide_id, step_id, direction):
    _require(type(direction) is int and direction in (-1, 1), "移动方向无效。")
    draft = deepcopy(validate_document(document))
    guide = get_guide(draft, guide_id)
    index = next((i for i, s in enumerate(guide["steps"]) if s["id"] == step_id), -1)
    _require(index >= 0 and 0 <= index + direction < len(guide["steps"]), "节点已经在边界位置。")
    guide["steps"][index], guide["steps"][index + direction] = guide["steps"][index + direction], guide["steps"][index]
    guide["updated_at"] = now()
    return _commit(draft)


def update_record(document, guide_id, changes, record_id=None):
    draft = deepcopy(validate_document(document))
    guide = get_guide(draft, guide_id)
    if record_id is None:
        record = {**_new(RECORD_FIELDS), "status": STATUSES[0],
                  "guide_snapshot": deepcopy({k: v for k, v in guide.items() if k != "records"})}
        guide["records"].append(record)
    else:
        record = next((r for r in guide["records"] if r["id"] == record_id), None)
        _require(record is not None, "历年记录已变化，请刷新后重试。")
    _edit(record, changes, RECORD_FIELDS)
    guide["updated_at"] = now()
    return _commit(draft), record["id"]


def retained_ids(document):
    ids = set()
    for guide in document["guides"]:
        ids.add((guide["id"],))
        for kind in ("steps", "records"):
            ids.update((guide["id"], kind, item["id"]) for item in guide[kind])
    return ids


def check_transition(before, after):
    validate_document(after)
    _require(after["revision"] == (before["revision"] if before else 0) + 1, "修订号不连续，请刷新后重试。")
    if before is None:
        return
    _require(retained_ids(before) <= retained_ids(after), "保存不能移除已有内容，请使用归档或停用。")
    new_guides = {g["id"]: g for g in after["guides"]}
    for guide in before["guides"]:
        records = {r["id"]: r for r in new_guides[guide["id"]]["records"]}
        for record in guide["records"]:
            _require(record["guide_snapshot"] == records[record["id"]]["guide_snapshot"], "不能覆盖历年记录的原始指南快照。")


def search_guides(document, query="", category="全部分类", include_archived=False):
    words = query.casefold().split()
    result = []
    for guide in document["guides"]:
        if guide["archived"] and not include_archived or category != "全部分类" and guide["category"] != category:
            continue
        text = json.dumps(guide, ensure_ascii=False).casefold()
        if all(word in text for word in words):
            result.append(guide)
    return sorted(result, key=lambda g: (g["archived"], g["category"], g["title"]))


def flow_dot(guide, selected=None):
    steps = [s for s in guide["steps"] if s["enabled"]]
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    lines = ['digraph Work {', 'rankdir=LR; bgcolor="transparent";',
             'node [shape=box, style="rounded", fontname="sans-serif"];', 'edge [fontname="sans-serif"];']
    for index, step in enumerate(steps):
        label = quote(f"{index + 1} · {step['title']}")
        lines.append(f'{quote(step["id"])} [label={label}, penwidth={2 if step["id"] == selected else 1}];')
        if index + 1 < len(steps) and step["continue_next"]:
            lines.append(f'{quote(step["id"])} -> {quote(steps[index + 1]["id"])} [label={quote(step["next_label"])}];')
        if step["branch_to"]:
            lines.append(f'{quote(step["id"])} -> {quote(step["branch_to"])} [label={quote(step["branch_label"])}, style=dashed];')
    return "\n".join([*lines, "}"])


def guide_markdown(guide):
    lines = [f"# {guide['title']}", ""]
    for field, label in GUIDE_FIELDS.items():
        if field != "title" and guide[field]:
            lines.extend([f"## {label}", guide[field], ""])
    names = {s["id"]: s["title"] for s in guide["steps"]}
    for index, step in enumerate(guide["steps"], 1):
        lines.extend([f"## 节点 {index}：{step['title']}" + ("（已停用）" if not step["enabled"] else ""), ""])
        for field in ("action", "contacts", "materials", "output", "pitfalls", "sources", "next_label"):
            if step[field]:
                lines.extend([f"**{STEP_FIELDS[field]}**", step[field], ""])
        lines.extend(["**主线**", "继续下一节点" if step["continue_next"] else "在此结束主线", ""])
        if step["branch_to"]:
            lines.extend([f"**分支**：{step['branch_label']} → {names[step['branch_to']]}", ""])
    return "\n".join(lines)
