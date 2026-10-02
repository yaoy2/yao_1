"""Let the owner enter the local budget/TODO password without sending it to chat."""

import getpass
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils import budget_auth
from utils.github_backup_sync import _atomic_text


def configured_text(original, password):
    import json
    assignment = "budget_password = " + json.dumps(password, ensure_ascii=False)
    parsed = tomllib.loads(original)
    if "budget_password" in parsed:
        section = re.search(r"^\s*\[", original, re.M)
        boundary = section.start() if section else len(original)
        prefix = re.sub(r"^budget_password\s*=.*$", lambda match: assignment,
                        original[:boundary], count=1, flags=re.M)
        updated = prefix + original[boundary:]
    else:
        updated = assignment + "\n" + original
    if tomllib.loads(updated).get("budget_password") != password:
        raise ValueError("无法安全更新已有密码项，原配置未改动。")
    return updated


def main():
    path = ROOT / ".streamlit" / "secrets.toml"
    original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    secrets = tomllib.loads(original)
    if budget_auth.get_budget_password(secrets, os.environ):
        print("本机预算/待办访问密码已配置。")
        return 0
    print("请输入线上原密码，或自选一个本机密码。密码仅保存到本机，不上传。")
    first = getpass.getpass("密码（输入不会显示；直接回车跳过）：").strip()
    if not first:
        print("暂未设置密码；数据已保留，预算/待办页面会保持锁定。")
        return 0
    second = getpass.getpass("再次输入密码：").strip()
    if first != second:
        print("两次输入不同，未修改配置。")
        return 1
    updated = configured_text(original, first)
    _atomic_text(path, updated)
    print("本机密码已保存，可在预算和待办页面输入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
