"""Run M28 list collection without Streamlit; default is a non-publishing check."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.newspaper_daily import run_daily


def _local_secrets():
    path = ROOT / ".streamlit" / "secrets.toml"
    if not path.exists():
        return {}
    try:
        import tomllib
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except ImportError:
        try:
            import toml
            return toml.loads(path.read_text(encoding="utf-8-sig"))
        except ImportError:
            # Python 3.10 can use the existing gh session or environment secrets.
            return {}


def main(argv=None):
    parser = argparse.ArgumentParser(description="采集并校验日报列表；默认不发布，--publish 才同步到私有数据仓库。")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="采集与校验，不修改远端（默认）")
    modes.add_argument("--publish", action="store_true", help="采集后同步到 yaoy2/yao_1-data 并读回校验")
    parser.add_argument("--force", action="store_true", help="允许同一北京时间 09:00 更新周期再次采集；仍拒绝覆盖较新的远端版本")
    args = parser.parse_args(argv)
    try:
        report = run_daily(dry_run=not args.publish, secrets=_local_secrets(), force=args.force)
    except Exception:
        report = {"ok": False, "status": "failed", "reason": "local_configuration_unavailable"}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
