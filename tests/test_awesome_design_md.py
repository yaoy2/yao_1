import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from utils.awesome_design_md import (
    REPOSITORY_ROOT,
    discover_designs,
    heading_names,
    split_frontmatter,
)


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "20_21_awesome_design_md.py"


class AwesomeDesignMdTest(unittest.TestCase):
    def test_local_snapshot_discovers_design_systems(self):
        items = discover_designs()
        self.assertGreaterEqual(len(items), 70)
        self.assertIn("apple", {item["slug"] for item in items})
        self.assertTrue(all(item["design_path"].is_file() for item in items))

    def test_local_snapshot_is_a_deployable_parent_repository_asset(self):
        self.assertFalse((REPOSITORY_ROOT / ".git").exists())
        source_note = (REPOSITORY_ROOT / "SOURCE.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/VoltAgent/awesome-design-md", source_note)
        self.assertIn("8147538b4226ae41e2487a9179e3bcc1f68e8554", source_note)

    def test_frontmatter_is_separated_from_markdown_body(self):
        metadata, body = split_frontmatter(
            "---\nname: Demo-design-analysis\ndescription: A demo\n---\n\n## Colors\n"
        )
        self.assertEqual("Demo-design-analysis", metadata["name"])
        self.assertEqual("A demo", metadata["description"])
        self.assertEqual("## Colors", body)
        self.assertEqual(["Colors"], heading_names(body))

    def test_discovery_skips_folders_without_design_md(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "design-md" / "valid").mkdir(parents=True)
            (root / "design-md" / "valid" / "DESIGN.md").write_text(
                "---\nname: Valid\n---\n\n## Overview\n", encoding="utf-8"
            )
            (root / "design-md" / "ignored").mkdir()
            items = discover_designs(root)
            self.assertEqual(["valid"], [item["slug"] for item in items])

    def test_m21_page_renders_the_bundled_catalog_without_a_machine_path(self):
        app = AppTest.from_file(str(PAGE), default_timeout=10)
        app.run()

        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(3, len(app.metric))
        captions = "\n".join(item.value for item in app.caption)
        self.assertIn("仓库来源：assets/awesome-design-md/design-md/", captions)
        self.assertIn("/DESIGN.md", captions)
        self.assertNotIn(str(ROOT), captions)


if __name__ == "__main__":
    unittest.main()
