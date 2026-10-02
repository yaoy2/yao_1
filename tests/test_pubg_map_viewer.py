"""Output safety and source-image preservation for the standalone map viewer."""

import base64
from html.parser import HTMLParser
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


if __name__ == "__main__":
    unittest.main()
