import gzip
import hashlib
import json
from pathlib import Path

import duckdb
from streamlit.testing.v1 import AppTest

from stock.portal import is_usable_heat_payload
from stock.search_html.collector import chromium_executable, search_archive


ROOT = Path(__file__).resolve().parents[1]
STOCK_ROOT = ROOT / "stock"


def test_stock_page_exposes_two_sections_without_a_second_page_config():
    page = (ROOT / "pages" / "18_19_stock_portal.py").read_text(encoding="utf-8")
    portal = (STOCK_ROOT / "portal.py").read_text(encoding="utf-8")
    online_app = (STOCK_ROOT / "astocklab" / "online_app.py").read_text(encoding="utf-8")
    assert 'page_title="股票研究中心"' in page
    assert '["AStockLab", "股票搜索"]' in portal
    assert "st.set_page_config" not in online_app
    assert "materialize_astocklab_database()" in online_app
    assert "st.radio" in online_app
    assert "horizontal=True" in online_app
    assert "力诺药包与信息发展" in online_app
    assert "st.sidebar.radio" not in online_app


def test_stock_page_reuses_the_shared_password_gate():
    page = (ROOT / "pages" / "18_19_stock_portal.py").read_text(encoding="utf-8")
    assert "from utils import budget_auth" in page
    assert "budget_auth.get_budget_password(st.secrets, os.environ)" in page
    assert "budget_auth.is_budget_password_valid" in page
    assert "stock_portal_authenticated" in page
    assert page.rindex("require_stock_portal_auth()") < page.rindex("render_stock_portal()")


def test_stock_page_unlocks_and_switches_to_the_second_stock(monkeypatch):
    monkeypatch.setenv("BUDGET_PASSWORD", "stock-test-password")
    page = ROOT / "pages" / "18_19_stock_portal.py"
    app = AppTest.from_file(str(page), default_timeout=30).run()

    assert not app.exception
    assert [field.label for field in app.text_input] == ["访问密码"]
    app.text_input[0].input("stock-test-password")
    app.button[0].click().run()

    assert not app.exception
    selector = next(
        radio for radio in app.radio
        if radio.key == "astocklab_selected_stock"
    )
    assert [option[-10:-4] for option in selector.options] == ["301188", "300469"]
    comparison = next(
        radio for radio in app.radio
        if radio.key == "market_comparison_mode"
    )
    assert comparison.options == ["累计收益率（%）", "归一化走势（首日=100）"]
    assert comparison.value == "累计收益率（%）"
    selector.set_value(selector.options[1]).run()
    assert not app.exception
    assert any("300469" in item.value for item in app.subheader)

    section = next(
        control for control in app.segmented_control
        if control.key == "stock_portal_section"
    )
    section.set_value(section.options[1]).run()
    assert not app.exception
    assert any(button.key == "refresh_stock_heat" for button in app.button)


def test_compressed_astocklab_snapshot_matches_manifest(tmp_path):
    online = STOCK_ROOT / "astocklab" / "data" / "online"
    manifest = json.loads((online / "snapshot_manifest.json").read_text(encoding="utf-8"))
    compressed = online / "astock.duckdb.gz"
    assert compressed.stat().st_size == manifest["compressed_size"]
    assert hashlib.sha256(compressed.read_bytes()).hexdigest() == manifest["compressed_sha256"]

    digest = hashlib.sha256()
    size = 0
    extracted = tmp_path / "astock.duckdb"
    with gzip.open(compressed, "rb") as source, extracted.open("wb") as target:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
            target.write(chunk)
    assert size == manifest["database_size"]
    assert digest.hexdigest() == manifest["database_sha256"]

    with duckdb.connect(str(extracted), read_only=True) as connection:
        rows = dict(connection.execute(
            "SELECT code, COUNT(*) FROM daily_bars "
            "WHERE code IN ('301188', '300469') GROUP BY code"
        ).fetchall())
    assert rows["301188"] > 0
    assert rows["300469"] > 0


def test_search_snapshot_and_archive_query_are_available():
    latest = json.loads(
        (STOCK_ROOT / "search_html" / "data" / "latest.json").read_text(encoding="utf-8")
    )
    assert latest["hotspots"]
    assert set(latest["ai_pool"]) == {"confirmed", "disputed"}
    result = search_archive("300058", "heat")
    assert result["count"] >= 1
    assert {item["source"] for item in result["results"]}.issubset({"雪球", "淘股吧"})


def test_heat_refresh_rejects_all_failed_or_empty_payloads():
    assert not is_usable_heat_payload({
        "source_health": [
            {"source": "雪球", "status": "error"},
            {"source": "淘股吧", "status": "error"},
        ],
        "hotspots": [],
        "evidence": [],
    })
    assert not is_usable_heat_payload({
        "source_health": [{"source": "雪球", "status": "ok"}],
        "hotspots": [],
        "evidence": [],
    })
    assert is_usable_heat_payload({
        "source_health": [
            {"source": "雪球", "status": "degraded"},
            {"source": "淘股吧", "status": "error"},
        ],
        "hotspots": [{"source": "雪球"}],
        "evidence": [],
    })


def test_search_page_exposes_manual_heat_refresh_without_writing_snapshot():
    portal = (STOCK_ROOT / "portal.py").read_text(encoding="utf-8")
    assert '"采集最新热度"' in portal
    assert '"恢复发布快照"' in portal
    assert 'st.session_state["stock_live_heat_payload"]' in portal
    assert "is_usable_heat_payload(refreshed)" in portal
    assert "write_snapshot" not in portal


def test_online_search_accepts_an_explicit_chromium_path(tmp_path, monkeypatch):
    executable = tmp_path / "chromium"
    executable.write_bytes(b"test executable placeholder")
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", str(executable))
    assert chromium_executable() == str(executable)
    assert "chromium" in (ROOT / "packages.txt").read_text(encoding="utf-8")


def test_stock_module_does_not_commit_runtime_artifacts():
    forbidden = {".duckdb", ".wal", ".log", ".tmp"}
    offenders = [
        path for path in STOCK_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden
    ]
    assert offenders == []
