"""Run only this instance's application and conversation store."""
import json
import os
from pathlib import Path
import runpy
import sys

root = Path(sys.argv[1]).resolve()
receipt = json.loads((root / "installation.json").read_text(encoding="utf-8"))
app = root / f"app/AstrBot-{receipt['app_version']}"
os.environ["ASTRBOT_ROOT"] = str(root / "state")
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.dont_write_bytecode = True
sys.path.insert(0, str(app))
os.chdir(app)
sys.argv = [str(app / "main.py"), "--webui-dir", str(root / "state/data/dist")]
runpy.run_path(str(app / "main.py"), run_name="__main__")
