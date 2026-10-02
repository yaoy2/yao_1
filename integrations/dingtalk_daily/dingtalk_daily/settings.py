"""Private machine configuration, deliberately separate from public code."""
from __future__ import annotations

from datetime import timedelta, timezone
import json
import os
from pathlib import Path

CHINA = timezone(timedelta(hours=8), "Asia/Shanghai")
PROJECT_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_DIR.parents[1]
DEFAULT_CONFIG = PROJECT_DIR / "config.local.json"


def output_path(value: str, *, repository: Path = REPOSITORY_ROOT) -> Path:
    """Reject output in the public checkout, including links resolving into it."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("必须配置本机输出目录。")
    path = Path(os.path.expandvars(value)).expanduser()
    if not path.is_absolute():
        raise ValueError("输出目录必须为绝对路径。")
    path = path.resolve()
    if path == repository.resolve() or repository.resolve() in path.parents:
        raise ValueError("聊天结果不能保存在公开代码仓库内，请使用本机私人目录。")
    return path


def defaults() -> dict:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        local = str(Path.home() / ".local" / "share")
    return {
        "version": 1,
        "priority_contact": "",
        "self_group": "",
        "self_names": [],
        "output_dir": str(Path(local) / "YaoTools" / "DingTalkDaily"),
        "calibration_ok": False,
        "ui": {},
    }


def validate(config: dict) -> dict:
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValueError("配置格式不正确，请先运行 configure。")
    for key in ("priority_contact", "self_group"):
        val = config.get(key)
        if not isinstance(val, str) or not val.strip() or len(val) > 200:
            raise ValueError(f"配置 {key} 必须是完整的会话名称。")
        if any(ch in val for ch in "\r\n\0"):
            raise ValueError(f"配置 {key} 不能含换行或控制字符。")
    if config["priority_contact"] == config["self_group"]:
        raise ValueError("指定联系人和指定群不能同名。")
    names = config.get("self_names")
    if not isinstance(names, list) or not names or any(
        not isinstance(name, str) or not name.strip() or len(name) > 200
        or any(ch in name for ch in "\r\n\0") for name in names
    ):
        raise ValueError("请填写本人在钉钉里的准确显示姓名，可配置多个别名。")
    if not isinstance(config.get("ui"), dict):
        raise ValueError("ui 配置必须是对象。")
    if not isinstance(config.get("calibration_ok"), bool):
        raise ValueError("calibration_ok 必须是布尔值。")
    output_path(config.get("output_dir", ""))
    return config


def load(path: Path = DEFAULT_CONFIG) -> dict:
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            return validate(json.load(stream))
    except FileNotFoundError as exc:
        raise ValueError("缺少本机配置，请先运行 setup.ps1 或 main.py configure。") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("本机配置不是有效 JSON，请检查 config.local.json。") from exc


def safe_config_target(path: Path) -> Path:
    path = path.resolve()
    if path == REPOSITORY_ROOT or REPOSITORY_ROOT in path.parents:
        if PROJECT_DIR not in path.parents or not path.name.endswith(".local.json"):
            raise ValueError("仓库内私人配置只能保存在本项目被忽略的 *.local.json 文件。")
    return path
