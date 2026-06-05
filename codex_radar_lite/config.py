from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_RULES = {
    "high_probability_threshold": 60,
    "watch_threshold": 25,
    "cooldown_hours_after_closed": 24,
    "keywords": {
        "open": [
            "will reset",
            "resetting limits",
            "reset rate limits",
            "reset usage limits",
            "reset codex",
        ],
        "closed": [
            "limits have been reset",
            "usage limits have been reset",
            "rate limits have been reset",
            "restored to 100%",
            "fully recovered",
        ],
        "codex": ["codex", "codex cloud", "codex compaction"],
        "limit": ["limit", "limits", "rate limit", "usage limit", "quota", "credit"],
        "incident": ["incident", "elevated errors", "latency", "degraded", "recovered"],
    },
}


DEFAULT_SOURCES = {
    "sources": [
        {
            "id": "openai_status_history",
            "name": "OpenAI Status Incidents",
            "url": "https://status.openai.com/api/v2/incidents.json",
            "kind": "statuspage_incidents",
            "weight": 40,
            "enabled": True,
                "keywords": ["codex", "usage limit", "rate limit", "quota", "credit"],
        }
    ]
}


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_rules(config_dir: Path) -> dict[str, Any]:
    return load_json(config_dir / "codex_radar_rules.json", DEFAULT_RULES)


def load_sources(config_dir: Path) -> dict[str, Any]:
    return load_json(config_dir / "codex_radar_sources.json", DEFAULT_SOURCES)
