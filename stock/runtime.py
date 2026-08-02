"""Runtime isolation for the stock portal's bundled read-only snapshot."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sys
import tempfile
import threading
from functools import lru_cache
from pathlib import Path


STOCK_ROOT = Path(__file__).resolve().parent
ASTOCKLAB_ROOT = STOCK_ROOT / "astocklab"
SNAPSHOT_ROOT = ASTOCKLAB_ROOT / "data" / "online"
COMPRESSED_DATABASE = SNAPSHOT_ROOT / "astock.duckdb.gz"
MANIFEST_PATH = SNAPSHOT_ROOT / "snapshot_manifest.json"
VALIDATION_PATH = SNAPSHOT_ROOT / "latest_validation.json"
_MATERIALIZE_LOCK = threading.Lock()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def snapshot_manifest() -> dict[str, object]:
    """Return the checked metadata shipped with the online snapshot."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    required = {"database_sha256", "database_size", "snapshot_date"}
    missing = required.difference(manifest)
    if missing:
        raise RuntimeError(f"股票快照清单缺少字段：{', '.join(sorted(missing))}")
    return manifest


def materialize_astocklab_database() -> Path:
    """Decompress and verify DuckDB in an isolated temporary directory."""
    manifest = snapshot_manifest()
    expected_hash = str(manifest["database_sha256"]).lower()
    expected_size = int(manifest["database_size"])
    target_dir = Path(tempfile.gettempdir()) / "yaoyao-stock" / expected_hash[:16]
    target = target_dir / "astock.duckdb"

    def is_valid() -> bool:
        return (
            target.exists()
            and target.stat().st_size == expected_size
            and _sha256(target) == expected_hash
        )

    if is_valid():
        return target

    with _MATERIALIZE_LOCK:
        if is_valid():
            return target
        target_dir.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".duckdb.tmp")
        try:
            with gzip.open(COMPRESSED_DATABASE, "rb") as source, temporary.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            if temporary.stat().st_size != expected_size or _sha256(temporary) != expected_hash:
                raise RuntimeError("AStockLab 在线数据库快照校验失败。")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def activate_astocklab_imports() -> None:
    """Make the copied AStockLab source package importable without path drift."""
    root = str(ASTOCKLAB_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def online_validation_path() -> Path:
    return VALIDATION_PATH
