"""Compatibility entry for Cyber QQ's existing whale configuration."""
from pathlib import Path
import runpy
import sys

entry = Path(__file__).resolve().parents[1] / "cyber_qq/whale_companion/prepare.py"
sys.path.insert(0, str(entry.parent))
if __name__ == "__main__":
    runpy.run_path(str(entry), run_name="__main__")
else:
    globals().update({k: v for k, v in runpy.run_path(str(entry)).items() if not k.startswith("__")})
