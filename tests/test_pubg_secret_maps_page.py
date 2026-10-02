from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "25_26_pubg_secret_maps.py"


def _image(image_id):
    return {
        "id": image_id,
        "label": f"位置图 {image_id}",
        "filename": f"{image_id}.png",
        "width": 4096,
        "height": 4096,
        "mime_type": "image/png",
        "source_url": f"https://example.com/{image_id}",
        "original_url": f"https://example.com/{image_id}.png",
        "author": "地图作者",
        "source_note": "来源版本说明",
        "legend": "圆点表示密室入口",
    }


@pytest.fixture
def map_page(monkeypatch):
    from utils import pubg_map_viewer, pubg_secret_maps, ui_theme

    # Deliberately put Erangel second: its default must not depend on catalog order.
    catalog = [
        {
            "id": map_id,
            "name": name,
            "kind": "密室",
            "access_note": "寻找入口",
            "images": [_image(image_id) for image_id in image_ids],
        }
        for map_id, name, image_ids in [
            ("taego", "泰戈 · Taego", ["taego_main", "taego_detail"]),
            ("erangel", "艾伦格 · Erangel", ["erangel_main", "erangel_detail"]),
            ("vikendi", "维寒迪 · Vikendi", ["vikendi_main"]),
        ]
    ]
    loaded = []

    def load_image(image_id):
        loaded.append(image_id)
        return image_id.encode("ascii")

    monkeypatch.setattr(pubg_secret_maps, "load_catalog", lambda: catalog)
    monkeypatch.setattr(pubg_secret_maps, "load_map_image", load_image)
    monkeypatch.setattr(
        pubg_map_viewer,
        "build_map_viewer",
        lambda image_bytes, mime_type, title, *, crop_box=None: (
            f"<p>{image_bytes.decode('ascii')} crop={crop_box}</p>"
        ),
    )
    monkeypatch.setattr(ui_theme, "render_home_link", lambda: None)
    return AppTest.from_file(str(PAGE_PATH)), loaded


def test_map_selection_loads_immediately_without_a_load_button(map_page):
    app, loaded = map_page
    app.run()
    assert not app.exception
    assert app.selectbox(key="pubg_secret_map").value == "erangel"
    assert loaded == ["erangel_main"]
    assert not app.button
    assert "4,096 × 4,096" in " ".join(item.value for item in app.caption)
    assert "erangel_main" in app.get("iframe")[0].proto.srcdoc

    app.selectbox(key="pubg_secret_map").set_value("taego").run()
    assert not app.exception
    assert loaded[-1] == "taego_main"
    assert "taego_main" in app.get("iframe")[0].proto.srcdoc


def test_image_selection_stays_with_its_own_map(map_page):
    app, loaded = map_page
    app.run()
    app.selectbox(key="pubg_secret_image_erangel").set_value("erangel_detail").run()
    assert loaded[-1] == "erangel_detail"

    app.selectbox(key="pubg_secret_map").set_value("taego").run()
    assert not app.exception
    assert app.selectbox(key="pubg_secret_image_taego").value == "taego_main"
    assert loaded[-1] == "taego_main"
    app.selectbox(key="pubg_secret_image_taego").set_value("taego_detail").run()
    assert loaded[-1] == "taego_detail"

    app.selectbox(key="pubg_secret_map").set_value("vikendi").run()
    assert not app.exception
    assert len(app.selectbox) == 1
    assert loaded[-1] == "vikendi_main"

    app.selectbox(key="pubg_secret_map").set_value("erangel").run()
    assert not app.exception
    assert loaded[-1].startswith("erangel_")
    assert app.selectbox(key="pubg_secret_image_erangel").value == loaded[-1]


def test_map_crop_is_passed_to_viewer_and_resets_for_full_maps(map_page):
    from utils import pubg_secret_maps

    catalog = pubg_secret_maps.load_catalog()
    catalog[1]["images"][0]["display_crop"] = [1500, 0, 2000, 2000]
    app, _loaded = map_page
    app.run()
    assert not app.exception
    assert "2,000 × 2,000" in " ".join(item.value for item in app.caption)
    assert "crop=(1500, 0, 2000, 2000)" in app.get("iframe")[0].proto.srcdoc

    app.selectbox(key="pubg_secret_map").set_value("vikendi").run()
    assert not app.exception
    assert "crop=None" in app.get("iframe")[0].proto.srcdoc
    assert "4,096 × 4,096" in " ".join(item.value for item in app.caption)


@pytest.mark.parametrize("error_type", [OSError, ValueError])
def test_missing_image_keeps_source_links_available(map_page, monkeypatch, error_type):
    from utils import pubg_secret_maps

    def fail_image(image_id):
        raise error_type("unavailable")

    monkeypatch.setattr(pubg_secret_maps, "load_map_image", fail_image)
    app, _loaded = map_page
    app.run()
    assert not app.exception
    assert "无法加载" in app.warning[0].value
    assert not app.get("iframe")
    assert not app.get("download_button")
    assert {item.proto.url for item in app.get("link_button")} == {
        "https://example.com/erangel_main",
        "https://example.com/erangel_main.png",
    }


def test_unavailable_catalog_reports_a_readable_error(map_page, monkeypatch):
    from utils import pubg_secret_maps

    def fail_catalog():
        raise OSError("unavailable")

    monkeypatch.setattr(pubg_secret_maps, "load_catalog", fail_catalog)
    app, _loaded = map_page
    app.run()
    assert not app.exception
    assert "地图目录" in app.error[0].value
    assert not app.selectbox
