# -*- coding: utf-8 -*-
"""监控状态：已见 URL / 归档结果（JSON，存在仓库 data/ 下）。"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "items": {},
        "last_run": {
            "at": "",
            "discovered": 0,
            "archived": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        },
    }


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return default_state()
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return default_state()
    data = json.loads(raw)
    if not isinstance(data, dict):
        return default_state()
    base = default_state()
    base["items"] = data.get("items") if isinstance(data.get("items"), dict) else {}
    if isinstance(data.get("last_run"), dict):
        base["last_run"].update(data["last_run"])
    base["version"] = data.get("version", 1)
    return base


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(state)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def get_item(state: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    items = state.get("items") or {}
    item = items.get(key)
    return item if isinstance(item, dict) else None


def upsert_item(state: Dict[str, Any], key: str, **fields: Any) -> Dict[str, Any]:
    items = state.setdefault("items", {})
    current = items.get(key)
    if not isinstance(current, dict):
        current = {
            "url": fields.get("url", key),
            "title": "",
            "source_name": "",
            "first_seen": utc_now_iso(),
            "status": "seen",
            "path": "",
            "fail_count": 0,
            "last_error": "",
            "archived_at": "",
            "updated_at": utc_now_iso(),
        }
    current.update({k: v for k, v in fields.items() if v is not None})
    current["updated_at"] = utc_now_iso()
    items[key] = current
    return current
