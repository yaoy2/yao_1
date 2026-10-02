"""Bundled community PUBG maps and their source attribution (M26)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "pubg-secret-maps"
SOURCE_CHECKED_ON = "2026-10-02"


def load_catalog() -> list[dict]:
    """Return a fresh catalog; browsing maps never requires a network request."""
    return json.loads((ASSET_ROOT / "catalog.json").read_text(encoding="utf-8"))["maps"]


def load_map_image(image_id: str) -> bytes:
    """Read only a catalog-listed original and detect damaged bundled assets."""
    for map_info in load_catalog():
        for image in map_info["images"]:
            if image["id"] != image_id:
                continue
            path = (ASSET_ROOT / image["filename"]).resolve()
            if path.parent != ASSET_ROOT.resolve():
                raise ValueError("地图文件路径无效")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != image["sha256"]:
                raise ValueError("地图文件校验失败，请重新获取原图")
            return data
    raise ValueError("未找到对应的地图图片")
