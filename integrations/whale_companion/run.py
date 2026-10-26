"""Run the pinned application with its own data and process-local tool paths."""
import os
from pathlib import Path
import runpy
import sys

root = Path(sys.argv[1]).resolve()
app = root / "app/AstrBot-4.29.3"
os.environ["ASTRBOT_ROOT"] = str(root / "state")
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PATH"] = os.pathsep.join([
    str(app / ".venv/Scripts"), str(root / "ffmpeg/bin"), os.environ.get("PATH", "")])
sys.path.insert(0, str(app))
os.chdir(app)
sys.argv = [str(app / "main.py"), "--webui-dir", str(root / "state/data/dist")]
runpy.run_path(str(app / "main.py"), run_name="__main__")
