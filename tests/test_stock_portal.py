import gzip
import hashlib
import json
from pathlib import Path

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


def test_compressed_astocklab_snapshot_matches_manifest():
    online = STOCK_ROOT / "astocklab" / "data" / "online"
    manifest = json.loads((online / "snapshot_manifest.json").read_text(encoding="utf-8"))
    compressed = online / "astock.duckdb.gz"
    assert compressed.stat().st_size == manifest["compressed_size"]
    assert hashlib.sha256(compressed.read_bytes()).hexdigest() == manifest["compressed_sha256"]

    digest = hashlib.sha256()
    size = 0
    with gzip.open(compressed, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    assert size == manifest["database_size"]
    assert digest.hexdigest() == manifest["database_sha256"]


def test_search_snapshot_and_archive_query_are_available():
    latest = json.loads(
        (STOCK_ROOT / "search_html" / "data" / "latest.json").read_text(encoding="utf-8")
    )
    assert latest["hotspots"]
    assert set(latest["ai_pool"]) == {"confirmed", "disputed"}
    result = search_archive("300058", "heat")
    assert result["count"] >= 1
    assert {item["source"] for item in result["results"]}.issubset({"雪球", "淘股吧"})


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
