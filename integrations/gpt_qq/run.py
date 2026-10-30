"""Compatibility entry for an existing GPT QQ launcher."""
from pathlib import Path
import runpy
import sys

entry = Path(__file__).resolve().parents[1] / "cyber_qq/gpt_qq/run.py"
sys.path.insert(0, str(entry.parent))
runpy.run_path(str(entry), run_name="__main__")
