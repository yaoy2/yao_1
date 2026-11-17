from copy import deepcopy
import hashlib
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from utils import budget_auth
from utils import work_guides as guides
from utils import work_guides_sync as cloud
from tests.test_work_guides import example


PAGE = Path(__file__).resolve().parents[1] / "pages" / "33_34_work_guides.py"
PASSWORD = "unit-test-password"


def button(app, label):
    return next(item for item in app.button if item.label == label)


def reopen(app):
    # Read each saved result in a fresh page, independently of widget memory.
    # AppTest's delta parser retains orphan widgets when an explicit rerun
    # changes a form layout (unlike the browser's end-of-run cleanup).
    fresh = AppTest.from_file(str(PAGE), default_timeout=20)
    fresh.session_state["m34_authenticated"] = hashlib.sha256(PASSWORD.encode()).hexdigest()
    if "m34_selected" in app.session_state:
        fresh.session_state["m34_selected"] = app.session_state["m34_selected"]
    fresh.run()
    assert not fresh.exception
    return fresh


def harness(monkeypatch, document=None, authenticated=True):
    state = {"document": deepcopy(document if document is not None else guides.empty_document()), "conflict": False}
    loader = Mock(side_effect=lambda **kwargs: {"ok": True, "document": deepcopy(state["document"]), "sha": "a" * 40})

    def save(document, expected_sha, **kwargs):
        if state["conflict"]:
            return {"ok": False, "conflict": True, "message": "其他设备已更新指南，本次未覆盖。"}
        guides.check_transition(state["document"], document)
        state["document"] = deepcopy(document)
        return {"ok": True, "document": deepcopy(document), "sha": "a" * 40}

    monkeypatch.setattr(cloud, "load_document", loader)
    monkeypatch.setattr(cloud, "save_document", Mock(side_effect=save))
    monkeypatch.setattr(budget_auth, "get_budget_password", lambda *args: PASSWORD)
    app = AppTest.from_file(str(PAGE), default_timeout=20)
    if authenticated:
        app.session_state["m34_authenticated"] = hashlib.sha256(PASSWORD.encode()).hexdigest()
    app.run()
    assert not app.exception
    return app, state, loader


def test_login_wrong_password_correct_password_and_logout(monkeypatch):
    document, _, _, _ = example()
    app, _state, loader = harness(monkeypatch, document, authenticated=False)
    loader.assert_not_called()
    app.text_input[0].set_value("wrong")
    button(app, "进入工作导航").click().run()
    assert app.error and not app.exception
    loader.assert_not_called()
    app.text_input[0].set_value(PASSWORD)
    button(app, "进入工作导航").click().run()
    assert not app.exception and loader.call_count == 1
    assert any("年度申报" in item.value for item in app.markdown)
    button(app, "退出访问").click().run()
    assert not app.exception
    assert "m34_document" not in app.session_state
    assert not any("年度申报" in item.value for item in app.markdown)


@pytest.mark.parametrize("password", [None, "rotated-password"])
def test_missing_or_changed_password_removes_old_data_and_draft(monkeypatch, password):
    document, _, _, _ = example()
    app, _state, loader = harness(monkeypatch, document)
    app.session_state["m34_draft"] = deepcopy(document)
    loader.reset_mock()
    monkeypatch.setattr(budget_auth, "get_budget_password", lambda *args: password)
    app.run()
    assert not app.exception
    loader.assert_not_called()
    assert "m34_document" not in app.session_state and "m34_draft" not in app.session_state


def test_create_and_edit_guide_nodes_and_yearly_record_through_forms(monkeypatch):
    app, state, _loader = harness(monkeypatch)
    button(app, "新增工作").click().run()
    app.text_input(key="m34_guide_new_0_title").set_value("年度工作")
    app.text_input(key="m34_guide_new_0_category").set_value("行政")
    button(app, "创建工作指南").click().run()
    assert not app.exception
    app = reopen(app)
    gid = state["document"]["guides"][0]["id"]
    prefix = f"m34_step_{gid}_new_1_"
    app.text_input(key=prefix + "title").set_value("读通知")
    app.text_area(key=prefix + "action").set_value("核对当年通知")
    button(app, "保存流程节点").click().run()
    assert not app.exception
    app = reopen(app)
    first = state["document"]["guides"][0]["steps"][0]["id"]
    prefix = f"m34_step_{gid}_new_2_"
    app.text_input(key=prefix + "title").set_value("报送")
    app.selectbox(key=prefix + "branch_to").set_value(first)
    app.text_input(key=prefix + "branch_label").set_value("退回补件")
    button(app, "保存流程节点").click().run()
    assert not app.exception
    app = reopen(app)
    record_prefix = f"m34_record_{gid}_new_3_"
    app.text_input(key=record_prefix + "period").set_value("2026年度")
    app.text_input(key=record_prefix + "title").set_value("本轮办理")
    app.text_area(key=record_prefix + "next_tips").set_value("下次提前收材料")
    button(app, "保存办理记录").click().run()
    assert not app.exception
    app = reopen(app)
    snapshot = deepcopy(state["document"]["guides"][0]["records"][0]["guide_snapshot"])
    app.selectbox(key=f"m34_edit_node_{gid}_4").set_value(first).run()
    node_prefix = f"m34_step_{gid}_{first}_4_"
    app.text_area(key=node_prefix + "action").set_value("下一年做法")
    button(app, "保存流程节点").click().run()
    assert not app.exception
    app = reopen(app)
    guide_prefix = f"m34_guide_{gid}_5_"
    app.text_input(key=guide_prefix + "title").set_value("年度工作指南")
    button(app, "保存工作指南").click().run()
    assert not app.exception
    app = reopen(app)
    rid = state["document"]["guides"][0]["records"][0]["id"]
    app.selectbox(key=f"m34_edit_record_{gid}_6").set_value(rid).run()
    app.text_area(key=f"m34_record_{gid}_{rid}_6_receipt").set_value("已确认收到")
    button(app, "保存办理记录").click().run()
    assert not app.exception
    app = reopen(app)
    saved = state["document"]["guides"][0]
    assert saved["title"] == "年度工作指南"
    assert saved["steps"][0]["action"] == "下一年做法"
    assert saved["records"][0]["receipt"] == "已确认收到"
    assert saved["records"][0]["guide_snapshot"] == snapshot
    button(app, "刷新云端").click().run()
    assert not app.exception
    assert app.session_state["m34_document"] == state["document"]


def test_conflict_retains_draft_blocks_edits_and_requires_acknowledgement_before_refresh(monkeypatch):
    document, gid, _, _ = example()
    app, state, _loader = harness(monkeypatch, document)
    button(app, "查看指南").click().run()
    state["conflict"] = True
    app.text_input(key=f"m34_guide_{gid}_3_title").set_value("未保存的新名称")
    button(app, "保存工作指南").click().run()
    assert not app.exception and app.error
    assert app.session_state["m34_draft"]["guides"][0]["title"] == "未保存的新名称"
    assert app.session_state["m34_document"] == document
    assert button(app, "保存工作指南").disabled and button(app, "刷新云端").disabled
    assert app.get("download_button")
    app.checkbox(key="m34_allow_refresh").check().run()
    button(app, "刷新云端").click().run()
    assert not app.exception
    assert "m34_draft" not in app.session_state
    assert app.session_state["m34_document"] == document


def test_node_reordering_and_archived_guides_remain_accessible(monkeypatch):
    document, gid, first, second = example()
    app, state, _loader = harness(monkeypatch, document)
    button(app, "查看指南").click().run()
    app = reopen(app)
    app.selectbox(key=f"m34_edit_node_{gid}_3").set_value(second).run()
    button(app, "上移").click().run()
    assert not app.exception
    assert [s["id"] for s in state["document"]["guides"][0]["steps"]] == [second, first]
    app = reopen(app)
    app.checkbox(key=f"m34_guide_{gid}_4_archived").check()
    button(app, "保存工作指南").click().run()
    assert not app.exception and state["document"]["guides"][0]["archived"]
    app = reopen(app)
    button(app, "← 返回工作列表").click().run()
    app = reopen(app)
    assert not any(item.label == "查看指南" for item in app.button)
    app.checkbox(key="m34_archived").check().run()
    assert not app.exception and button(app, "查看指南")
