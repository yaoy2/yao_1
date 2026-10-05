"""Start or reopen the local room without changing installed tools or settings."""
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen, build_opener, ProxyHandler
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8766"


def health():
    try:
        with build_opener(ProxyHandler({})).open(URL + "/api/health", timeout=1) as response:
            result = json.load(response)
            return result if isinstance(result, dict) and result.get("app") == "local-discussion-room" else None
    except (OSError, ValueError, URLError):
        return None


def healthy():
    result = health()
    return bool(result and result.get("version") == 2)


def main():
    running = health()
    if running and running.get("version") != 2:
        raise RuntimeError("本机端口 8766 仍运行旧版问山集。请先关闭旧版服务，再双击本文件启动新版；聊天记录仍保存在原浏览器中。")
    if not healthy():
        # Keep diagnostics visible to both Explorer and packaged desktop apps.
        runtime = Path.home() / ".ai-discussion-room"
        runtime.mkdir(parents=True, exist_ok=True)
        with (runtime / "server.log").open("a", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, "-X", "utf8", str(ROOT / "server.py")],
                                       cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(40):
            if healthy():
                break
            if process.poll() is not None:
                raise RuntimeError("启动失败，端口 8766 可能已被占用。诊断记录：" + str(runtime / "server.log"))
            time.sleep(0.25)
        else:
            raise RuntimeError("服务尚未就绪，请稍后重新打开；诊断记录：" + str(runtime / "server.log"))
    if "--no-browser" not in sys.argv:
        webbrowser.open(URL)
    print(URL)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as error:
        print(f"无法启动问山集：{error}")
        raise SystemExit(1)
