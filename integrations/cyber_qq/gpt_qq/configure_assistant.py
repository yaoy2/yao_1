"""Apply the daughter persona and isolated group-assistant profile offline."""
from __future__ import annotations

import argparse
import asyncio
import copy
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import sys

try:
    from .group_assistant.engine import GROUP_PROFILE_NAME, GROUP_ROUTE, PLUGIN_DIRECTORY, PLUGIN_NAME
except ImportError:
    from group_assistant.engine import GROUP_PROFILE_NAME, GROUP_ROUTE, PLUGIN_DIRECTORY, PLUGIN_NAME

SOURCE = Path(__file__).resolve().parent


def group_profile(base: dict) -> dict:
    # AstrBotConfig is a dict subclass that also owns a non-copyable lock.
    config = copy.deepcopy(dict(base))
    config["plugin_set"] = [PLUGIN_NAME]
    config["disable_builtin_commands"] = True
    config["wake_prefix"] = ["/"]
    config["provider_settings"]["enable"] = False
    config["platform_settings"].update({
        "enable_id_white_list": False, "id_whitelist": [],
        "wl_ignore_admin_on_group": False, "wl_ignore_admin_on_friend": False,
        "ignore_at_all": True, "ignore_bot_self_message": True,
        "rate_limit": {"time": 60, "count": 0, "strategy": "stall"},
    })
    return config


async def apply_database_config(root: Path, receipt: dict) -> dict:
    from astrbot.core import astrbot_config, db_helper, sp
    from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
    from astrbot.core.umop_config_router import UmopConfigRouter

    await db_helper.initialize()
    await sp.initialize()
    try:
        router = UmopConfigRouter(sp)
        await router.initialize()
        manager = AstrBotConfigManager(astrbot_config, router, sp)
        await manager.initialize()
        current = await db_helper.get_persona_by_id("gpt-qq")
        if current is None:
            raise ValueError("The bound GPT persona is missing")
        profile_id = receipt.get("group_assistant_profile_id")
        existing = router.umop_to_conf_id.get(GROUP_ROUTE)
        if existing and existing != profile_id:
            raise ValueError("A different group route already exists; it was not replaced")
        if profile_id and profile_id not in manager.confs:
            raise ValueError("The recorded group profile is missing")
        if not profile_id:
            if any(x.get("name") == GROUP_PROFILE_NAME for x in manager.get_conf_list()):
                raise ValueError("An unowned profile with this name already exists")
            profile_id = await manager.create_conf(group_profile(astrbot_config), GROUP_PROFILE_NAME)
        else:
            manager.confs[profile_id].save_config(group_profile(manager.confs[profile_id]))
        # Put this exact platform/type route before any broader fallback patterns.
        routes = {GROUP_ROUTE: profile_id, **{k: v for k, v in router.umop_to_conf_id.items() if k != GROUP_ROUTE}}
        await router.update_routing_data(routes)
        persona = (SOURCE / "persona.txt").read_text(encoding="utf-8").strip()
        await db_helper.update_persona("gpt-qq", system_prompt=persona)
        reread = await db_helper.get_persona_by_id("gpt-qq")
        if reread.system_prompt != persona:
            raise RuntimeError("Persona read-back did not match")
        await sp.flush()
        return {"profile_id": profile_id, "persona_id": "gpt-qq", "route": GROUP_ROUTE}
    finally:
        await sp.close()
        await db_helper.engine.dispose()


def configure(root: Path) -> dict:
    root = root.resolve()
    receipt_path = root / "installation.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    if receipt.get("expected_host", "").lower() != socket.gethostname().lower():
        raise ValueError("This runtime belongs to another computer")
    if receipt.get("app_version") != "4.29.3" or not receipt.get("qq_data_isolated"):
        raise ValueError("Expected the isolated AstrBot 4.29.3 GPT QQ runtime")
    with socket.socket() as probe:
        probe.settimeout(0.3)
        if probe.connect_ex(("127.0.0.1", int(receipt["ports"]["dashboard"]))) == 0:
            raise ValueError("Stop only the GPT backend before applying; keep its QQ bridge running")
    stamp = datetime.now().strftime("%Y_%m_%d_%H%M%S_%f")
    backup = root / "backups" / ("daughter_group_assistant_" + stamp)
    backup.mkdir(parents=True)
    for source in (receipt_path, root / "state/data/cmd_config.json"):
        shutil.copy2(source, backup / source.name)
    database = root / "state/data/data_v4.db"
    with closing(sqlite3.connect(database)) as original, closing(sqlite3.connect(backup / "data_v4.db")) as destination:
        original.backup(destination)
    config_dir = root / "state/data/config"
    if config_dir.exists():
        shutil.copytree(config_dir, backup / "config")
    target = root / "state/data/plugins" / PLUGIN_DIRECTORY
    if target.exists():
        shutil.copytree(target, backup / PLUGIN_DIRECTORY)
    target.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "engine.py", "main.py", "metadata.yaml"):
        shutil.copy2(SOURCE / "group_assistant" / name, target / name)
    os.environ["ASTRBOT_ROOT"] = str(root / "state")
    sys.path.insert(0, str(root / "app/AstrBot-4.29.3"))
    result = asyncio.run(apply_database_config(root, receipt))
    receipt.update({"group_assistant_profile_id": result["profile_id"],
                    "group_assistant_owner_only": True, "daughter_persona_enabled": True,
                    "group_assistant_version": "1.0.0"})
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["backup"] = str(backup)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(configure(args.root), ensure_ascii=False))
