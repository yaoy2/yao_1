"""Prepare a fresh GPT/QQ instance without importing another bot's state."""
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

APP_VERSION = "4.29.3"
PORTS = {"dashboard": 6189, "onebot": 6199, "napcat": 6100}
PERSONA_ID = "gpt-qq"
PERSONA = (
    "你是通过 QQ 与用户聊天的 GPT 助手。默认用自然、简洁的中文交流，日常回复通常一到三句；"
    "需要解释或完成任务时给出足够的信息。可以有幽默感，但不套用客服话术。"
    "只根据当前对话和实际提供的记忆回答，不编造共同经历。明确区分已完成的动作与建议；"
    "没有工具证据时，不声称已经浏览网页、观看视频、发送消息或操作电脑。"
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def initial_config(owner_qq: str, api_key: str, password: str, bridge_token: str,
                   model: str = "gpt-6.1-sol") -> dict:
    if not owner_qq.isdecimal() or not 5 <= len(owner_qq) <= 12:
        raise ValueError("Provide the owner's QQ number.")
    if not api_key or not model.startswith("gpt-"):
        raise ValueError("A GPT model and an OpenAI API key are required.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
    return {
        "config_version": 5,
        "dashboard": {
            "host": "127.0.0.1", "port": PORTS["dashboard"], "username": "sir",
            "password": hashlib.md5(password.encode()).hexdigest(),
            "pbkdf2_password": f"pbkdf2_sha256$600000${salt}${digest}",
            "password_storage_upgraded": True, "password_change_required": False,
            "jwt_secret": secrets.token_urlsafe(48),
        },
        "admins_id": [owner_qq],
        "platform_settings": {
            "enable_id_white_list": True,
            "id_whitelist": [f"gpt-qq:FriendMessage:{owner_qq}"],
            "wl_ignore_admin_on_group": False, "wl_ignore_admin_on_friend": False,
            "no_permission_reply": False, "ignore_bot_self_message": True,
            "friend_message_needs_wake_prefix": False,
            "rate_limit": {"time": 60, "count": 10, "strategy": "stall"},
        },
        "platform": [{
            "id": "gpt-qq", "type": "aiocqhttp", "enable": True,
            "ws_reverse_host": "127.0.0.1", "ws_reverse_port": PORTS["onebot"],
            "ws_reverse_token": bridge_token,
        }],
        "provider_sources": [{
            "id": "openai", "provider": "openai", "type": "openai_chat_completion",
            "provider_type": "chat_completion", "enable": True, "key": [api_key],
            "api_base": "https://api.openai.com/v1", "timeout": 120,
            "proxy": "", "custom_headers": {},
        }],
        "provider": [{
            "id": "gpt-qq-model", "provider_source_id": "openai",
            "type": "openai_chat_completion", "provider_type": "chat_completion",
            "enable": True, "model": model, "modalities": ["text", "image", "tool_use"],
            "custom_extra_body": {
                "max_completion_tokens": 2048, "reasoning_effort": "low", "store": False,
            },
        }],
        "provider_settings": {
            "enable": True, "computer_use_runtime": "none", "web_search": False,
            "proactive_capability": {"add_cron_tools": False},
            "default_image_caption_provider_id": "gpt-qq-model",
        },
        "agent_runner": {"runner_type": "local", "config": {
            "model": {"provider_id": "gpt-qq-model", "request_max_retries": 1,
                      "fallback_provider_ids": []},
            "persona": {"persona_id": PERSONA_ID},
            "compression": {"max_turns": 30, "trim_turns": 6},
            "misc": {"max_steps": 4, "tool_call_timeout": 120},
        }},
        "timezone": "Asia/Taipei", "log_level": "INFO", "disable_metrics": True,
    }


def isolate_napcat(source: str) -> str:
    """Scope both QQ's login store and account data to this installation."""
    targets = (
        "let e = this.context.wrapper.NodeQQNTWrapperUtil.getNTUserDataInfoConfig();",
        "let e = t.NodeQQNTWrapperUtil.getNTUserDataInfoConfig();",
    )
    for target in targets:
        if source.count(target) != 1:
            raise ValueError("Unexpected NapCat build; data-directory patch was not applied.")
        source = source.replace(target, 'let e = process.env.NAPCAT_QQ_DATA_DIR;', 1)
    return source


def prepare(root: Path, bot_qq: str, owner_qq: str, model: str) -> None:
    root = root.resolve()
    if not bot_qq.isdecimal() or not 5 <= len(bot_qq) <= 12 or bot_qq == owner_qq:
        raise ValueError("Provide a dedicated bot QQ number distinct from its owner.")
    if (root / "installation.json").exists() or (root / "state/data/cmd_config.json").exists():
        raise ValueError("This instance already has settings; initialization will not overwrite them.")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    password = "G1q" + secrets.token_urlsafe(20)
    bridge_token = secrets.token_urlsafe(32)
    config = initial_config(owner_qq, api_key, password, bridge_token, model)
    napcat_script = root / "napcat/napcat/napcat.mjs"
    patched = isolate_napcat(napcat_script.read_text(encoding="utf-8"))
    # index.js is the only supported entry; the native QQ wrapper never sees a shared store.
    entry = root / "napcat/index.js"
    entry_source = entry.read_text(encoding="utf-8")
    marker = "const BASE_DIR = __dirname;"
    if entry_source.count(marker) != 1:
        raise ValueError("Unexpected NapCat entry point.")
    entry_source = entry_source.replace(marker, marker + (
        "\nprocess.env.NAPCAT_QQ_DATA_DIR = path.resolve(BASE_DIR, '../qq-data');"
        "\nrequire('fs').mkdirSync(process.env.NAPCAT_QQ_DATA_DIR, { recursive: true });"
    ), 1)
    napcat_script.write_text(patched, encoding="utf-8")
    entry.write_text(entry_source, encoding="utf-8")
    write_json(root / "state/data/cmd_config.json", config)
    napcat_token = secrets.token_urlsafe(32)
    write_json(root / "local-access.json", {
        "dashboard_url": f"http://127.0.0.1:{PORTS['dashboard']}", "username": "sir",
        "password": password, "onebot_token": bridge_token, "napcat_token": napcat_token,
        "napcat_url": f"http://127.0.0.1:{PORTS['napcat']}",
    })
    write_json(root / "napcat/napcat/config/webui.json", {
        "host": "127.0.0.1", "port": PORTS["napcat"], "token": napcat_token,
        "autoLoginAccount": bot_qq,
    })
    write_json(root / "napcat/napcat/config/napcat.json", {"autoTimeSync": False})
    write_json(root / f"napcat/napcat/config/napcat_{bot_qq}.json", {"autoTimeSync": False})
    write_json(root / f"napcat/napcat/config/onebot11_{bot_qq}.json", {
        "network": {
            "httpServers": [], "httpSseServers": [], "httpClients": [],
            "websocketServers": [], "plugins": [], "websocketClients": [{
                "enable": True, "name": "GPT QQ local", "url": f"ws://127.0.0.1:{PORTS['onebot']}/ws",
                "reportSelfMessage": False, "messagePostFormat": "array", "token": bridge_token,
                "debug": False, "heartInterval": 30000, "reconnectInterval": 5000,
            }],
        }, "enableLocalFile2Url": False, "parseMultMsg": False,
    })
    state = root / "state"
    os.environ["ASTRBOT_ROOT"] = str(state)
    sys.path.insert(0, str(root / f"app/AstrBot-{APP_VERSION}"))
    from astrbot.core import db_helper

    async def add_persona():
        await db_helper.initialize()
        await db_helper.insert_persona(PERSONA_ID, PERSONA, tools=[], skills=[])
        await db_helper.engine.dispose()

    asyncio.run(add_persona())
    write_json(root / "installation.json", {
        "expected_host": socket.gethostname(), "root": str(root),
        "app_version": APP_VERSION, "bot_qq": bot_qq, "owner_qq": owner_qq,
        "model": model, "ports": PORTS, "qq_account_logged_in": False,
        "login_autostart_enabled": False, "qq_data_isolated": True,
        "verified_features": ["isolated_configuration"],
    })
    print("Fresh GPT QQ settings created; QQ login and live chat remain to be verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bot-qq", required=True)
    parser.add_argument("--owner-qq", required=True)
    parser.add_argument("--model", default="gpt-6.1-sol")
    args = parser.parse_args()
    prepare(args.root, args.bot_qq, args.owner_qq, args.model)
