# -*- coding: utf-8 -*-
"""日志写到仓库 logs/，不写 C 盘。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def log_line(log_dir: Path, message: str, name: str = "mp_watch") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    path = log_dir / f"{name}_{day}.log"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {message.rstrip()}\n")
    return path
