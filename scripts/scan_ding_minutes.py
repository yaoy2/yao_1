import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from utils import ding_minutes


def main():
    result = ding_minutes.scan_once()
    print(
        "Ding minutes scan finished: "
        f"found={result.get('found', 0)}, "
        f"processed={result.get('processed', 0)}, "
        f"skipped={result.get('skipped', 0)}, "
        f"failed={result.get('failed', 0)}"
    )
    if result.get("error"):
        print(result["error"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
