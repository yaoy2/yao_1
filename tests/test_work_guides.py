from copy import deepcopy
import json

import pytest

from utils import work_guides as guides
from utils.data_sync_validation import MANAGED_FILES, validate_backup, would_drop_records


def example():
    document, gid = guides.update_guide(guides.empty_document(), {"title": "年度申报", "category": "行政", "contacts": "业务联系人"})
    document, first = guides.update_step(document, gid, {"title": '读通知 "原文"', "action": "核对当年要求"})
    document, second = guides.update_step(document, gid, {"title": "报送", "output": "接收回执", "branch_to": first, "branch_label": "退回补充"})
    return document, gid, first, second


def test_edits_preserve_children_and_never_mutate_the_previous_document():
    before, gid, first, _second = example()
    saved = deepcopy(before)
    after, _ = guides.update_guide(before, {"title": "新名称", "verified_on": "2026-11-17"}, gid)
    assert before == saved
    assert after["revision"] == before["revision"] + 1
    assert after["guides"][0]["steps"] == before["guides"][0]["steps"]
    after, same_id = guides.update_step(after, gid, {"action": "新做法"}, first)
    assert same_id == first and after["guides"][0]["steps"][0]["action"] == "新做法"
    assert before["guides"][0]["steps"][0]["action"] == "核对当年要求"


def test_historical_snapshot_survives_future_guide_node_and_record_edits():
    document, gid, first, _ = example()
    document, rid = guides.update_record(document, gid, {"period": "2026年度", "title": "首轮报送", "receipt": "待对方确认"})
    original = deepcopy(document["guides"][0]["records"][0]["guide_snapshot"])
    document, _ = guides.update_guide(document, {"requirements": "新一年的要求"}, gid)
    document, _ = guides.update_step(document, gid, {"action": "新一年做法"}, first)
    document, _ = guides.update_record(document, gid, {"status": "已完成", "next_tips": "提前一周收集"}, rid)
    record = document["guides"][0]["records"][0]
    assert record["guide_snapshot"] == original
    assert "records" not in original
    assert record["status"] == "已完成"
    assert guides.validate_document(json.loads(guides.serialize(document))) == document


def test_flow_reordering_branches_and_disabled_nodes():
    document, gid, first, second = example()
    dot = guides.flow_dot(document["guides"][0], second)
    assert f'"{first}" -> "{second}"' in dot
    assert f'"{second}" -> "{first}"' in dot
    assert 'style=dashed' in dot and '\\"原文\\"' in dot
    after = guides.move_step(document, gid, second, -1)
    assert [s["id"] for s in after["guides"][0]["steps"]] == [second, first]
    with pytest.raises(ValueError):
        guides.move_step(after, gid, second, -1)
    with pytest.raises(ValueError, match="分支目标"):
        guides.update_step(document, gid, {"enabled": False}, first)
    after, _ = guides.update_step(document, gid, {"branch_to": "", "branch_label": "", "continue_next": False}, second)
    after, _ = guides.update_step(after, gid, {"enabled": False}, first)
    assert first not in guides.flow_dot(after["guides"][0])
    assert '->' not in guides.flow_dot(after["guides"][0])
    markdown = guides.guide_markdown(after["guides"][0])
    assert "已停用" in markdown and "在此结束主线" in markdown


@pytest.mark.parametrize("changes", [{"title": " "}, {"verified_on": "2026-02-30"}, {"id": "bad"}, {"archived": 1}])
def test_invalid_guide_changes_are_rejected(changes):
    with pytest.raises(ValueError):
        guides.update_guide(guides.empty_document(), changes)


def test_bad_or_duplicate_nested_data_is_not_treated_as_an_empty_guide():
    document, gid, first, _ = example()
    broken = deepcopy(document)
    broken["guides"][0]["steps"].append(deepcopy(broken["guides"][0]["steps"][0]))
    with pytest.raises(ValueError, match="重复"):
        guides.validate_document(broken)
    with pytest.raises(ValueError, match="分支目标"):
        guides.update_step(document, gid, {"branch_to": "f" * 32, "branch_label": "不通过"}, first)
    with pytest.raises(ValueError):
        guides.update_record(document, gid, {"period": "2026", "title": "报送", "status": "bogus"})


def test_guards_reject_removal_revision_jumps_and_rewriting_old_snapshots():
    document, gid, _, _ = example()
    document, _ = guides.update_record(document, gid, {"period": "2026", "title": "记录"})
    for kind in ("guides", "steps", "records"):
        removed = deepcopy(document)
        removed["revision"] += 1
        if kind == "guides":
            removed["guides"] = []
        elif kind == "steps":
            removed["guides"][0][kind].pop()
        else:
            removed["guides"][0][kind] = []
        assert would_drop_records(guides.REPO_PATH, document, removed)
        with pytest.raises(ValueError):
            guides.check_transition(document, removed)
    changed = deepcopy(document)
    changed["revision"] += 1
    changed["guides"][0]["records"][0]["guide_snapshot"]["title"] = "被改写的历史"
    with pytest.raises(ValueError, match="快照"):
        guides.check_transition(document, changed)
    with pytest.raises(ValueError, match="修订号"):
        guides.check_transition(document, document)


def test_search_archive_and_registered_private_backup():
    document, gid, _, _ = example()
    document, _ = guides.update_record(document, gid, {"period": "2025", "title": "历史报送", "notes": "特殊口径"})
    assert guides.search_guides(document, "2025 特殊口径")[0]["id"] == gid
    assert guides.search_guides(document, "业务联系人")[0]["id"] == gid
    archived, _ = guides.update_guide(document, {"archived": True}, gid)
    assert not guides.search_guides(archived)
    assert guides.search_guides(archived, include_archived=True)[0]["id"] == gid
    assert guides.REPO_PATH in MANAGED_FILES
    assert validate_backup(guides.REPO_PATH, guides.serialize(document)) == document


def test_capacity_failure_keeps_the_previous_document(monkeypatch):
    document, gid, _, _ = example()
    previous = deepcopy(document)
    monkeypatch.setattr(guides, "MAX_DOCUMENT_BYTES", 50)
    with pytest.raises(ValueError, match="容量"):
        guides.update_guide(document, {"summary": "内容"}, gid)
    assert document == previous
