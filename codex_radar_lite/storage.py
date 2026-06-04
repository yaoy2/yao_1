from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import RadarState


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_previous_state(data_dir: Path) -> RadarState | None:
    path = data_dir / "codex_radar_current.json"
    if not path.exists():
        return None
    return RadarState.from_dict(read_json(path, {}))


def load_history(data_dir: Path) -> list[dict[str, Any]]:
    return list(read_json(data_dir / "codex_radar_history.json", []))


def save_outputs(data_dir: Path, state: RadarState, history: list[dict[str, Any]]) -> None:
    write_json(data_dir / "codex_radar_current.json", state.to_dict())
    write_json(data_dir / "codex_radar_signals.json", [signal.to_dict() for signal in state.signals])
    write_json(data_dir / "codex_radar_history.json", history)


def update_history(history: list[dict[str, Any]], state: RadarState) -> list[dict[str, Any]]:
    if state.status not in {"open", "closed", "high_probability"}:
        return history[:50]
    event = {
        "status": state.status,
        "checked_at": state.checked_at,
        "closed_at": state.checked_at if state.status == "closed" else None,
        "probability_24h": state.probability_24h,
        "probability_48h": state.probability_48h,
        "reason": state.reason,
    }
    if history and history[0].get("status") == state.status:
        history[0] = event
    else:
        history.insert(0, event)
    return history[:50]

