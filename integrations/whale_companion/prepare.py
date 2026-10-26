"""Create an isolated AstrBot installation's initial settings; never reset tuning."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys

HERE = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def schema_defaults(schema):
    return {
        key: schema_defaults(spec.get("items", {})) if spec.get("type") == "object"
        else spec.get("default")
        for key, spec in schema.items()
    }


def apply_keys(config, overrides):
    """Set legacy and grouped copies together, rejecting stale preset keys."""
    found = set()
    def visit(node):
        for key in node:
            if key in overrides:
                node[key] = overrides[key]
                found.add(key)
            elif isinstance(node[key], dict):
                visit(node[key])
    visit(config)
    missing = set(overrides) - found
    if missing:
        raise ValueError(f"Unknown plugin settings: {sorted(missing)}")


def initial_config(password, bridge_token):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
    return {
        "config_version": 5,
        "dashboard": {"host": "127.0.0.1", "port": 6188, "username": "sir",
            "password": hashlib.md5(password.encode()).hexdigest(),
            "pbkdf2_password": f"pbkdf2_sha256$600000${salt}${digest}",
            "password_storage_upgraded": True, "password_change_required": False,
            "jwt_secret": secrets.token_urlsafe(48)},
        "admins_id": [],
        "platform_settings": {"enable_id_white_list": True,
            "id_whitelist": ["whale-setup-pending:FriendMessage:no-user"],
            "wl_ignore_admin_on_group": False, "no_permission_reply": False,
            "ignore_bot_self_message": True},
        "platform": [{"id": "whale-qq", "type": "aiocqhttp", "enable": False,
            "ws_reverse_host": "127.0.0.1", "ws_reverse_port": 6198,
            "ws_reverse_token": bridge_token}],
        "provider_sources": [{"id": "deepseek", "provider": "deepseek",
            "type": "openai_chat_completion", "provider_type": "chat_completion",
            "enable": False, "key": [], "api_base": "https://api.deepseek.com/v1",
            "timeout": 120, "proxy": "", "custom_headers": {}}],
        "provider": [{"id": "deepseek-whale", "provider_source_id": "deepseek",
            "type": "openai_chat_completion", "provider_type": "chat_completion",
            "enable": False, "model": "deepseek-flash", "modalities": ["text", "image", "tool_use"],
            "custom_extra_body": {"max_tokens": 4096, "thinking": {"type": "disabled"}}}],
        "provider_settings": {"computer_use_runtime": "none",
            "proactive_capability": {"add_cron_tools": False},
            "default_image_caption_provider_id": "deepseek-whale"},
        "agent_runner": {"runner_type": "local", "config": {
            "model": {"provider_id": "deepseek-whale", "request_max_retries": 2},
            "persona": {"persona_id": "小鲸"},
            "compression": {"max_turns": 30, "trim_turns": 6},
            "misc": {"max_steps": 8, "tool_call_timeout": 120}}},
        "timezone": "Asia/Taipei",
    }


def prepare(root):
    root = Path(root).resolve()
    state = root / "state"
    app = root / "app/AstrBot-4.29.3"
    cfg_path = state / "data/cmd_config.json"
    if not cfg_path.exists():
        password = "W1a" + secrets.token_urlsafe(20)
        bridge_token = secrets.token_urlsafe(32)
        write_json(cfg_path, initial_config(password, bridge_token))
        write_json(root / "local-access.json", {
            "dashboard_url": "http://127.0.0.1:6188", "username": "sir",
            "password": password, "onebot_token": bridge_token,
            "napcat_token": secrets.token_urlsafe(24)})
    profiles = read_json(HERE / "profiles.json")
    for plugin, overrides in profiles.items():
        path = state / f"data/config/{plugin}_config.json"
        if path.exists():
            continue
        schema = read_json(state / f"data/plugins/{plugin}/_conf_schema.json")
        settings = schema_defaults(schema)
        apply_keys(settings, overrides)
        write_json(path, settings)
    access = read_json(root / "local-access.json")
    napcat_config = root / "napcat/napcat/config/webui.json"
    if not napcat_config.exists():
        write_json(napcat_config, {"host": "127.0.0.1", "port": 6099,
            "token": access["napcat_token"], "autoLoginAccount": ""})
    receipt = root / "installation.json"
    if not receipt.exists():
        write_json(receipt, {"expected_host": socket.gethostname(),
            "root": str(root), "state": str(state), "app": str(app),
            "account_setup_complete": False})
    os.environ["ASTRBOT_ROOT"] = str(state)
    sys.path.insert(0, str(app))
    from astrbot.core import db_helper
    async def add_persona():
        await db_helper.initialize()
        if not await db_helper.get_persona_by_id("小鲸"):
            await db_helper.insert_persona("小鲸", (HERE / "persona.txt").read_text(encoding="utf-8"),
                tools=["search_bilibili", "watch_video", "bili_recall",
                       "memory_companion_recall", "memory_companion_remember"], skills=[])
        await db_helper.engine.dispose()
    asyncio.run(add_persona())
    print("Initial settings ready. Existing settings and memories were preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    prepare(args.root)
