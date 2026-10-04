"""Local, text-only CLI bridges. Never read or copy authentication files."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib

NAMES = {"codex": "Codex", "claude": "Claude", "grok": "Grok"}
CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def executable(provider: str) -> str | None:
    found = shutil.which(provider)
    if provider == "claude" and found and Path(found).suffix.lower() in (".cmd", ".bat", ".ps1"):
        native = Path(found).parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
        return str(native) if native.is_file() else None
    if found and Path(found).suffix.lower() not in (".cmd", ".bat", ".ps1"):
        return found
    return None


def official_claude_env() -> dict[str, str]:
    # Only this child process is changed. Existing terminal settings stay intact.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("ANTHROPIC_")}
    env["DISABLE_AUTOUPDATER"] = "1"
    return env


def grok_chat_env() -> dict[str, str]:
    env = dict(os.environ)
    for source in ("CLAUDE", "CURSOR"):
        for surface in ("SKILLS", "RULES", "AGENTS", "MCPS", "HOOKS"):
            env[f"GROK_{source}_{surface}_ENABLED"] = "0"
    env["GROK_TOOL_SEARCH"] = "0"
    env["GROK_MEMORY"] = "0"
    return env


def status_command(provider: str, path: str) -> tuple[list[str], dict | None]:
    if provider == "codex":
        return [path, "login", "status"], None
    if provider == "claude":
        return [path, "--safe-mode", "--setting-sources", "", "auth", "status"], official_claude_env()
    return [path, "--no-auto-update", "models"], grok_chat_env()


def provider_status(provider: str) -> dict:
    result = {"id": provider, "name": NAMES[provider], "available": False, "detail": "未找到命令行工具"}
    path = executable(provider)
    if not path:
        return result
    args, env = status_command(provider, path)
    try:
        with tempfile.TemporaryDirectory(prefix="ai-room-status-") as cwd:
            r = subprocess.run(args, env=env, cwd=cwd, capture_output=True,
                               encoding="utf-8", errors="replace", timeout=20,
                               creationflags=CREATE_FLAGS)
        output = r.stdout + r.stderr
        if provider == "claude":
            info = json.loads(r.stdout)
            result["available"] = bool(info.get("loggedIn")) and info.get("apiProvider") == "firstParty"
            result["detail"] = "官方 Claude 登录可用" if result["available"] else "尚未登录官方 Claude；原第三方配置已隔离"
        elif provider == "codex":
            result["available"] = r.returncode == 0 and "Logged in" in output
            result["detail"] = "ChatGPT 登录可用" if result["available"] and "ChatGPT" in output else ("CLI 登录可用" if result["available"] else "尚未登录 Codex")
        else:
            lowered = output.lower()
            explicit_no = "not authenticated" in lowered or "not logged in" in lowered
            explicit_yes = "logged in" in lowered or "authenticated as" in lowered or "you are authenticated" in lowered
            result["available"] = r.returncode == 0 and explicit_yes and not explicit_no
            result["detail"] = "Grok 登录可用" if result["available"] else ("尚未登录 Grok" if explicit_no else "无法确认 Grok 登录；请在终端核实")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        result["detail"] = "登录检查超时" if isinstance(error, subprocess.TimeoutExpired) else "登录状态检查失败"
    return result


def codex_model_args() -> list[str]:
    # Reuse the user's selected model, but not MCP, hooks or other tool settings.
    try:
        root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        config = tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))
        args = []
        if isinstance(config.get("model"), str):
            args += ["--model", config["model"]]
        if isinstance(config.get("model_reasoning_effort"), str):
            args += ["-c", "model_reasoning_effort=" + json.dumps(config["model_reasoning_effort"])]
        return args
    except (OSError, ValueError):
        return []


def command(provider: str, prompt: str, cwd: str) -> tuple[list[str], str | None, dict | None]:
    path = executable(provider)
    if not path:
        raise RuntimeError(f"未找到 {NAMES[provider]} 命令行工具")
    if provider == "codex":
        args = [path, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
                "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--color", "never",
                "-c", 'approval_policy="never"', "-c", 'web_search="disabled"',
                "-c", "mcp_servers={}"]
        for feature in ("shell_tool", "unified_exec", "apps", "plugins", "hooks", "multi_agent",
                        "browser_use", "computer_use", "image_generation", "view_image",
                        "memories", "sleep_tool", "code_mode", "code_mode_host"):
            args += ["--disable", feature]
        args += codex_model_args() + ["-"]
        return args, prompt, None
    if provider == "claude":
        return [path, "--safe-mode", "--setting-sources", "", "--strict-mcp-config",
                "--tools", "", "--permission-mode", "dontAsk", "--no-session-persistence",
                "--no-chrome", "--print", "--verbose", "--output-format", "stream-json",
                "--include-partial-messages"], prompt, official_claude_env()
    prompt_file = Path(cwd) / "prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")
    return [path, "--no-auto-update", "--cwd", cwd, "--prompt-file", str(prompt_file),
            "--output-format", "streaming-messages-json", "--include-partial-messages",
            "--permission-mode", "dontAsk", "--deny", "*", "--no-subagents",
            "--disable-web-search", "--max-turns", "1", "--tools", "todo_write",
            "--disallowed-tools", "todo_write,search_tool,use_tool"], None, grok_chat_env()


def parse_event(provider: str, event: dict) -> list[tuple[str, str]]:
    """Return public answer text only; omit thoughts, tool output and auth metadata."""
    kind = event.get("type")
    found: list[tuple[str, str]] = []
    if provider == "codex":
        item = event.get("item", {})
        if kind == "item.completed" and item.get("type") == "agent_message":
            found.append(("final", item.get("text", "")))
        elif kind == "turn.completed":
            found.append(("complete", ""))
        elif kind in ("error", "turn.failed"):
            error = event.get("error", event)
            found.append(("error", str(error.get("message", "Codex 返回错误"))))
        return found
    if kind in ("stream_event", "event"):
        event = event.get("event", {})
        kind = event.get("type")
    if kind == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            found.append(("delta", delta.get("text", "")))
    if kind == "assistant":
        content = event.get("message", {}).get("content", [])
        answer = "".join(x.get("text", "") for x in content if x.get("type") == "text")
        if answer:
            found.append(("final", answer))
    if kind in ("result", "end"):
        if event.get("is_error") or str(event.get("subtype", "")).startswith("error"):
            found.append(("error", str(event.get("result") or event.get("error") or "模型调用失败")))
        else:
            if isinstance(event.get("result"), str) and event["result"]:
                found.append(("final", event["result"]))
            found.append(("complete", ""))
    if kind == "error":
        found.append(("error", str(event.get("message") or event.get("error") or "模型调用失败")))
    return found


def safe_error(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    text = re.sub(r"(?i)(bearer\s+|(?:api[_-]?key|token)\s*[=:]\s*)[^\s,;]+", r"\1[已隐藏]", text)
    text = re.sub(r"\b(?:sk-|xai-)[A-Za-z0-9_-]{12,}\b", "[已隐藏]", text)
    return text.strip()[-1600:]


class Cancelled(Exception):
    pass


def run_cli(provider: str, prompt: str, emit, cancel: threading.Event, timeout: int = 240) -> str:
    with tempfile.TemporaryDirectory(prefix="ai-room-chat-") as cwd:
        args, stdin, env = command(provider, prompt, cwd)
        process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=CREATE_FLAGS)
        lines: queue.Queue = queue.Queue()

        def reader(stream, source):
            try:
                for line in stream:
                    lines.put((source, line))
            finally:
                lines.put((source, None))

        readers = [threading.Thread(target=reader, args=(process.stdout, "out"), daemon=True),
                   threading.Thread(target=reader, args=(process.stderr, "err"), daemon=True)]
        for thread in readers:
            thread.start()
        deadline = time.monotonic() + timeout
        stderr = ""
        answer = ""
        streamed = ""
        complete = False
        failure = ""
        ended = set()
        try:
            if stdin:
                process.stdin.write(stdin)
            process.stdin.close()
            while len(ended) < 2:
                if cancel.is_set():
                    raise Cancelled("已停止生成")
                if time.monotonic() > deadline:
                    raise RuntimeError("本次回复超过 4 分钟，已停止；可以单独点名重试")
                try:
                    source, line = lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    ended.add(source)
                    continue
                if source == "err":
                    stderr = (stderr + line)[-6000:]
                    continue
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        continue
                except ValueError:
                    stderr = (stderr + line)[-6000:]
                    continue
                for kind, text in parse_event(provider, event):
                    if kind == "delta":
                        streamed += text
                        emit({"type": "delta", "text": text})
                    elif kind == "final":
                        answer = text
                    elif kind == "complete":
                        complete = True
                    elif kind == "error":
                        failure = text
            code = process.wait(timeout=3)
            if cancel.is_set():
                raise Cancelled("已停止生成")
            if code or failure:
                raise RuntimeError(safe_error(failure or stderr or f"命令行退出码 {code}"))
            if not complete:
                raise RuntimeError("未收到模型正常完成信号，请重试；部分输出未纳入后续讨论")
            answer = (answer or streamed).strip()
            if not answer:
                raise RuntimeError("模型未返回可用回复")
            return answer
        finally:
            if process.poll() is None:
                process.kill()  # Only this room's own child process, on cancel/error/timeout.
                process.wait(timeout=5)
            for thread in readers:
                thread.join(timeout=2)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()
