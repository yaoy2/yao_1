# -*- coding: utf-8 -*-
"""读取 mp_watch 配置（仓库 config/ 下，E 盘项目内）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .paths import DEFAULT_CONFIG_PATH, DEFAULT_LOG_DIR, DEFAULT_STATE_PATH, REPO_ROOT


REQUIRED_SOURCE_KEYS = ("name", "kind", "feed_url")


def default_config() -> Dict[str, Any]:
    return {
        "poll_hours": 2,
        "archive_type": "raw",
        "headless": True,
        "max_new_per_run": 10,
        "retry_failed": True,
        "max_fail_count": 5,
        "request_timeout": 30,
        "archive_interval": 2.0,
        "state_path": str(DEFAULT_STATE_PATH),
        "log_dir": str(DEFAULT_LOG_DIR),
        # 可选：覆盖 wechat_core.TARGET_DIRS，方便 D/L 两台机器路径不同
        # 例：{"raw": "D:\\\\GoogleDrive\\\\Obsidian Vault\\\\00\\\\LLM_WIKI\\\\raw"}
        "target_dirs": {},
        "sources": [],
    }


def load_config(path: Path | None = None) -> Dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"找不到配置文件：{cfg_path}\n"
            f"请复制 config/mp_watch_sources.example.json 为 mp_watch_sources.json 并填写两个公众号的 RSS。"
        )
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("配置文件根节点必须是 JSON 对象")

    cfg = default_config()
    for key in (
        "poll_hours",
        "archive_type",
        "headless",
        "max_new_per_run",
        "retry_failed",
        "max_fail_count",
        "request_timeout",
        "archive_interval",
        "state_path",
        "log_dir",
        "target_dirs",
        "sources",
    ):
        if key in data:
            cfg[key] = data[key]

    # 相对路径一律相对仓库根，避免落到 C 盘 cwd
    cfg["state_path"] = str(_resolve_under_repo(cfg["state_path"]))
    cfg["log_dir"] = str(_resolve_under_repo(cfg["log_dir"]))
    cfg["_config_path"] = str(cfg_path)
    cfg["_repo_root"] = str(REPO_ROOT)

    target_dirs = cfg.get("target_dirs") or {}
    if target_dirs and not isinstance(target_dirs, dict):
        raise ValueError("target_dirs 必须是对象，例如 {\"raw\": \"D:\\\\path\\\\to\\\\raw\"}")
    normalized_dirs: Dict[str, str] = {}
    for k, v in dict(target_dirs).items():
        if v:
            normalized_dirs[str(k)] = str(v)
    cfg["target_dirs"] = normalized_dirs

    sources = cfg.get("sources") or []
    if not isinstance(sources, list):
        raise ValueError("sources 必须是数组")
    normalized: List[Dict[str, Any]] = []
    for idx, src in enumerate(sources):
        if not isinstance(src, dict):
            raise ValueError(f"sources[{idx}] 必须是对象")
        item = {
            "name": str(src.get("name") or f"source_{idx + 1}"),
            "kind": str(src.get("kind") or "rss").lower(),
            "feed_url": str(src.get("feed_url") or "").strip(),
            "enabled": bool(src.get("enabled", True)),
            "archive_type": str(src.get("archive_type") or cfg["archive_type"]),
        }
        if item["enabled"] and not item["feed_url"]:
            raise ValueError(f"sources[{idx}] ({item['name']}) 已启用但缺少 feed_url")
        if item["kind"] not in {"rss", "json"}:
            raise ValueError(f"sources[{idx}] kind 仅支持 rss / json，收到：{item['kind']}")
        # note 等扩展字段保留，便于配置里写备注
        if src.get("note"):
            item["note"] = str(src["note"])
        normalized.append(item)
    cfg["sources"] = normalized
    return cfg


def enabled_sources(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in cfg.get("sources", []) if s.get("enabled")]


def _resolve_under_repo(path_value: str | Path) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        # 允许绝对路径，但强烈建议仍在 E: 项目或数据盘
        return p
    return (REPO_ROOT / p).resolve()
