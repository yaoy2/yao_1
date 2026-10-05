"""Interactive login belongs to the user; preserve existing shell configuration."""
import subprocess
import sys
import tempfile
import gemini_bridge
from adapters import executable, grok_chat_env, official_claude_env


def _login():
    provider = sys.argv[1] if len(sys.argv) > 1 else "claude"
    if provider not in ("claude", "grok", "gemini"):
        raise SystemExit("Unsupported provider")
    if provider == "gemini":
        with tempfile.TemporaryDirectory(prefix="ai-room-gemini-login-") as cwd:
            args, env = gemini_bridge.login_command(cwd)
            print("即将进入 Google 官方 Antigravity。请自行选择 Google 登录、账号和必要的协议选项。")
            print("本通道使用专用配置，不迁移原 Gemini 配置；如出现迁移选项请选择跳过。")
            print("登录后进入输入界面，可输入 /exit 或按 Ctrl+C 退出，不必发送问题。")
            try:
                result = subprocess.run(args, env=env, cwd=cwd)
                code = result.returncode
            except KeyboardInterrupt:
                code = 0
        print("返回页面后，点击“刷新连接”。Gemini 可用性以官方模型列表检查结果为准。")
        return code
    path = executable(provider)
    if not path:
        raise SystemExit(f"{provider} CLI not found")
    if provider == "claude":
        args = [path, "--safe-mode", "--setting-sources", "", "auth", "login"]
        env = official_claude_env()
        print("请在接下来的官方 Claude 登录页面亲自完成登录。原第三方接口配置保持不变。")
    else:
        args, env = [path, "--no-auto-update", "login"], grok_chat_env()
        print("请亲自完成 Grok 登录。")
    result = subprocess.run(args, env=env)
    print("返回问山集后，点击“刷新连接”。")
    return result.returncode


def main():
    try:
        return _login()
    except (RuntimeError, OSError) as error:
        print(f"无法启动登录：{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
