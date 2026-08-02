from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def artifact_path(directory: Path, code: str) -> Path:
    if not code.isdigit():
        raise ValueError("股票代码必须只包含数字。")
    return directory / f"{code}.json"


def write_forecast_artifact(
    directory: Path,
    code: str,
    artifact: dict[str, Any],
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = artifact_path(directory, code)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def load_forecast_artifact(
    directory: Path,
    code: str,
) -> dict[str, Any] | None:
    target = artifact_path(directory, code)
    if not target.exists():
        return None
    content = json.loads(target.read_text(encoding="utf-8"))
    if content.get("code") != code:
        raise ValueError(f"预测文件股票代码不匹配: {target}")
    return content
