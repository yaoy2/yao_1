import ast
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from utils.ding2026_showcase import SNAPSHOT_FIELDS, load_public_snapshot


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "19_20_ding2026.py"
SNAPSHOT = ROOT / "assets" / "ding2026_m20_snapshot.json"
VALID_SNAPSHOT = {
    "schema_version": "1",
    "project_version": "v1.1.0",
    "generated_at": "2026-08-31 00:55",
    "logical_files": 4293,
    "instances": 6721,
    "pending": 714,
    "invoices": 60,
    "official_docs": 96,
    "operations": 2920,
    "root_left": 0,
}


def write_snapshot(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_load_public_snapshot_accepts_only_the_desensitized_aggregate(tmp_path):
    path = tmp_path / "snapshot.json"
    write_snapshot(path, VALID_SNAPSHOT)

    assert load_public_snapshot(path) == VALID_SNAPSHOT
    assert set(VALID_SNAPSHOT) == SNAPSHOT_FIELDS


def test_load_public_snapshot_rejects_an_unapproved_field(tmp_path):
    path = tmp_path / "snapshot.json"
    write_snapshot(path, {**VALID_SNAPSHOT, "root_path": "sensitive"})

    assert load_public_snapshot(path) is None


def test_load_public_snapshot_rejects_invalid_counts_and_strings(tmp_path):
    path = tmp_path / "snapshot.json"
    invalid_payloads = [
        {**VALID_SNAPSHOT, "pending": -1},
        {**VALID_SNAPSHOT, "operations": True},
        {**VALID_SNAPSHOT, "generated_at": ""},
    ]

    for payload in invalid_payloads:
        write_snapshot(path, payload)
        assert load_public_snapshot(path) is None


def test_load_public_snapshot_falls_back_for_missing_or_malformed_files(tmp_path):
    missing = tmp_path / "missing.json"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")

    assert load_public_snapshot(missing) is None
    assert load_public_snapshot(malformed) is None


def test_repository_snapshot_uses_the_public_contract():
    assert load_public_snapshot(SNAPSHOT) == VALID_SNAPSHOT


def test_m20_page_explains_the_transfer_workflow_and_safety_boundary():
    app = AppTest.from_file(str(PAGE), default_timeout=10)
    app.run()

    assert not app.exception
    assert app.title[0].value == "M20 · Ding2026 文件中转发放系统"
    visible_text = "\n".join(
        item.value
        for collection in (app.markdown, app.info, app.warning, app.caption, app.subheader)
        for item in collection
    )
    for phrase in (
        "本页仅展示",
        "它能做什么",
        "日常怎么用",
        "五条时间轴",
        "90_中转",
        "永不自动删除",
    ):
        assert phrase in visible_text
    assert len(app.metric) >= 5


def test_m20_page_has_no_operational_controls_or_runtime_dependencies():
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    forbidden_calls = {
        "button",
        "download_button",
        "file_uploader",
        "form",
        "form_submit_button",
        "link_button",
        "switch_page",
    }
    streamlit_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
    }
    assert streamlit_calls.isdisjoint(forbidden_calls)

    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(name == "ding2026" or name.startswith("ding2026.") for name in imported_modules)
    source = PAGE.read_text(encoding="utf-8")
    assert "127.0.0.1" not in source
    assert "E:\\github\\ding2026-system" not in source

