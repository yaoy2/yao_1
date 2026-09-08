"""Monthly department activity rosters, accruals and versioned persistence."""

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from utils import github_backup_sync


MONTHLY_RATE = 30
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_SAVE_LOCK = threading.RLock()


def today_in_shanghai():
    return datetime.now(timezone(timedelta(hours=8))).date()


def new_budget(year):
    return {
        "schema_version": 1,
        "year": int(year),
        "months": {str(month): None for month in range(1, 13)},
        "reimbursed_months": [],
        "reimbursement_confirmed": False,
        "updated_at": "",
    }


def validate_budget(data, year):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("year") != year:
        raise ValueError("部门活动预算文件版本或年度不正确。")
    months = data.get("months")
    if not isinstance(months, dict) or set(months) != {str(m) for m in range(1, 13)}:
        raise ValueError("部门活动预算必须包含1—12月。")
    for names in months.values():
        if names is not None and (
            not isinstance(names, list)
            or any(not isinstance(name, str) or not name.strip() for name in names)
        ):
            raise ValueError("月度名单格式不正确。")
    paid = data.get("reimbursed_months")
    if (not isinstance(paid, list)
            or any(type(m) is not int or not 1 <= m <= 12 for m in paid)
            or len(set(paid)) != len(paid)):
        raise ValueError("已报销月份必须是1—12月，且不能重复。")
    if any(months[str(m)] is None for m in paid):
        raise ValueError("已报销月份缺少完整名单。")
    if type(data.get("reimbursement_confirmed")) is not bool:
        raise ValueError("缺少报销确认状态。")
    if paid and not data["reimbursement_confirmed"]:
        raise ValueError("已报销月份尚未确认。")
    return data


def parse_names(text):
    """Keep same-name teachers; never silently remove people from a roster."""
    return [name.strip() for name in re.split(r"[\r\n,，、;；\t]+", text) if name.strip()]


def cutoff_month(year, today=None):
    today = today or today_in_shanghai()
    return 12 if year < today.year else 0 if year > today.year else today.month


def set_rosters(data, months, names):
    updated = copy.deepcopy(data)
    if not months:
        raise ValueError("请至少选择一个月份。")
    if not isinstance(names, list):
        raise ValueError("教师名单必须逐人填写。")
    for month in months:
        if type(month) is not int or not 1 <= month <= 12:
            raise ValueError("月份必须在1—12月之间。")
        updated["months"][str(month)] = list(names)
    return validate_budget(updated, data["year"])


def change_people(data, month, additions=None, remove_indices=None):
    """Apply one month's hires/departures, keeping every other month intact."""
    if type(month) is not int or not 1 <= month <= 12:
        raise ValueError("月份必须在1—12月之间。")
    names = data["months"][str(month)]
    if names is None:
        raise ValueError("请先补全该月名单，或从已录入月份复制名单。")
    additions = [] if additions is None else additions
    remove_indices = [] if remove_indices is None else remove_indices
    if not isinstance(additions, list):
        raise ValueError("新增姓名须逐人填写。")
    if any(type(index) is not int or not 0 <= index < len(names) for index in remove_indices):
        raise ValueError("离职人员选择已失效，请刷新名单后重新选择。")
    if not additions and not remove_indices:
        raise ValueError("请填写新入职姓名，或选择离职人员。")
    removed = set(remove_indices)
    remaining = [name for index, name in enumerate(names) if index not in removed]
    return set_rosters(data, [month], remaining + additions)


def set_reimbursed_months(data, months, today=None):
    updated = copy.deepcopy(data)
    cutoff = cutoff_month(data["year"], today)
    for month in months:
        if type(month) is not int or not 1 <= month <= cutoff:
            raise ValueError("只能报销截至当前月份已经产生的预算。")
        if data["months"][str(month)] is None:
            raise ValueError(f"请先补全{month}月名单，再登记报销。")
    updated["reimbursed_months"] = sorted(set(months))
    updated["reimbursement_confirmed"] = True
    return validate_budget(updated, data["year"])


def summarize(data, today=None):
    validate_budget(data, data["year"])
    cutoff = cutoff_month(data["year"], today)
    missing = [m for m in range(1, cutoff + 1) if data["months"][str(m)] is None]
    known_total = sum(len(data["months"][str(m)]) * MONTHLY_RATE
                      for m in range(1, cutoff + 1) if m not in missing)
    paid_months = [m for m in data["reimbursed_months"] if m <= cutoff]
    reimbursed = (sum(len(data["months"][str(m)]) * MONTHLY_RATE for m in paid_months)
                  if data["reimbursement_confirmed"] else None)
    total = None if missing else known_total
    return {
        "cutoff_month": cutoff, "missing_months": missing, "known_total": known_total,
        "total": total, "reimbursed_months": paid_months, "reimbursed": reimbursed,
        "balance": total - reimbursed if total is not None and reimbursed is not None else None,
    }


def monthly_rows(data, today=None):
    cutoff = cutoff_month(data["year"], today)
    rows = []
    for month in range(1, 13):
        names = data["months"][str(month)]
        amount = None if names is None else len(names) * MONTHLY_RATE
        status = ("未到月份" if month > cutoff else "名单待补全" if names is None
                  else "报销待确认" if not data["reimbursement_confirmed"]
                  else "已报销" if month in data["reimbursed_months"] else "未报销")
        rows.append({"月份": f"{month}月", "教师人数": None if names is None else len(names),
                     "预算（元）": amount, "报销状态": status,
                     "已报销（元）": amount if status == "已报销" else None if "待" in status else 0})
    return rows


def roster_columns(data):
    height = max(1, max(len(names or []) for names in data["months"].values()))
    return {f"{month}月": (["待补全"] if names is None else names or ["已确认0人"])
            + [""] * (height - max(1, len(names or [])))
            for month in range(1, 13) for names in [data["months"][str(month)]]}


def build_roster_html(data, selected_month=None):
    """Excel-style month columns, with the amount and headcount kept above names."""
    validate_budget(data, data["year"])
    columns = roster_columns(data)
    amounts, headcounts = [], []
    for month in range(1, 13):
        names = data["months"][str(month)]
        amounts.append("待补全" if names is None else f"{len(names) * MONTHLY_RATE:,}")
        headcounts.append("待补全" if names is None else str(len(names)))

    def row(label, values, header=False):
        cells = [f'<th scope="row">{escape(str(label))}</th>']
        for month, value in enumerate(values, 1):
            tag = "th" if header else "td"
            selected = ' class="selected-month"' if month == selected_month else ""
            cells.append(f"<{tag}{selected}>{escape(str(value))}</{tag}>")
        return "<tr>" + "".join(cells) + "</tr>"

    parts = ["""<style>
    .department-activity-sheet {overflow:auto;max-height:560px;border:1px solid #cbd3dc;
        border-radius:6px;background:#fff;color:#233044;}
    .department-activity-sheet table {border-collapse:separate;border-spacing:0;
        width:100%;font-size:13px;line-height:1.4;}
    .department-activity-sheet th,.department-activity-sheet td {box-sizing:border-box;
        min-width:68px;height:31px;padding:5px 9px;text-align:center;white-space:nowrap;
        border-right:1px solid #d9dfe6;border-bottom:1px solid #d9dfe6;}
    .department-activity-sheet thead th,.department-activity-sheet thead td {
        position:sticky;z-index:2;background:#eef2f5;height:32px;}
    .department-activity-sheet thead tr:nth-child(1)>* {top:0;}
    .department-activity-sheet thead tr:nth-child(2)>* {top:32px;}
    .department-activity-sheet thead tr:nth-child(3)>* {top:64px;}
    .department-activity-sheet tr>:first-child {position:sticky;left:0;z-index:1;
        background:#eef2f5;min-width:72px;font-weight:normal;}
    .department-activity-sheet thead tr>:first-child {z-index:3;}
    .department-activity-sheet .selected-month {background:#e6f4ef;}
    </style><div class="department-activity-sheet"><table aria-label="部门活动经费月度名单"><thead>"""]
    parts.append(row("月份", [f"{month}月" for month in range(1, 13)], header=True))
    parts.append(row("费用（元）", amounts))
    parts.append(row("人数", headcounts))
    parts.append("</thead><tbody>")
    for index, values in enumerate(zip(*columns.values()), 1):
        parts.append(row(index, values))
    parts.append("</tbody></table></div>")
    return "".join(parts)


def _paths(year):
    filename = f"department_activity_budget_{year}.json"
    return DATA_DIR / filename, f"data/{filename}"


def _version(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _decode(raw, year):
    try:
        return validate_budget(json.loads(raw), year)
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("部门活动预算文件无法读取，请核对原文件；本次未覆盖任何数据。") from None


def load_budget(year, secrets=None, environ=None, session=None):
    local_path, repo_path = _paths(year)
    result = github_backup_sync.read_file_from_github(
        repo_path, secrets=secrets, environ=environ, session=session)
    if result.get("ok"):
        if not result.get("sha"):
            raise RuntimeError("远端未返回有效版本，请刷新后重试。")
        return {"data": _decode(result["content"], year), "version": result["sha"], "source": "github"}
    if result.get("reason") == "missing_remote_file":
        return {"data": new_budget(year), "version": None, "source": "github"}
    if result.get("reason") != "missing_token":
        raise RuntimeError("部门活动预算读取失败，请稍后重试。")
    with _SAVE_LOCK:
        raw = local_path.read_bytes() if local_path.exists() else None
    return {"data": new_budget(year) if raw is None else _decode(raw, year),
            "version": _version(raw), "source": "local"}


def save_budget(data, snapshot, secrets=None, environ=None, session=None):
    """Publish against the version the user read; only then replace the local backup."""
    data = copy.deepcopy(validate_budget(data, snapshot["data"]["year"]))
    data["updated_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    local_path, repo_path = _paths(data["year"])
    raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with _SAVE_LOCK:
        config = github_backup_sync.get_backup_sync_config(secrets, environ)
        source = "github" if config["enabled"] else "local"
        if source != snapshot["source"]:
            raise RuntimeError("保存位置已变化，请先刷新最新数据。")
        if source == "local":
            current = local_path.read_bytes() if local_path.exists() else None
            if _version(current) != snapshot["version"]:
                raise RuntimeError("本地数据已更新，本次未覆盖；请刷新最新数据后重新保存。")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=local_path.parent, suffix=".tmp", delete=False) as staged:
            staged.write(raw)
            staged_path = Path(staged.name)
        warning = None
        try:
            version = _version(raw)
            if source == "github":
                result = github_backup_sync.sync_file_to_github(
                    staged_path, repo_path, "data: sync department activity budget",
                    secrets=secrets, environ=environ, session=session, expected_sha=snapshot["version"])
                if not result.get("ok"):
                    raise RuntimeError("部门活动预算尚未保存，请刷新后重试。")
                version = result.get("sha")
            try:
                os.replace(staged_path, local_path)
            except OSError:
                if source == "local":
                    raise
                warning = "已保存到云端，但当前环境的本地副本未能更新；请刷新读取云端结果。"
        finally:
            staged_path.unlink(missing_ok=True)
    return {"data": data, "version": version, "source": source, "warning": warning}
