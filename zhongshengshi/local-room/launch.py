"""Start or reopen the local room without changing installed tools or settings."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen, build_opener, ProxyHandler
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8766"


def healthy():
    try:
        with build_opener(ProxyHandler({})).open(URL + "/api/health", timeout=1) as response:
            return json.load(response).get("app") == "local-discussion-room"
    except (OSError, ValueError, URLError):
        return False


def main():
    if not healthy():
        runtime = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AiDiscussionRoom"
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
    main()
