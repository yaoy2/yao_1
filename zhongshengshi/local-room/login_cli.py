"""Interactive login belongs to the user; preserve existing shell configuration."""
import subprocess
import sys
from adapters import executable, grok_chat_env, official_claude_env


def main():
    provider = sys.argv[1] if len(sys.argv) > 1 else "claude"
    if provider not in ("claude", "grok"):
        raise SystemExit("Unsupported provider")
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
    print("返回讨论室后，点击“刷新连接”。")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
