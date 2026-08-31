"""Public-data boundary for the M20 Ding2026 showcase."""

from __future__ import annotations

import json
from pathlib import Path


STRING_FIELDS = ("schema_version", "project_version", "generated_at")
COUNT_FIELDS = (
    "logical_files",
    "instances",
    "pending",
    "invoices",
    "official_docs",
    "operations",
    "root_left",
)
SNAPSHOT_FIELDS = frozenset((*STRING_FIELDS, *COUNT_FIELDS))


def load_public_snapshot(path: str | Path) -> dict[str, str | int] | None:
    """Return a validated public aggregate snapshot, or ``None``."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict) or set(payload) != SNAPSHOT_FIELDS:
        return None
    if any(
        not isinstance(payload[name], str) or not payload[name].strip()
        for name in STRING_FIELDS
    ):
        return None
    for name in COUNT_FIELDS:
        value = payload[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
    return payload
