"""Output safety and source-image preservation for the standalone map viewer."""

import base64
from html.parser import HTMLParser
import re
import shutil
import subprocess
import unittest

from utils.pubg_map_viewer import build_map_viewer


class _Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class PubgMapViewerTests(unittest.TestCase):
    def test_embeds_original_image_bytes(self):
        original = bytes(range(256))
        parsed = _Elements(build_map_viewer(original, "image/png", "泰戈"))
        image = next(attrs for tag, attrs in parsed.elements if tag == "img")
        header, encoded = image["src"].split(",", 1)
        self.assertEqual(header, "data:image/png;base64")
        self.assertEqual(base64.b64decode(encoded), original)
        self.assertEqual(image["alt"], "泰戈")

    def test_title_cannot_inject_markup_or_attributes(self):
        title = '\" onload=\"evil()\"><script>evil()</script>& 密室'
        source = build_map_viewer(b"image", "image/jpeg", title)
        parsed = _Elements(source)
        images = [attrs for tag, attrs in parsed.elements if tag == "img"]
        scripts = [attrs for tag, attrs in parsed.elements if tag == "script"]
        self.assertEqual(len(images), 1)
        self.assertEqual(len(scripts), 1)
        self.assertEqual(images[0]["alt"], title)
        self.assertNotIn("onload", images[0])
        self.assertNotIn("<script>evil()", source)

    def test_rejects_empty_payload_and_non_raster_mime(self):
        with self.assertRaises(ValueError):
            build_map_viewer(b"", "image/png", "地图")
        for mime in ("image/svg+xml", "text/html", 'image/png\" onload=\"evil()'):
            with self.subTest(mime=mime), self.assertRaises(ValueError):
                build_map_viewer(b"image", mime, "地图")
        with self.assertRaises(TypeError):
            build_map_viewer("image", "image/png", "地图")

    def test_crop_preserves_original_image_payload(self):
        original = bytes(range(256))
        source = build_map_viewer(original, "image/png", "地图", crop_box=(1348, 30, 1640, 1640))
        parsed = _Elements(source)
        image = next(attrs for tag, attrs in parsed.elements if tag == "img")
        self.assertEqual(base64.b64decode(image["src"].split(",", 1)[1]), original)
        self.assertIn("const cropBox = [1348, 30, 1640, 1640];", source)

    def test_rejects_invalid_crop_types_and_dimensions(self):
        invalid_types = (
            [0, 0, 10, 10], (0, 0, 10), (0, 0, 10, 10, 10),
            (False, 0, 10, 10), (0, True, 10, 10),
            (0, 0, True, 10), (0, 0, 10, False),
            (0.0, 0, 10, 10), (0, 0, "10", 10),
        )
        for crop in invalid_types:
            with self.subTest(crop=crop), self.assertRaises(TypeError):
                build_map_viewer(b"image", "image/png", "地图", crop_box=crop)
        for crop in ((-1, 0, 10, 10), (0, -1, 10, 10), (0, 0, 0, 10), (0, 0, 10, -1)):
            with self.subTest(crop=crop), self.assertRaises(ValueError):
                build_map_viewer(b"image", "image/png", "地图", crop_box=crop)


_NODE = shutil.which("node")


@unittest.skipUnless(_NODE, "Node is needed for viewer interaction checks")
class PubgMapViewerInteractionTests(unittest.TestCase):
    def run_viewer_checks(self, crop_box, checks):
        source = build_map_viewer(b"image", "image/png", "Map", crop_box=crop_box)
        script = re.search(r"<script>(.*?)</script>", source, re.S).group(1)
        harness = r"""
const assert = require("node:assert/strict");
const elements = new Map();
function element(id) {
  const el = { id, style: {}, events: {}, disabled: true, hidden: false, textContent: "",
    clientWidth: 1000, clientHeight: 570, naturalWidth: 3023, naturalHeight: 1701, complete: true,
    classList: { add() {}, remove() {} }, focus() {}, setPointerCapture() {},
    getBoundingClientRect() { return { left: 0, top: 0 }; },
    addEventListener(type, callback) { this.events[type] = callback; }
  };
  elements.set(id, el); return el;
}
global.document = { getElementById(id) { return elements.get(id) || element(id); } };
global.ResizeObserver = class { constructor(callback) { this.callback = callback; } observe() { this.callback(); } };
const get = id => elements.get(id);
"""
        result = subprocess.run(
            [_NODE, "-e", harness + script + checks],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cropped_fit_original_size_and_pan_bounds(self):
        self.run_viewer_checks((1348, 30, 1640, 1640), r"""
const layer = get("map-layer");
const stage = get("stage");
assert.equal(layer.style.width, "1640px");
assert.equal(layer.style.height, "1640px");
assert.equal(get("map").style.left, "-1348px");
assert.equal(get("map").style.top, "-30px");
assert.equal(get("map").style.width, "3023px");
assert.equal(get("scale").textContent, "35%");
assert.match(layer.style.transform, /^translate\(215px, 0px\)/);
get("original").events.click();
assert.equal(get("scale").textContent, "100%");
stage.events.pointerdown({pointerType: "mouse", button: 0, pointerId: 1, clientX: 500, clientY: 200});
stage.events.pointermove({pointerId: 1, clientX: 20000, clientY: 20000});
assert.equal(layer.style.transform, "translate(0px, 0px) scale(1)");
stage.events.pointermove({pointerId: 1, clientX: -20000, clientY: -20000});
assert.equal(layer.style.transform, "translate(-640px, -1070px) scale(1)");
stage.events.pointerup({pointerId: 1});
stage.events.keydown({key: "0", preventDefault() {}});
assert.equal(get("scale").textContent, "35%");
assert.equal(get("map").style.left, "-1348px");
""")

    def test_uncropped_view_uses_full_source_dimensions(self):
        self.run_viewer_checks(None, r"""
assert.equal(get("map-layer").style.width, "3023px");
assert.equal(get("map-layer").style.height, "1701px");
assert.equal(get("map").style.left, "0px");
assert.equal(get("map").style.top, "0px");
assert.equal(get("scale").textContent, "33%");
assert.equal(get("message").hidden, true);
""")

    def test_out_of_bounds_crop_is_hidden_and_controls_disabled(self):
        for crop in ((3020, 0, 10, 10), (0, 1700, 10, 10)):
            with self.subTest(crop=crop):
                self.run_viewer_checks(crop, r"""
assert.equal(get("map-layer").style.visibility, "hidden");
assert.equal(get("message").hidden, false);
assert.equal(get("original").disabled, true);
assert.equal(get("zoom-in").disabled, true);
""")


if __name__ == "__main__":
    unittest.main()
