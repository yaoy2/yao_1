"""Integrity checks for the actual reading corpus, independent of Streamlit."""

import ast
import hashlib
import json
from pathlib import Path
import re

import pytest
from pypdf import PdfReader

from scripts.build_life_guide import comparable_title, parse_section, pdf_locations, write_snapshot


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "integrations/life_guide/frontend"


@pytest.fixture(scope="module")
def corpus():
    return json.loads((FRONTEND / "guide.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def reader():
    return PdfReader(FRONTEND / "guide.pdf")


def test_snapshot_contains_the_complete_pdf_bookmark_index(corpus, reader):
    metadata = corpus["metadata"]
    sections, entries, documents = pdf_locations(reader)
    assert metadata["pdf_pages"] == len(reader.pages)
    assert metadata["printed_pages"] + metadata["page_offset"] == len(reader.pages)
    version = re.search(r"对应提交[：:]\s*([0-9a-f]{7,40})", reader.pages[-1].extract_text())[1]
    assert metadata["pdf_source_commit"] == version
    assert metadata["source_commit"].startswith(version)
    assert metadata["section_count"] == len(corpus["sections"]) == len(sections) == 34
    assert metadata["entry_count"] == len(corpus["entries"]) == len(entries) == 667
    assert {entry["id"] for entry in corpus["entries"]} == set(entries)
    assert metadata["documents_count"] == len(corpus["documents"]) == 9
    for entry in corpus["entries"]:
        bookmark = entries[entry["id"]]
        assert comparable_title(entry["title"]) == comparable_title(bookmark["title"])
        assert entry["pdf_page"] == bookmark["page"]
        assert 1 <= entry["pdf_page"] <= len(reader.pages)
    for document in corpus["documents"]:
        assert document["pdf_page"] == documents[comparable_title(document["title"])]["page"]


def test_original_pdf_and_skill_are_unchanged_and_attributed(corpus):
    metadata = corpus["metadata"]
    for filename, checksum in (("guide.pdf", "pdf_sha256"), ("skill.md", "skill_sha256")):
        assert hashlib.sha256((FRONTEND / filename).read_bytes()).hexdigest() == metadata[checksum]
    assert metadata["author"] == "eternity4719"
    assert metadata["license"] == "CC BY 4.0"
    assert re.fullmatch(r"[0-9a-f]{40}", metadata["source_commit"])
    assert "Creative Commons" in (FRONTEND / "LICENSE-CONTENT.txt").read_text(encoding="utf-8")
    assert "eternity4719" in (FRONTEND / "LICENSE-UPSTREAM-CODE.txt").read_text(encoding="utf-8")


def test_every_raw_entry_retains_all_fields_and_source_version(corpus):
    for entry in corpus["entries"]:
        assert entry["raw"].startswith(f"### {entry['n']}. {entry['title']}")
        for label, key in (("成本", "cost"), ("说人话", "human"), ("收益", "gain"),
                           ("来源", "src"), ("备注", "note")):
            assert entry[key], entry["id"]
            assert f"- {label}：{entry[key]}" in entry["raw"], entry["id"]
        assert entry["grade"] in "ABC"
        assert corpus["metadata"]["source_commit"] in entry["source_url"]
    # Qualifications are part of the result and the AI evidence packet.
    salt = next(e for e in corpus["entries"] if "换成低钠盐" in e["title"])
    assert "肾功能" in salt["note"]
    assert "保钾类药物" in salt["note"]
    guarantee = next(e for e in corpus["entries"] if e["id"] == "s8-e17")
    assert "担保" in guarantee["raw"]
    assert guarantee["pdf_page"] > corpus["metadata"]["page_offset"]


def test_parser_preserves_multiline_conditions_and_refuses_partial_records():
    text = """# 1. 测试节
这段是导读。
### 1. 示例
<!-- 成本标签: 钱=0 时间=少 毅力=否 收益=大 口径=时间 -->
- 成本：第一段
  成本的续行
- 说人话：说明
- 收益：原数值
- 证据等级：B
- 来源：https://example.com/source
- 备注：争议。仅适用于条件甲。

另一个不能遗漏的条件乙。
"""
    section, entries = parse_section(text, "book/01-test.md", "a" * 40)
    assert section["intro"] == "这段是导读。"
    assert "成本的续行" in entries[0]["cost"]
    assert "条件乙" in entries[0]["note"]
    assert entries[0]["dispute"]
    with pytest.raises(ValueError, match="Incomplete entry"):
        parse_section(text.replace("- 来源：", "- 出处："), "book/01-test.md", "a" * 40)


def test_page_uses_the_importable_component_and_pinned_local_assets():
    from streamlit.testing.v1 import AppTest

    source = (ROOT / "pages/28_29_life_decision_guide.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "render_home_link()" in source
    assert "from utils.life_guide_component import declare_life_guide_component" in source
    assert "streamlit run" not in source
    component = (ROOT / "utils/life_guide_component.py").read_text(encoding="utf-8")
    assert "components.declare_component" in component
    assert '"life_guide" / "frontend"' in component
    app = AppTest.from_file(str(ROOT / "pages/28_29_life_decision_guide.py")).run(timeout=15)
    assert not app.exception
    assert len(app.get("component_instance")) == 1


def test_snapshot_writer_can_reuse_delivered_pdf_and_leaves_old_output_on_missing_source(tmp_path):
    source = tmp_path / "upstream"
    skill_dir = source / "skills/life-decision-guide"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Rules", encoding="utf-8")
    (source / "LICENSE").write_text("Content attribution", encoding="utf-8")
    (source / "LICENSE-CODE").write_text("Code attribution", encoding="utf-8")
    output = tmp_path / "frontend"
    output.mkdir()
    pdf = output / "guide.pdf"
    pdf.write_bytes(b"%PDF-pretend-test-input")
    for _ in range(2):
        write_snapshot({"version": 1}, source, pdf, output)
    assert pdf.read_bytes() == b"%PDF-pretend-test-input"
    assert json.loads((output / "guide.json").read_text(encoding="utf-8")) == {"version": 1}
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    (source / "LICENSE-CODE").unlink()
    with pytest.raises(FileNotFoundError):
        write_snapshot({"version": 2}, source, pdf, output)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
