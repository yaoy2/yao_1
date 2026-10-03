"""Validate private backups before treating them as an authoritative snapshot."""

import json
import math
import re

MANAGED_FILES = (
    "data/budget_ledger_backup.md", "data/department_activity_budget_2026.json",
    "data/ding_minutes_cloud.json", "data/llm_budget_accounts.json", "data/llm_budget_records.json",
    "data/schedule_cache.json", "data/schedule_metadata.json", "data/teacher_category_cache.json",
    "data/todo_items_backup.md", "data/web_memos_backup.md",
)


def validate_backup(repo_path, content):
    if not isinstance(content, str) or not content.strip():
        raise ValueError("备份为空，已停止同步。")
    if repo_path == "data/todo_items_backup.md":
        from utils.todo_backup_validation import validate_todo_backup
        return validate_todo_backup(content)
    if repo_path in {"data/budget_ledger_backup.md", "data/web_memos_backup.md"}:
        from utils import budget_db, web_memo_db
        parser = budget_db if "budget_ledger" in repo_path else web_memo_db
        title = "# 预算速记台账备份" if parser is budget_db else "# 灵感便签盒备份"
        if content.lstrip("\ufeff\r\n ").splitlines()[0:1] != [title]:
            raise ValueError("备份标题无效。")
        if parser is budget_db:
            header = next((line for line in content.splitlines() if line.strip().startswith("|")), "")
            if budget_db._split_markdown_table_row(header) != [label for _, label in budget_db.BACKUP_COLUMNS]:
                raise ValueError("预算备份字段不完整。")
        records = parser.parse_markdown_backup(content)
        preamble = re.split(r"^## |^\|", content, maxsplit=1, flags=re.M)[0]
        counts = re.findall(r"^- 记录数量：(\d+)\s*$", preamble, re.M)
        for item in records:
            if not re.fullmatch(r"[1-9]\d*", str(item.get("id", ""))):
                raise ValueError("备份记录标识无效。")
            item["id"] = int(item["id"])
        ids = [item.get("id") for item in records]
        if len(counts) != 1 or int(counts[0]) != len(records) or len(set(ids)) != len(ids) or any(
                not isinstance(value, int) or value <= 0 for value in ids):
            raise ValueError("备份数量或记录标识无效，已停止同步。")
        if "budget_ledger" in repo_path and any(not math.isfinite(float(item["amount"])) for item in records):
            raise ValueError("备份金额无效，已停止同步。")
        return records
    data = json.loads(content, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("JSON 含无效数值")))
    if repo_path == "data/department_activity_budget_2026.json":
        from utils.department_activity import validate_budget
        validate_budget(data, 2026)
    elif repo_path == "data/ding_minutes_cloud.json":
        if (not isinstance(data, dict) or not isinstance(data.get("records"), list)
                or data.get("record_count") != len(data["records"])
                or any(not isinstance(item, dict) for item in data["records"])):
            raise ValueError("Recorder 备份结构或记录数量不完整。")
    elif repo_path == "data/schedule_cache.json":
        fields = {"term", "weekday", "start_period", "end_period", "teachers", "course", "weeks", "classroom", "class_group"}
        if (not isinstance(data, list) or any(not isinstance(item, dict) or not fields <= item.keys()
                or not isinstance(item["teachers"], list) or not isinstance(item["weeks"], list) for item in data)):
            raise ValueError("课表备份字段不完整。")
    elif repo_path == "data/llm_budget_records.json":
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ValueError("LLM 流水备份应为记录列表。")
    elif repo_path in {"data/llm_budget_accounts.json", "data/schedule_metadata.json", "data/teacher_category_cache.json"}:
        if not isinstance(data, dict):
            raise ValueError("备份应为 JSON 对象。")
    elif not isinstance(data, (list, dict)):
        raise ValueError("备份应为 JSON 记录集合。")
    return data


def would_drop_records(repo_path, before, after):
    if repo_path == "data/ding_minutes_cloud.json":
        before, after = before["records"], after["records"]
    if isinstance(before, list):
        if len(after) < len(before):
            return True
        if repo_path == "data/todo_items_backup.md":
            from utils.todo_db import record_uid
            after_uids = {record_uid(item) for item in after}
            legacy_after_ids = {item["id"] for item in after if not item.get("uid")}
            for item in before:
                if record_uid(item) in after_uids:
                    continue
                # Legacy snapshots have no UID; editing their date must not
                # turn the derived UID into an apparent deletion.
                if not item.get("uid") and item["id"] in legacy_after_ids:
                    continue
                return True
            return False
        if repo_path in {"data/budget_ledger_backup.md", "data/web_memos_backup.md", "data/ding_minutes_cloud.json"}:
            # Additions must not hide removed records; editing existing fields is safe.
            before_ids = {str(item["id"]) for item in before if item.get("id") is not None}
            after_ids = {str(item["id"]) for item in after if item.get("id") is not None}
            return not before_ids <= after_ids
        return False
    if repo_path in {"data/llm_budget_accounts.json", "data/teacher_category_cache.json"}:
        return not before.keys() <= after.keys()
    return False


def equivalent_backup(repo_path, first, second):
    """Ignore export timestamps and serialization order, never business fields."""
    left, right = validate_backup(repo_path, first), validate_backup(repo_path, second)
    if isinstance(left, list) and repo_path.endswith(".md"):
        left = sorted(left, key=lambda record: record["id"])
        right = sorted(right, key=lambda record: record["id"])
    return left == right
