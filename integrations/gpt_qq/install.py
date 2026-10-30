"""Compatibility entry for the relocated Cyber QQ installer."""
from pathlib import Path
import runpy
import sys

entry = Path(__file__).resolve().parents[1] / "cyber_qq/gpt_qq/install.py"
sys.path.insert(0, str(entry.parent))
if __name__ == "__main__":
    runpy.run_path(str(entry), run_name="__main__")
