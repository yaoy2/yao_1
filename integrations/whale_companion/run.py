"""Compatibility entry for existing whale launch commands."""
from pathlib import Path
import runpy
import sys

entry = Path(__file__).resolve().parents[1] / "cyber_qq/whale_companion/run.py"
sys.path.insert(0, str(entry.parent))
runpy.run_path(str(entry), run_name="__main__")
