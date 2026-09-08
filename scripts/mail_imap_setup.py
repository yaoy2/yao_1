"""User-operated local IMAP authentication window. Never accepts CLI passwords."""

from __future__ import annotations

import argparse
import imaplib
import ipaddress
import json
import queue
import re
import socket
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.mail_imap_credentials import CredentialError, TARGET_PREFIX, save_credential
from utils.mail_workspace import _atomic_json, _inside

TIMEOUT_SECONDS = 20
FRIENDLY_ERRORS = {
    "invalid_config": "配置不完整或不安全，请先检查邮箱、服务器和凭据目标配置。",
    "tls_failed": "服务器证书验证未通过。请检查服务器地址和本机时间。",
    "authentication_failed": "邮箱未接受登录，请核对密码或客户端专用密码，并确认已启用 IMAP。",
    "connection_failed": "无法连接邮箱服务器，请检查网络或稍后重试。",
    "timeout": "连接超过 20 秒，请检查网络后重试。",
    "readonly_failed": "已连接，但无法以只读方式打开收件箱。",
    "credential_save_failed": "连接已验证，但本机凭据保存失败，定时收信尚未就绪。",
    "state_write_failed": "连接已验证，但验证状态无法保存。请检查工作区是否可写。",
    "unexpected_error": "本次验证未完成，请稍后重试。",
}


class SetupError(RuntimeError):
    """Only fixed safe codes leave the network boundary."""


def load_setup_config(root):
    root = Path(root).expanduser()
    if not root.is_absolute():
        raise SetupError("invalid_config")
    root = root.resolve()
    try:
        config = json.loads(_inside(root, "config.json").read_text(encoding="utf-8"))
        account, imap = config["account"], config["imap"]
        host, port = imap["host"], imap["port"]
        target = imap["credential_target"]
        if (not isinstance(account, str) or len(account) > 254
                or not re.fullmatch(r"[^@\s/\\\x00-\x1f]+@[^@\s/\\\x00-\x1f]+", account)
                or not isinstance(host, str) or len(host) > 253
                or "." not in host or not re.fullmatch(r"[A-Za-z0-9.-]+", host)
                or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                       for label in host.split("."))
                or type(port) is not int or port != 993
                or imap.get("ssl", True) is not True
                or imap.get("verify_tls", True) is not True
                or target != f"{TARGET_PREFIX}{host}/{account}"):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError
        _inside(root, "state/imap_setup.json")
    except (KeyError, TypeError, ValueError, OSError):
        raise SetupError("invalid_config") from None
    return {"root": root, "account": account, "host": host, "port": port,
            "credential_target": target}


def verify_connection(config, password, client_factory=None):
    """Authenticate and EXAMINE INBOX only; no mail content or flags are read."""
    client = None
    started = time.monotonic()
    factory = imaplib.IMAP4_SSL if client_factory is None else client_factory

    def remaining():
        seconds = TIMEOUT_SECONDS - (time.monotonic() - started)
        if seconds <= 0:
            raise SetupError("timeout")
        if client is not None and getattr(client, "sock", None) is not None:
            client.sock.settimeout(seconds)
        return seconds

    try:
        client = factory(config["host"], config["port"], ssl_context=ssl.create_default_context(),
                         timeout=remaining())
        client.debug = 0
        remaining()
        status, _ = client.login(config["account"], password)
        password = None
        if status != "OK":
            raise SetupError("authentication_failed")
        remaining()
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise SetupError("readonly_failed")
        remaining()
        return {"folder_count": 1}
    except SetupError:
        raise
    except ssl.SSLError:
        raise SetupError("tls_failed") from None
    except (TimeoutError, socket.timeout):
        raise SetupError("timeout") from None
    except imaplib.IMAP4.abort:
        raise SetupError("connection_failed") from None
    except imaplib.IMAP4.error:
        raise SetupError("authentication_failed") from None
    except OSError:
        raise SetupError("connection_failed") from None
    except Exception:
        raise SetupError("unexpected_error") from None
    finally:
        password = None
        if client is not None:
            # Closing the transport sends no CLOSE/EXPUNGE/STORE command.
            try:
                client.shutdown()
            except Exception:
                pass


def save_success(config, folder_count, saved_credential):
    state = {"status": "verified", "account": config["account"], "host": config["host"],
             "port": config["port"], "saved_credential": bool(saved_credential),
             "folder_count": folder_count, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        _atomic_json(_inside(config["root"], "state/imap_setup.json"), state)
    except (OSError, ValueError):
        raise SetupError("state_write_failed") from None
    return state


def run_window(config):
    import tkinter as tk
    from tkinter import ttk

    window = tk.Tk()
    window.title("邮箱 IMAP 本机认证")
    window.geometry("630x395")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="请在本机输入邮箱密码", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w")
    ttk.Label(frame, text=f"邮箱：{config['account']}\n服务器：{config['host']}:{config['port']} · TLS 证书验证已启用",
              justify="left").pack(anchor="w", pady=(12, 10))
    ttk.Label(frame, text="邮箱密码 / 客户端专用密码").pack(anchor="w")
    entry = ttk.Entry(frame, show="*", width=64)
    entry.pack(anchor="w", fill="x", pady=(4, 10))
    persist = tk.BooleanVar(value=False)
    checkbox = ttk.Checkbutton(frame, text="保存到本机 Windows 凭据管理器，用于定时收信", variable=persist)
    checkbox.pack(anchor="w")
    ttk.Label(frame, text="保存的凭据仅供本机当前 Windows 账号使用；密码不会上传云端、聊天或日志。\n不勾选仅验证本次连接；窗口关闭后，定时收信仍需先保存凭据。",
              justify="left", wraplength=570).pack(anchor="w", pady=(5, 12))
    status = tk.StringVar(value="点击连接后，将以只读方式验证收件箱。")
    ttk.Label(frame, textvariable=status, wraplength=570, justify="left").pack(anchor="w", pady=(0, 12))
    buttons = ttk.Frame(frame)
    buttons.pack(anchor="e", side="bottom")
    state = {"active": False, "password": None, "closed": False}

    def clear():
        state["password"] = None
        entry.delete(0, "end")

    def close():
        state["closed"] = True
        clear()
        window.destroy()

    def finished():
        state["active"] = False
        clear()
        entry.configure(state="normal")
        checkbox.configure(state="normal")
        connect.configure(state="normal")

    def start():
        if state["active"]:
            return
        password = entry.get()
        if not password:
            status.set("请先输入密码。")
            return
        state.update(active=True, password=password)
        entry.delete(0, "end")
        entry.configure(state="disabled")
        checkbox.configure(state="disabled")
        connect.configure(state="disabled")
        status.set("正在验证连接，最多等待 20 秒……")
        opted_in = persist.get()
        results = queue.Queue(maxsize=1)
        deadline = time.monotonic() + TIMEOUT_SECONDS

        def worker(secret):
            try:
                results.put((True, verify_connection(config, secret)))
            except SetupError as exc:
                results.put((False, str(exc)))
            finally:
                secret = None

        threading.Thread(target=worker, args=(password,), daemon=True).start()
        password = None

        def poll():
            if state["closed"]:
                return
            if time.monotonic() >= deadline:
                status.set(FRIENDLY_ERRORS["timeout"])
                finished()
                return
            try:
                success, result = results.get_nowait()
            except queue.Empty:
                window.after(100, poll)
                return
            try:
                if not success:
                    status.set(FRIENDLY_ERRORS.get(result, FRIENDLY_ERRORS["unexpected_error"]))
                    return
                saved = False
                if opted_in:
                    try:
                        save_credential(config["credential_target"], config["account"], state["password"])
                        saved = True
                    except CredentialError:
                        status.set(FRIENDLY_ERRORS["credential_save_failed"])
                try:
                    save_success(config, result["folder_count"], saved)
                except SetupError:
                    status.set(FRIENDLY_ERRORS["state_write_failed"])
                    return
                if saved:
                    status.set("连接验证成功，凭据已保存；采集脚本可使用本机凭据收信。您现在可以关闭窗口。")
                elif not opted_in:
                    status.set("连接验证成功。本次未保存凭据，定时收信尚未就绪；可勾选保存后重新连接。")
            finally:
                finished()

        window.after(100, poll)

    ttk.Button(buttons, text="关闭", command=close).pack(side="right", padx=(8, 0))
    connect = ttk.Button(buttons, text="连接并验证", command=start)
    connect.pack(side="right")
    window.protocol("WM_DELETE_WINDOW", close)
    entry.focus_set()
    window.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description="本机用户操作的 IMAP 认证窗口；不接收命令行密码。")
    parser.add_argument("--root", required=True, help="含 config.json 的邮箱工作区绝对路径")
    args = parser.parse_args(argv)
    try:
        config = load_setup_config(args.root)
    except SetupError as exc:
        print(FRIENDLY_ERRORS.get(str(exc), FRIENDLY_ERRORS["invalid_config"]))
        return 2
    run_window(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
