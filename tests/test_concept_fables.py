"""Tests for concept_fables schema-v1 catalog core."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from concept_fables.catalog import (
    CATALOG_PATH,
    filter_items,
    load_catalog,
    make_slug,
    normalize_concept,
    save_catalog,
    select_item,
    upsert_concept,
    validate_catalog,
    validate_item,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
UPSERT_SCRIPT = (
    REPO_ROOT
    / ".codex"
    / "skills"
    / "concept-fable-gallery"
    / "scripts"
    / "upsert_concept.py"
)
SKILL_MD = REPO_ROOT / ".codex" / "skills" / "concept-fable-gallery" / "SKILL.md"
SKILL_AGENT_YAML = (
    REPO_ROOT / ".codex" / "skills" / "concept-fable-gallery" / "agents" / "openai.yaml"
)


def _chinese_payload(**overrides):
    base = {
        "concept": "阴阳",
        "field": "哲学",
        "school": "道家",
        "definition": "对立统一的两种力量",
        "story": "太极图中黑白互抱，阴中有阳，阳中有阴。",
        "mappings": [
            {
                "story_element": "黑白互抱",
                "concept_element": "对立统一",
            }
        ],
        "questions": {
            "core": "阴阳如何相互依存？",
            "transfer": "生活中哪里可见阴阳平衡？",
        },
        "tags": ["道家", "辩证法"],
    }
    base.update(overrides)
    return base


def _valid_item(**overrides):
    item = {
        "id": "yin-yang",
        "concept": "阴阳",
        "field": "哲学",
        "school": "道家",
        "definition": "对立统一的两种力量",
        "story": "太极图中黑白互抱。",
        "mappings": [
            {"story_element": "黑白互抱", "concept_element": "对立统一"},
        ],
        "questions": {
            "core": "阴阳如何相互依存？",
            "transfer": "生活中哪里可见阴阳平衡？",
        },
        "tags": ["道家", "辩证法"],
        "created_at": "2026-01-01",
        "updated_at": "2026-01-02",
    }
    item.update(overrides)
    return item


class TestConceptFablesRendering(unittest.TestCase):
    def test_multiline_detail_and_mappings_use_html_without_markdown(self):
        from concept_fables import page

        item = _valid_item(
            story="第一段。\n\n    第二段含 <script>alert(1)</script>。",
            definition="定义第一段。\n\n    定义第二段。",
            mappings=[
                {"story_element": f"故事 {i}\n\n    后续 & <元素>",
                 "concept_element": f"概念 {i}"}
                for i in range(4)
            ],
        )
        with patch.object(page.st, "html") as html, \
                patch.object(page.st, "markdown") as markdown, \
                patch.object(page.st, "button", return_value=False):
            page._render_detail(item)

        markdown.assert_not_called()
        html.assert_called_once()
        body = html.call_args.args[0]
        self.assertEqual(body.count('class="cf-map-item"'), 4)
        for i in range(4):
            self.assertIn(f"故事 {i}", body)
            self.assertIn(f"概念 {i}", body)
        self.assertIn("第一段。\n\n    第二段", body)
        self.assertIn("定义第一段。\n\n    定义第二段。", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertIn("后续 &amp; &lt;元素&gt;", body)
        self.assertNotIn("<script>", body)

    def test_gallery_fragments_use_html_without_markdown(self):
        from concept_fables import page

        item = _valid_item(definition="第一段\n\n    第二段", tags=[])
        with patch.object(page.st, "html") as html, \
                patch.object(page.st, "markdown") as markdown, \
                patch.object(page.st, "button", return_value=False):
            page._render_hero([item])
            page._render_card(item, "cf_test_card")
            page._render_empty_catalog()

        markdown.assert_not_called()
        self.assertEqual(html.call_count, 3)
        self.assertIn("第一段\n\n    第二段", html.call_args_list[1].args[0])


class TestConceptFablesCatalog(unittest.TestCase):
    def test_empty_load_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            catalog = load_catalog(path)
            self.assertEqual(catalog, {"schema_version": 1, "items": []})
            self.assertFalse(path.exists())

    def test_valid_chinese_item(self):
        item = _valid_item()
        validated = validate_item(item)
        self.assertEqual(validated["concept"], "阴阳")
        self.assertEqual(validated["tags"], ["道家", "辩证法"])
        catalog = validate_catalog({"schema_version": 1, "items": [item]})
        self.assertEqual(len(catalog["items"]), 1)

    def test_tag_nfkc_dedup_keeps_first_display(self):
        item = _valid_item(tags=["AI", "ＡＩ", " ai ", "  Machine   Learning  ", "machine learning"])
        validated = validate_item(item)
        self.assertEqual(validated["tags"], ["AI", "Machine Learning"])
        catalog, action = upsert_concept(
            {"schema_version": 1, "items": []},
            _chinese_payload(tags=["AI", "ＡＩ", " ai "]),
            today="2026-06-01",
        )
        self.assertEqual(action, "created")
        self.assertEqual(catalog["items"][0]["tags"], ["AI"])

    def test_malformed_catalog_rejection(self):
        with self.assertRaises(ValueError):
            validate_catalog({"schema_version": 2, "items": []})
        with self.assertRaises(ValueError):
            validate_catalog({"schema_version": 1, "items": "nope"})
        with self.assertRaises(ValueError):
            validate_catalog({"items": []})

    def test_malformed_record_rejection(self):
        with self.assertRaises(ValueError):
            validate_item({"id": "x"})
        bad = _valid_item(mappings=[])
        with self.assertRaises(ValueError):
            validate_item(bad)
        bad_q = _valid_item(questions={"core": "only"})
        with self.assertRaises(ValueError):
            validate_item(bad_q)

    def test_story_over_1000_rejected(self):
        item = _valid_item(story="字" * 1001)
        with self.assertRaises(ValueError) as ctx:
            validate_item(item)
        self.assertIn("1000", str(ctx.exception))

    def test_stable_chinese_slug_and_collision(self):
        concept = "阴阳"
        normalized = normalize_concept(concept)
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
        expected = f"concept-{digest}"
        self.assertEqual(make_slug(concept, set()), expected)
        self.assertEqual(make_slug(concept, {expected}), f"{expected}-2")
        self.assertEqual(make_slug(concept, {expected, f"{expected}-2"}), f"{expected}-3")

    def test_upsert_new_concept(self):
        catalog = {"schema_version": 1, "items": []}
        updated, action = upsert_concept(catalog, _chinese_payload(), today="2026-03-01")
        self.assertEqual(action, "created")
        self.assertEqual(len(updated["items"]), 1)
        item = updated["items"][0]
        self.assertTrue(item["id"].startswith("concept-"))
        self.assertEqual(item["created_at"], "2026-03-01")
        self.assertEqual(item["updated_at"], "2026-03-01")
        self.assertEqual(catalog["items"], [])

    def test_upsert_duplicate_preserves_id_created_at(self):
        catalog = {"schema_version": 1, "items": []}
        first, _ = upsert_concept(catalog, _chinese_payload(), today="2026-03-01")
        original_id = first["items"][0]["id"]
        original_created = first["items"][0]["created_at"]

        second, action = upsert_concept(
            first,
            _chinese_payload(
                definition="更新后的定义",
                tags=["道家", "更新"],
            ),
            today="2026-04-15",
        )
        self.assertEqual(action, "updated")
        self.assertEqual(len(second["items"]), 1)
        item = second["items"][0]
        self.assertEqual(item["id"], original_id)
        self.assertEqual(item["created_at"], original_created)
        self.assertEqual(item["updated_at"], "2026-04-15")
        self.assertEqual(item["definition"], "更新后的定义")

    def test_deterministic_save_reload_chinese(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "concept_fables.json"
            catalog, _ = upsert_concept(
                {"schema_version": 1, "items": []},
                _chinese_payload(),
                today="2026-05-01",
            )
            save_catalog(catalog, path)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertIn("阴阳", text)
            reloaded = load_catalog(path)
            self.assertEqual(reloaded, catalog)
            # deterministic rewrite
            save_catalog(reloaded, path)
            self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_filter_across_fields_and_tags(self):
        items = [
            _valid_item(
                id="a",
                concept="阴阳",
                field="哲学",
                school="道家",
                definition="对立统一",
                tags=["辩证", "古典"],
                updated_at="2026-01-01",
            ),
            _valid_item(
                id="b",
                concept="熵",
                field="物理",
                school="",
                definition="混乱程度的度量",
                tags=["热力学"],
                updated_at="2026-02-01",
            ),
        ]
        by_concept = filter_items(items, query="阴阳")
        self.assertEqual([i["id"] for i in by_concept], ["a"])
        by_def = filter_items(items, query="混乱")
        self.assertEqual([i["id"] for i in by_def], ["b"])
        by_tag = filter_items(items, query="辩证")
        self.assertEqual([i["id"] for i in by_tag], ["a"])
        by_school = filter_items(items, query="道家")
        self.assertEqual([i["id"] for i in by_school], ["a"])

    def test_field_filter(self):
        items = [
            _valid_item(id="a", concept="阴阳", field="哲学", updated_at="2026-01-01"),
            _valid_item(id="b", concept="熵", field="物理", updated_at="2026-02-01"),
        ]
        only_philosophy = filter_items(items, field="哲学")
        self.assertEqual([i["id"] for i in only_philosophy], ["a"])
        all_items = filter_items(items, field="全部")
        self.assertEqual(len(all_items), 2)

    def test_sort_latest_and_name(self):
        items = [
            _valid_item(id="a", concept="Beta", field="哲学", updated_at="2026-01-01"),
            _valid_item(id="b", concept="Alpha", field="哲学", updated_at="2026-03-01"),
            _valid_item(id="c", concept="Gamma", field="哲学", updated_at="2026-02-01"),
        ]
        latest = filter_items(items, sort="最新")
        self.assertEqual([i["id"] for i in latest], ["b", "c", "a"])
        by_name = filter_items(items, sort="名称")
        self.assertEqual([i["concept"] for i in by_name], ["Alpha", "Beta", "Gamma"])
        # no mutation
        self.assertEqual(items[0]["id"], "a")

    def test_select_item(self):
        items = [
            _valid_item(id="a", concept="阴阳"),
            _valid_item(id="b", concept="熵", field="物理"),
        ]
        found = select_item(items, "b")
        self.assertIsNotNone(found)
        self.assertEqual(found["concept"], "熵")
        found["concept"] = "changed"
        self.assertEqual(items[1]["concept"], "熵")
        self.assertIsNone(select_item(items, "missing"))

    def test_catalog_path_points_to_repo_data(self):
        self.assertEqual(CATALOG_PATH.name, "concept_fables.json")
        self.assertEqual(CATALOG_PATH.parent.name, "data")

    def test_page_ui_source_is_readonly_and_escapes_catalog_text(self):
        root = Path(__file__).resolve().parents[1]
        page_source = (root / "concept_fables" / "page.py").read_text(encoding="utf-8")
        entry_source = (root / "pages" / "18_19_concept_fables.py").read_text(encoding="utf-8")

        self.assertIn("from html import escape", page_source)
        self.assertIn("load_catalog()", page_source)
        self.assertIn("filter_items(", page_source)
        self.assertIn('st.query_params', page_source)
        self.assertIn("返回全部概念", page_source)
        self.assertIn("$concept-fable-gallery", page_source)
        self.assertIn("等待首篇", page_source)
        self.assertIn(".stApp {", page_source)
        self.assertNotIn("upsert_concept", page_source)
        self.assertNotIn("save_catalog", page_source)
        self.assertNotIn("st.form(", page_source)

        self.assertIn('page_title="概念寓言馆"', entry_source)
        self.assertIn('page_icon="📜"', entry_source)
        self.assertIn("render_home_link()", entry_source)
        self.assertIn("render_page()", entry_source)
        self.assertLess(
            entry_source.index("st.set_page_config"),
            entry_source.index("render_home_link()"),
        )

    def test_skill_source_files_exist_and_encode_contracts(self):
        self.assertTrue(SKILL_MD.is_file())
        self.assertTrue(SKILL_AGENT_YAML.is_file())
        self.assertTrue(UPSERT_SCRIPT.is_file())

        skill_text = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("name: concept-fable-gallery", skill_text)
        self.assertIn("寓言", skill_text)
        self.assertIn("概念寓言馆", skill_text)
        self.assertIn("1000", skill_text)
        self.assertIn("钟表匠", skill_text)
        self.assertIn("upsert_concept.py", skill_text)
        self.assertIn("git pull --rebase origin main", skill_text)
        self.assertIn("data/concept_fables.json", skill_text)

        agent_text = SKILL_AGENT_YAML.read_text(encoding="utf-8")
        self.assertIn('display_name: "概念寓言馆"', agent_text)
        self.assertIn("allow_implicit_invocation: true", agent_text)
        self.assertIn("$concept-fable-gallery", agent_text)

        script_text = UPSERT_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("parents[4]", script_text)
        self.assertIn("upsert_concept", script_text)
        self.assertIn("save_catalog", script_text)
        self.assertNotIn("git ", script_text)
        self.assertNotIn("requests", script_text)

    def test_cli_upsert_create_then_update_preserves_created_at(self):
        production_before = CATALOG_PATH.read_text(encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                catalog_path = tmp_path / "concept_fables.json"
                payload_path = tmp_path / "payload.json"

                payload = _chinese_payload(
                    concept="阴阳",
                    definition="对立统一的两种力量",
                    story="值班护士把两支体温计交叉放进同一只口袋，一只偏冷一只偏热。",
                    tags=["道家", "辩证法"],
                )
                payload_path.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )

                first = subprocess.run(
                    [
                        sys.executable,
                        str(UPSERT_SCRIPT),
                        str(payload_path),
                        "--catalog",
                        str(catalog_path),
                        "--today",
                        "2026-07-01",
                    ],
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(first.returncode, 0, msg=first.stderr)
                first_out = json.loads(first.stdout.strip().splitlines()[-1])
                self.assertEqual(first_out["action"], "created")
                self.assertTrue(first_out["id"])
                self.assertEqual(
                    Path(first_out["catalog"]).resolve(),
                    catalog_path.resolve(),
                )

                created_catalog = load_catalog(catalog_path)
                self.assertEqual(len(created_catalog["items"]), 1)
                created_item = created_catalog["items"][0]
                self.assertEqual(created_item["concept"], "阴阳")
                self.assertEqual(created_item["id"], first_out["id"])
                self.assertEqual(created_item["created_at"], "2026-07-01")
                self.assertEqual(created_item["updated_at"], "2026-07-01")

                dup_payload = _chinese_payload(
                    concept="  阴阳  ",
                    definition="更新后的对立统一定义",
                    story="夜班结束时，护士发现口袋里两支体温计读数已经彼此靠近。",
                    tags=["道家", "更新"],
                )
                payload_path.write_text(
                    json.dumps(dup_payload, ensure_ascii=False),
                    encoding="utf-8",
                )

                second = subprocess.run(
                    [
                        sys.executable,
                        str(UPSERT_SCRIPT),
                        str(payload_path),
                        "--catalog",
                        str(catalog_path),
                        "--today",
                        "2026-07-18",
                    ],
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(second.returncode, 0, msg=second.stderr)
                second_out = json.loads(second.stdout.strip().splitlines()[-1])
                self.assertEqual(second_out["action"], "updated")
                self.assertEqual(second_out["id"], first_out["id"])

                updated_catalog = load_catalog(catalog_path)
                self.assertEqual(len(updated_catalog["items"]), 1)
                updated_item = updated_catalog["items"][0]
                self.assertEqual(updated_item["id"], first_out["id"])
                self.assertEqual(updated_item["created_at"], "2026-07-01")
                self.assertEqual(updated_item["updated_at"], "2026-07-18")
                self.assertEqual(updated_item["definition"], "更新后的对立统一定义")
        finally:
            production_after = CATALOG_PATH.read_text(encoding="utf-8")
            self.assertEqual(production_before, production_after)


if __name__ == "__main__":
    unittest.main()
