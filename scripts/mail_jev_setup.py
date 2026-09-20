"""User-operated local Jev setup. Never print or send a key anywhere except TypeSafe."""

import os
import math

import requests


def save_settings(key=None, *, enabled=True):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as registry:
        if key is not None:
            winreg.SetValueEx(registry, "TYPESAFE_API_KEY", 0, winreg.REG_SZ, key)
        winreg.SetValueEx(registry, "MAIL_JEV_ENABLED", 0, winreg.REG_SZ, "1" if enabled else "0")


def check_key(key):
    """Only a synthetic sentence is sent during setup; no mailbox is read."""
    try:
        with requests.post("https://api.typesafe.ai/v1/systemone",
                           headers={"Authorization": "Bearer " + key},
                           json={"model": "jev-latest", "state": "这是一条连接测试消息。",
                                 "questions": {"test": {"type": "noul",
                                     "instructions": "这段文字是否说明它是一条测试消息？"}}},
                           timeout=(5, 20), allow_redirects=False) as response:
            if response.status_code == 401:
                return "密钥无效，请核对后重试。"
            if response.status_code != 200:
                return "服务暂不可用或账户额度不足，请到 TypeSafe 控制台核对。"
            value = response.json().get("answers", {}).get("test", {})
            if (value.get("type") != "noul" or type(value.get("noul")) not in (int, float)
                    or not math.isfinite(value["noul"]) or not 0 <= value["noul"] <= 1):
                return "服务返回格式不符合预期，尚未启用。"
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return "连接失败，请核对网络后重试。密钥没有保存。"
    return ""


def main():
    if os.name != "nt":
        raise SystemExit("This local setup requires Windows.")
    import tkinter as tk
    from tkinter import messagebox, ttk

    window = tk.Tk()
    window.title("邮件工作台 · Jev 设置")
    window.geometry("570x265")
    panel = ttk.Frame(window, padding=20)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="粘贴 TypeSafe API Key（仅保存在此 Windows 用户的环境变量中）").pack(anchor="w")
    entry = ttk.Entry(panel, show="*", width=72)
    entry.pack(fill="x", pady=12)
    ttk.Label(panel, text="启用后，新邮件正文、已读取的附件文字和 AI 整理结果会交给 TypeSafe 复核。\n"
              "设置时仅发送一条虚构测试消息，会产生一次 API 调用；不读取真实邮件。\n"
              "密钥不进入项目或 Git；同一用户的其他本机进程可以读取用户环境变量。",
              wraplength=530).pack(anchor="w")
    status = ttk.Label(panel, text="设置完成后，请重新启动邮件接收程序。")
    status.pack(anchor="w", pady=12)
    buttons = ttk.Frame(panel)
    buttons.pack(fill="x")

    def enable():
        key = entry.get().strip()
        if not key or any(ord(c) < 32 for c in key):
            messagebox.showerror("尚未配置", "请粘贴有效的 API Key。", parent=window)
            return
        status.config(text="正在测试连接，请稍候……")
        window.update_idletasks()
        error = check_key(key)
        if error:
            status.config(text=error)
            return
        try:
            save_settings(key)
        except OSError:
            status.config(text="本机设置保存失败，尚未启用。")
            return
        entry.delete(0, "end")
        status.config(text="连接测试通过，已保存。请重启接收程序，之后新邮件自动复核。")

    def disable():
        try:
            save_settings(enabled=False)
        except OSError:
            status.config(text="关闭设置未保存，请重试。")
            return
        status.config(text="已关闭自动复核；请重启接收程序。已有邮件和判断保留。")

    ttk.Button(buttons, text="测试连接并启用", command=enable).pack(side="left")
    ttk.Button(buttons, text="关闭自动复核", command=disable).pack(side="left", padx=12)
    entry.focus_set()
    window.mainloop()


if __name__ == "__main__":
    main()
