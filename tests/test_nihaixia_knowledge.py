import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.build_nihaixia_library import clean_markdown, domain_for
from utils import nihaixia_knowledge as kb


ROOT = Path(__file__).resolve().parents[1]


def example_library():
    entries = [
        {"id": "guide:a", "title": "体系导航", "kind": "总纲", "domain": "framework", "order": 0,
         "body": "私有正文标记：先定主体，再分时间层次。", "sources": []},
        {"id": "rule:a", "title": "条件相同仍需辨主体", "kind": "规则", "domain": "ziwei",
         "body": "具体例外完整保留；特别关键词：甲乙条件。", "sources": ["示例教材 · 第1页"]},
    ]
    part = kb.pack_part(entries)
    revision = kb.digest(kb.canonical_json(entries))
    manifest = {"schema_version": 1, "revision": revision, "updated_on": "2026-10-30",
                "parts": [{"path": f"data/nihaixia/releases/{revision}/part-000.json", "sha256": kb.digest(part)}],
                "counts": {"entries": 2, "rules": 1, "chapters": 1, "comparisons": 0, "source_documents": 1},
                "domains": {"framework": 1, "ziwei": 1}}
    return {"manifest": manifest, "entries": entries}, part


def test_package_round_trip_preserves_complete_body():
    library, part = example_library()
    manifest = kb.validate_manifest(library["manifest"])
    restored = kb.unpack_part(part, manifest["parts"][0]["sha256"])
    assert kb.validate_entries(restored, manifest) == library["entries"]


def test_tampered_or_cross_revision_volume_is_rejected():
    library, part = example_library()
    with pytest.raises(ValueError):
        kb.unpack_part(part + " ", library["manifest"]["parts"][0]["sha256"])
    library["manifest"]["parts"][0]["path"] = "data/other_private_ledger.json"
    with pytest.raises(ValueError):
        kb.validate_manifest(library["manifest"])


def test_duplicate_ids_missing_entries_and_changed_bodies_are_rejected():
    library, _ = example_library()
    with pytest.raises(ValueError):
        kb.validate_entries(library["entries"] * 2, library["manifest"])
    with pytest.raises(ValueError):
        kb.validate_entries(library["entries"][:1], library["manifest"])
    library["entries"][1]["body"] = "正文被截断"
    with pytest.raises(ValueError):
        kb.validate_entries(library["entries"], library["manifest"])


def test_full_text_search_finds_exception_not_just_title():
    library, _ = example_library()
    results = kb.search_entries(library["entries"], "例外 甲乙条件", domain="ziwei", kinds={"规则"})
    assert [entry["id"] for entry in results] == ["rule:a"]
    assert kb.search_entries(library["entries"], "甲乙条件", domain="earth") == []
    assert "特别关键词：甲乙条件" in kb.export_markdown(results)


def test_cleaning_discards_accounting_but_preserves_theory_and_uncertainty():
    source = """# 第37轮：主题
## 学习量与验收
一百小时、三十文件。
### 明细
执行流水。
## 二、条件与反例
在甲条件下成立；在乙条件下不成立。
### 未决问题
规则只及第一年，后续仍缺。
"""
    body, omitted = clean_markdown(source)
    assert "一百小时" not in body and "执行流水" not in body
    assert "在乙条件下不成立" in body and "后续仍缺" in body
    assert omitted == ["学习量与验收"]


def test_report_title_and_mixed_boundary_heading_cannot_hide_theory():
    body, _ = clean_markdown("# 第37轮实际研习报告\n## 仍然未决与下一轮入口\n阴阳分支尚缺。\n## 来源与实际阅读范围\n版本不同不可混用。")
    assert "阴阳分支尚缺" in body and "版本不同不可混用" in body


def test_supplementary_authors_are_not_classified_as_ni_school_rules():
    assert domain_for("白宝全四柱六神用法", hint="minggua") == "supplements"
    assert domain_for("罗经透解", hint="dimaidao") == "supplements"


def test_public_repository_is_rejected_before_content_read():
    session = Mock()
    with pytest.raises(ValueError):
        kb.private_connection(environ={"GITHUB_BACKUP_TOKEN": "test-only", "GITHUB_BACKUP_REPO": "yaoy2/yao_1"},
                              session=session)
    session.get.assert_not_called()
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = {"private": False, "full_name": kb.PRIVATE_REPO}
    with pytest.raises(ValueError):
        kb.private_connection(environ={"GITHUB_BACKUP_TOKEN": "test-only"}, session=session)
    assert session.get.call_count == 1


def test_page_password_gate_precedes_loading_and_logout_removes_content(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from utils import budget_auth

    library, _ = example_library()
    loader = Mock(return_value=library)
    monkeypatch.setattr(kb, "load_library", loader)
    monkeypatch.setattr(budget_auth, "get_budget_password", lambda *args: "unit-test-password")
    app = AppTest.from_file(str(ROOT / "pages/31_32_nihaixia_knowledge.py"), default_timeout=15).run()
    assert not app.exception
    loader.assert_not_called()
    app.text_input[0].set_value("wrong")
    app.button(key="FormSubmitter:m32_login-进入知识库").click().run()
    loader.assert_not_called()
    assert app.error
    app.text_input[0].set_value("unit-test-password")
    app.button(key="FormSubmitter:m32_login-进入知识库").click().run()
    assert not app.exception
    assert loader.call_count == 1
    assert any("私有正文标记" in element.value for element in app.markdown)
    next(button for button in app.button if button.label == "退出访问").click().run()
    assert not app.exception
    assert not any("私有正文标记" in element.value for element in app.markdown)
    assert "m32_library" not in app.session_state


def test_missing_or_rotated_password_clears_previous_session(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from utils import budget_auth

    loader = Mock()
    monkeypatch.setattr(kb, "load_library", loader)
    monkeypatch.setattr(budget_auth, "get_budget_password", lambda *args: None)
    app = AppTest.from_file(str(ROOT / "pages/31_32_nihaixia_knowledge.py"), default_timeout=15)
    app.session_state["m32_authenticated"] = "old-fingerprint"
    app.session_state["m32_library"] = example_library()[0]
    app.run()
    assert not app.exception
    loader.assert_not_called()
    assert "m32_library" not in app.session_state
