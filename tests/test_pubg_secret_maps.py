import hashlib
import json
from io import BytesIO

import pytest
from PIL import Image

from utils import pubg_secret_maps as maps


def test_catalog_covers_secret_maps_and_original_images_are_intact():
    catalog = maps.load_catalog()
    assert {item["id"] for item in catalog} == {
        "erangel", "miramar", "taego", "rondo", "deston", "vikendi"
    }
    image_ids = set()
    for map_info in catalog:
        for item in map_info["images"]:
            assert item["id"] not in image_ids
            image_ids.add(item["id"])
            data = maps.load_map_image(item["id"])
            with Image.open(BytesIO(data)) as image:
                assert image.size == (item["width"], item["height"])
                assert Image.MIME[image.format] == item["mime_type"]
                assert max(image.size) >= 2000
                image.verify()
            assert item["original_url"].startswith("https://")
            assert item["source_url"].startswith("https://")
            assert item["author"] and item["source_note"] and item["legend"]


def test_unknown_id_cannot_be_used_as_a_file_path():
    with pytest.raises(ValueError, match="未找到"):
        maps.load_map_image("../../.env")


@pytest.mark.parametrize("filename,error", [
    ("../../outside.png", "路径无效"),
    ("map.png", "校验失败"),
])
def test_invalid_or_damaged_asset_is_rejected(tmp_path, monkeypatch, filename, error):
    (tmp_path / "map.png").write_bytes(b"damaged")
    catalog = {"maps": [{"images": [{
        "id": "test", "filename": filename,
        "sha256": hashlib.sha256(b"original").hexdigest(),
    }]}]}
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(maps, "ASSET_ROOT", tmp_path)
    with pytest.raises(ValueError, match=error):
        maps.load_map_image("test")
