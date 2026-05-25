import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import ding_minutes


def main():
    path = ding_minutes.sync_cloud_export()
    records = ding_minutes.get_records(limit=1000)
    print(f"Recorder cloud export synced: path={path}, records={len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
