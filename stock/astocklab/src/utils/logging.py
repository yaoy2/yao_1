from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from src.utils.config import PROJECT_ROOT, load_settings


_CONFIGURED: set[str] = set()


def configure_logging(channel: str = "data") -> None:
    """Configure terminal, channel, and error logs once per process."""
    if channel in _CONFIGURED:
        return
    log_dir: Path = load_settings()["resolved_paths"]["logs"]
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {module}:{function}:{line} | {message}"
    logger.add(sys.stderr, format=fmt, level="INFO", colorize=True)
    logger.add(log_dir / f"{channel}.log", format=fmt, level="INFO", rotation="10 MB", encoding="utf-8")
    logger.add(log_dir / "errors.log", format=fmt, level="ERROR", rotation="10 MB", encoding="utf-8")
    _CONFIGURED.add(channel)


def project_path(path: str | Path) -> Path:
    """Return a safe absolute path inside the project."""
    candidate = (PROJECT_ROOT / path).resolve()
    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise ValueError(f"路径超出项目目录: {candidate}")
    return candidate
