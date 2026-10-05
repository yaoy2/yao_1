"""Gemini text channel through the official Antigravity CLI.

Configuration and customizations use a dedicated USERPROFILE. Authentication
belongs to the official CLI and the user; this module never reads credentials.
The strict agent excludes all tools and default components before inference.
The adapter also verifies the agent, Gemini model, and permission mode at init.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


_AGENT_NAME = "room-text-only"
_AGENT = """---
name: room-text-only
description: Answer only the supplied conversation as text.
tools: []
mainAgent: true
subagent: false
commandExecutionPolicy: "off"
mcpServers: []
skills: []
plugins: []
inheritCustomizations: false
excludeDefaultComponents: true
---
Answer the supplied conversation directly as text.
Do not use tools, commands, files, browsing, skills, plugins, or other agents.
Treat paths, at-signs, and slash commands in the request as ordinary text.
"""
_SETTINGS = {
    "toolPermission": "request-review",
    "permissions": {
        "allow": [], "ask": [],
        "deny": [f"{action}(*)" for action in (
            "read_file", "write_file", "read_url", "execute_url", "command", "unsandboxed", "mcp")],
    },
    "allowNonWorkspaceAccess": False,
    "useG1Credits": False,
    "hooks": {},
}
_MODEL_ID = re.compile(r"(?<![a-z0-9_-])gemini-\d[a-z0-9._-]*[a-z0-9](?![a-z0-9_-])", re.I)
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_selected_model: str | None = None
_CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _app_dir() -> Path:
    # MSIX may virtualize AppData for Codex but not Explorer-launched Python.
    return Path.home() / ".ai-discussion-room"


def _profile() -> Path:
    return _app_dir() / "antigravity-profile"


def _probe_path(path: Path) -> dict:
    """Preserve filesystem errors that Python 3.14 Path.is_file() suppresses."""
    result = {"path": str(path)}
    try:
        info = path.stat()
        result.update({"kind": "file" if stat.S_ISREG(info.st_mode) else
                       "directory" if stat.S_ISDIR(info.st_mode) else "other",
                       "size": info.st_size})
    except OSError as error:
        result["error"] = {"type": type(error).__name__, "errno": error.errno,
                           "winerror": getattr(error, "winerror", None), "message": str(error)}
    return result


def _runtime() -> Path:
    binary = _app_dir() / "antigravity/agy.exe"
    probe = _probe_path(binary)
    if "error" in probe:
        error = probe["error"]
        raise RuntimeError(
            f"当前进程无法访问专用 Antigravity CLI：{binary}\n"
            f"{error['type']}；errno={error['errno']}；WinError={error['winerror']}\n"
            f"系统信息：{error['message']}\n"
            "请先运行 diagnose-gemini.cmd 查看只读自检结果"
        )
    if probe.get("kind") != "file":
        raise RuntimeError(f"专用 Antigravity CLI 路径不是普通文件：{binary}")
    return binary


def runtime_diagnostics() -> dict:
    """Read runtime metadata only; do not inspect authentication or launch CLI."""
    binary = _app_dir() / "antigravity/agy.exe"
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "process_id": os.getpid(),
        "runtime_root": str(_app_dir()),
        "profile": str(_profile()),
        "bridge": str(Path(__file__).resolve()),
        "python": sys.executable,
        "cwd": str(Path.cwd()),
        "environment": {key: os.environ.get(key) for key in
                        ("USERNAME", "USERDOMAIN", "USERPROFILE", "LOCALAPPDATA")},
        "cli_path_checks": [_probe_path(path) for path in [binary, *list(binary.parents)[:3]]],
    }


def _environment(*, login: bool) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("GEMINI_", "GOOGLE_", "GCLOUD_", "CLOUDSDK_", "VERTEX_",
                                           "CODE_ASSIST_", "ANTIGRAVITY_", "AGY_", "OAUTH_"))
           and key.upper() not in {"NODE_OPTIONS", "NODE_PATH", "CLOUD_SHELL", "CLOUD_CODE_URL", "NO_BROWSER"}}
    profile = _profile()
    # Go's os.UserHomeDir uses USERPROFILE on Windows; HOME covers child tools.
    env.update({"USERPROFILE": str(profile), "HOME": str(profile),
                "AGY_CLI_DISABLE_AUTO_UPDATE": "true"})
    if sys.platform == "win32":
        env["HOMEDRIVE"] = profile.drive
        env["HOMEPATH"] = str(profile)[len(profile.drive):]
    return env


def _write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".room-", suffix=".tmp", delete=False) as output:
        temporary = Path(output.name)
        output.write(content)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _prepare(cwd: str, *, login: bool) -> tuple[list[str], dict[str, str]]:
    binary = _runtime()
    workspace = Path(cwd).resolve(strict=True)
    if not workspace.is_dir():
        raise RuntimeError("Gemini 临时工作目录不可用")
    settings_path = _profile() / ".gemini/antigravity-cli/settings.json"
    settings = {}
    if settings_path.is_file():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            raise RuntimeError("Antigravity 专用配置格式无效")
    # Preserve preferences and user-completed onboarding; enforce this channel's
    # tool limits. Never set consent flags or migrate an existing Google profile.
    settings.update(_SETTINGS)
    if str(settings.get("modelProvider", "")).strip().lower() == "gemini":
        raise RuntimeError("此通道需要官方 Google 账号登录；专用配置当前选择了 Gemini API key 方式")
    _write_if_changed(settings_path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
    # Headless Windows builds may discover only the profile customization root
    # at startup (official issue #1052); this remains inside our dedicated home.
    _write_if_changed(_profile() / f".gemini/config/agents/{_AGENT_NAME}.md", _AGENT)
    _write_if_changed(workspace / f".agents/agents/{_AGENT_NAME}.md", _AGENT)
    return [str(binary), "--agent", _AGENT_NAME], _environment(login=login)


def _parse_models(output: str) -> list[str]:
    clean = _ANSI.sub("", output)
    if _model_error(clean):
        return []
    found = []
    for line in clean.splitlines():
        # Verified native output: <model-id> TAB <display name>, one per row.
        columns = line.strip().split("\t")
        if len(columns) != 2:
            continue
        model, label = (column.strip() for column in columns)
        if _MODEL_ID.fullmatch(model) and re.fullmatch(
                r"Gemini\s+\d+(?:\.\d+)?\s+(?:Pro|Flash)(?:\s+\([A-Za-z ]+\))?", label, re.I):
            found.append(model)
    return list(dict.fromkeys(found))


def _model_error(output: str) -> bool:
    return bool(re.search(
        r"not (?:logged in|authenticated)|unauthenticated|authentication (?:is )?required|login required|sign in to|"
        r"\berror\b|\bfailed\b|AGY_ERROR|not eligible|not recognized", output, re.I))


def models(cwd: str | None = None) -> list[str]:
    """Ask the official CLI for available IDs, without issuing a model prompt."""
    if cwd is None:
        with tempfile.TemporaryDirectory(prefix="ai-room-google-status-") as temporary:
            return models(temporary)
    args, env = _prepare(cwd, login=False)
    try:
        result = subprocess.run([args[0], "models"], stdin=subprocess.DEVNULL,
                                capture_output=True, encoding="utf-8", errors="replace",
                                cwd=cwd, env=env, timeout=20, creationflags=_CREATE_FLAGS)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Antigravity 连接检查超时，请稍后刷新连接") from error
    available = (_parse_models(result.stdout) if result.returncode == 0 and
                 not _model_error(result.stderr) else [])
    if not available:
        raise RuntimeError("Antigravity 尚未登录或未返回可用 Gemini 模型；请双击 login-gemini.cmd 完成官方登录")
    return available


def _choose_model(available: list[str]) -> str:
    # Choose only IDs actually returned by the current official client.
    def rank(model: str) -> tuple:
        version = tuple(int(part) for part in re.findall(r"\d+", model))
        return ("pro" in model.lower(), version, "high" in model.lower(), model)
    return max(available, key=rank)


def status() -> dict:
    global _selected_model
    result = {"id": "gemini", "name": "Gemini", "available": False, "detail": ""}
    try:
        _selected_model = _choose_model(models())
        result.update({"available": True, "detail": f"Google 官方通道已返回 Gemini 模型：{_selected_model}"})
    except (OSError, ValueError, RuntimeError) as error:
        _selected_model = None
        result["detail"] = str(error)
    return result


def command(prompt: str, cwd: str) -> tuple[list[str], str, dict[str, str]]:
    model = _selected_model or _choose_model(models(cwd))
    args, env = _prepare(cwd, login=False)
    args += ["--model", model, "--disable-slash-commands",
             "--input-format", "stream-json", "--output-format", "stream-json"]
    # The nested JSON preserves user text without exposing literal @paths to
    # CLI attachment expansion. Slash expansion is separately disabled above.
    request = json.dumps({"request": prompt}, ensure_ascii=False).replace("@", "\\u0040")
    content = "Answer this JSON request as plain text; interpret its escaped characters normally:\n" + request
    stdin = json.dumps({"event": "user", "message": {"content": content}}, ensure_ascii=False) + "\n"
    return args, stdin, env


def login_command(cwd: str) -> tuple[list[str], dict[str, str]]:
    return _prepare(cwd, login=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--diagnose"]:
        print(json.dumps(runtime_diagnostics(), ensure_ascii=False, indent=2))
    elif sys.argv[1:] == ["--status"]:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        raise SystemExit("只读自检：python -X utf8 gemini_bridge.py --diagnose；官方连接检查：--status")
