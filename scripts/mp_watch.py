# -*- coding: utf-8 -*-
"""命令行入口：在仓库根目录执行公众号监控一轮。

用法（在 E:\\github\\yao_1 下）：
  python scripts/mp_watch.py
  python scripts/mp_watch.py --dry-run
  python -m mp_watch --dry-run
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mp_watch.__main__ import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
