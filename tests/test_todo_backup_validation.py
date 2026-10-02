"""Malformed remote snapshots must never become writable M14 state."""

import pytest

from utils import todo_db
from utils.todo_backup_validation import validate_todo_backup


def record(**changes):
    return {"id": 7, "uid": "existing-record-7", "content": "既有待办\n- 正文列表",
            "record_date": "2026-09-30", "due_date": "2026-10-01", "due_time": "17:00",
            "status": "pending", "is_archived": False, "completed_at": "",
            "created_at": "2026-09-30 09:00:00", "updated_at": "2026-09-30 09:00:00", **changes}


def test_valid_snapshot_retains_fields_and_deleted_tombstone():
    records = [record(), record(id=8, uid="existing-record-8", status="deleted", is_archived=True)]
    assert validate_todo_backup(todo_db.build_markdown_backup(records)) == records
    assert validate_todo_backup(todo_db.build_markdown_backup([])) == []


@pytest.mark.parametrize("mutation", [
    lambda text: text.replace("记录数量：1", "记录数量：0"),
    lambda text: text.replace("- 记录数量：1\n", ""),
    lambda text: text.replace("- 更新时间：2026-09-30 09:00:00\n", ""),
    lambda text: text.replace("- 状态：pending", "- 状态：invalid"),
    lambda text: text.replace("- 归档：否", "- 归档：未知"),
    lambda text: text.replace("- 截止日期：2026-10-01", "- 截止日期：2026-02-30"),
    lambda text: text.replace("- 截止时间：17:00", "- 截止时间：25:00"),
    lambda text: text.replace("- 创建时间：2026-09-30 09:00:00", "- 创建时间："),
    lambda text: text.replace("## TODO-7", "## TODO-0"),
    lambda text: text.replace("- 唯一标识：existing-record-7", "- 唯一标识："),
    lambda text: text.replace("### 内容", "### 其他"),
    lambda text: text.replace("- 状态：pending", "- 状态：pending\n- 状态：done"),
    lambda text: text.replace("- 状态：pending", "- 状态：pending\n- 未识别字段：业务信息"),
])
def test_partial_or_invalid_snapshot_is_rejected(mutation):
    with pytest.raises(ValueError):
        validate_todo_backup(mutation(todo_db.build_markdown_backup([record()])))


def test_duplicate_numeric_ids_and_uids_are_rejected():
    for second in (record(uid="distinct"), record(id=8)):
        with pytest.raises(ValueError, match="重复标识"):
            validate_todo_backup(todo_db.build_markdown_backup([record(), second]))


def test_legacy_uidless_snapshot_remains_compatible():
    text = todo_db.build_markdown_backup([record()])
    text = text.replace("- 唯一标识：existing-record-7\n", "")
    parsed = validate_todo_backup(text)
    assert parsed[0]["id"] == 7
    assert todo_db.record_uid(parsed[0])


def test_count_like_body_text_is_preserved():
    parsed = validate_todo_backup(todo_db.build_markdown_backup([record(content="正文\n- 记录数量：5")]))
    assert parsed[0]["content"] == "正文\n- 记录数量：5"


def test_content_separator_inside_body_is_preserved():
    body = "正文第一段\n### 内容\n正文第二段"
    parsed = validate_todo_backup(todo_db.build_markdown_backup([record(content=body)]))
    assert parsed[0]["content"] == body


def test_zero_count_does_not_hide_corrupt_nonrecord_text():
    with pytest.raises(ValueError):
        validate_todo_backup(todo_db.build_markdown_backup([]) + "未识别的业务记录\n")
