"""Copy verified program files into a fresh instance, never account/chat data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def install(source: Path, root: Path, python: str, uv: str, owner: str, bot: str, model: str):
    source, root = source.resolve(), root.resolve()
    if root == source or root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError("The new runtime must be separate from the source installation.")
    if root.exists() and any(p.name != ".gitignore" for p in root.iterdir()):
        raise ValueError("Use an empty destination; existing account data will not be overwritten.")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY in the current process before installing.")
    manifest = json.loads((source / "installed-versions.json").read_text(encoding="utf-8-sig"))
    versions = {item["id"]: item["version"] for item in manifest["sources"]}
    if versions.get("astrbot") != "4.29.3" or versions.get("napcat") != "4.18.41":
        raise ValueError("Expected the locally verified AstrBot 4.29.3 / NapCat 4.18.41 builds.")
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text("*\n", encoding="utf-8")
    app = root / "app/AstrBot-4.29.3"
    shutil.copytree(source / "app/AstrBot-4.29.3", app,
                    ignore=shutil.ignore_patterns(".venv", "__pycache__", ".git", ".pytest_cache",
                                                 "data", "logs", ".env", "*.pyc"))
    shutil.copytree(source / "state/data/dist", root / "state/data/dist")
    napcat = root / "napcat"
    napcat.mkdir()
    for item in (source / "napcat").iterdir():
        if item.is_file() and (item.suffix.lower() in {".exe", ".dll", ".node"}
                               or item.name in {"index.js", "package.json", "config.json"}):
            shutil.copy2(item, napcat / item.name)
    shutil.copytree(source / "napcat/win64", napcat / "win64")
    inner = napcat / "napcat"
    inner.mkdir()
    for item in (source / "napcat/napcat").iterdir():
        if item.is_file():
            shutil.copy2(item, inner / item.name)
        elif item.name in {"native", "node_modules", "static", "worker"}:
            shutil.copytree(item, inner / item.name)
    venv = app / ".venv"
    subprocess.run([uv, "venv", "--python", python, str(venv)], check=True)
    env_python = str(venv / "Scripts/python.exe")
    # Reuse exact package versions, but install them into a separate environment.
    requirements = Path(__file__).resolve().parents[1] / "whale_companion/requirements.lock.txt"
    subprocess.run([uv, "pip", "sync", "--python", env_python, str(requirements)], check=True)
    subprocess.run([uv, "pip", "check", "--python", env_python], check=True)
    subprocess.run([env_python, "-B", str(Path(__file__).with_name("prepare.py")),
                    "--root", str(root), "--bot-qq", bot, "--owner-qq", owner, "--model", model], check=True)
    copied = {"sources": [item for item in manifest["sources"]
                           if item["id"] in {"astrbot", "dashboard", "napcat"}],
              "copied_program_files_from_verified_installation": True}
    (root / "installed-versions.json").write_text(json.dumps(copied, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-runtime", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--uv", required=True)
    parser.add_argument("--owner-qq", required=True)
    parser.add_argument("--bot-qq", required=True)
    parser.add_argument("--model", default="gpt-6.1-sol")
    args = parser.parse_args()
    try:
        install(args.source_runtime, args.root, args.python, args.uv, args.owner_qq, args.bot_qq, args.model)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
