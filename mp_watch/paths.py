# -*- coding: utf-8 -*-
"""仓库根路径与默认数据路径（强制落在项目目录，避免写入 C 盘）。"""

from __future__ import annotations

from pathlib import Path

# E:\github\yao_1
REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "mp_watch_sources.json"
DEFAULT_STATE_PATH = REPO_ROOT / "data" / "mp_watch_state.json"
DEFAULT_LOG_DIR = REPO_ROOT / "logs"
