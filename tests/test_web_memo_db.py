import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from utils import web_memo_db


@contextmanager
def patched_web_memo_storage(tmpdir):
    tmp_path = Path(tmpdir)
    with (
        patch.object(web_memo_db, "DB_PATH", str(tmp_path / "web_memos.db")),
        patch.object(web_memo_db, "BACKUP_MD_PATH", str(tmp_path / "web_memos_backup.md")),
    ):
        yield tmp_path


class WebMemoDbTest(unittest.TestCase):
    def test_add_memo_classifies_and_lists_newest_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir):
                web_memo_db.init_db()
                web_memo_db.add_memo("2026-05-20", "这是一句可以放进汇报稿的金句。")
                web_memo_db.add_memo("2026-05-23", "会议段子：会后再议，就是今天先放过彼此。")

                records = web_memo_db.get_memos()

        self.assertEqual(2, len(records))
        self.assertEqual("2026-05-23", records[0]["memo_date"])
        self.assertEqual("段子", records[0]["category"])
        self.assertIn("会议", records[0]["tags"])
        self.assertEqual("金句", records[1]["category"])

    def test_add_memo_can_skip_classification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir):
                web_memo_db.init_db()
                web_memo_db.add_memo("2026-05-23", "随手记一条。", classify=False)

                records = web_memo_db.get_memos()

        self.assertEqual("待整理", records[0]["category"])
        self.assertEqual(["待整理"], records[0]["tags"])

    def test_add_memo_merges_manual_tags_with_auto_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir):
                web_memo_db.init_db()
                web_memo_db.add_memo(
                    "2026-05-24",
                    "这是一条关于学院预算流程的思考。",
                    manual_tags=["重点", "预算管理"],
                )

                records = web_memo_db.get_memos()

        self.assertEqual("观点", records[0]["category"])
        self.assertIn("预算管理", records[0]["tags"])
        self.assertIn("重点", records[0]["tags"])

    def test_split_tags_accepts_common_separators(self):
        self.assertEqual(["重点", "写作素材", "待办"], web_memo_db.split_tags("重点、写作素材, 待办"))

    def test_add_memo_writes_markdown_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir) as tmp_path:
                backup_path = tmp_path / "web_memos_backup.md"
                web_memo_db.init_db()
                web_memo_db.add_memo("2026-05-24", "这是一条需要留下硬备份的内容。")

                backup_text = backup_path.read_text(encoding="utf-8")

        self.assertIn("灵感便签盒备份", backup_text)
        self.assertIn("记录数量：1", backup_text)
        self.assertIn("这是一条需要留下硬备份的内容", backup_text)

    def test_update_memo_edits_content_tags_category_and_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir) as tmp_path:
                backup_path = tmp_path / "web_memos_backup.md"
                web_memo_db.init_db()
                web_memo_db.add_memo("2026-06-07", "旧内容", classify=False)
                memo_id = web_memo_db.get_memos()[0]["id"]

                web_memo_db.update_memo(
                    memo_id,
                    content="新内容",
                    category="观点",
                    tags=["观点", "已编辑"],
                )
                record = web_memo_db.get_memos()[0]
                backup_text = backup_path.read_text(encoding="utf-8")
                backup_records = web_memo_db.parse_markdown_backup(backup_text)

        self.assertEqual("新内容", record["content"])
        self.assertEqual("观点", record["category"])
        self.assertEqual(["观点", "已编辑"], record["tags"])
        self.assertIn("新内容", backup_text)
        self.assertIn("已编辑", backup_text)
        self.assertEqual(memo_id, backup_records[0]["id"])

    def test_import_memo_records_skips_stale_remote_version_after_edit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir):
                web_memo_db.init_db()
                web_memo_db.add_memo("2026-06-07", "旧内容", classify=False)
                memo_id = web_memo_db.get_memos()[0]["id"]

                web_memo_db.update_memo(memo_id, content="新内容")
                inserted = web_memo_db.import_memo_records(
                    [
                        {
                            "id": memo_id,
                            "memo_date": "2026-06-07",
                            "content": "旧内容",
                            "category": "观点",
                            "tags": ["旧版本"],
                        }
                    ]
                )
                records = web_memo_db.get_memos()

        self.assertEqual(0, inserted)
        self.assertEqual(1, len(records))
        self.assertEqual("新内容", records[0]["content"])

    def test_archive_memo_hides_from_default_list_but_keeps_backup_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir) as tmp_path:
                backup_path = tmp_path / "web_memos_backup.md"
                web_memo_db.init_db()
                web_memo_db.add_memo("2026-06-07", "需要隐藏的便签", classify=False)
                memo_id = web_memo_db.get_memos()[0]["id"]

                web_memo_db.archive_memo(memo_id)
                visible_records = web_memo_db.get_memos()
                all_records = web_memo_db.get_memos(include_archived=True)
                backup_text = backup_path.read_text(encoding="utf-8")
                backup_records = web_memo_db.parse_markdown_backup(backup_text)
                export_text = web_memo_db.build_markdown_export(all_records)

        self.assertEqual([], visible_records)
        self.assertEqual(1, len(all_records))
        self.assertTrue(all_records[0]["is_archived"])
        self.assertEqual(1, len(backup_records))
        self.assertTrue(backup_records[0]["is_archived"])
        self.assertIn("状态：已隐藏", backup_text)
        self.assertNotIn("状态：已隐藏", export_text)

    def test_move_memo_changes_display_order_without_removing_waterfall_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir):
                web_memo_db.init_db()
                web_memo_db.add_memo("2026-06-01", "第一条", classify=False)
                web_memo_db.add_memo("2026-06-02", "第二条", classify=False)
                web_memo_db.add_memo("2026-06-03", "第三条", classify=False)
                records = web_memo_db.get_memos()
                bottom_id = next(record["id"] for record in records if record["content"] == "第一条")

                web_memo_db.move_memo(bottom_id, "up")
                moved_records = web_memo_db.get_memos()
                html = web_memo_db.build_memo_cards_html(moved_records)

        self.assertEqual(["第三条", "第一条", "第二条"], [record["content"] for record in moved_records])
        self.assertIn("memo-card-grid", html)
        self.assertEqual(3, html.count('class="memo-card-column"'))

    def test_init_db_restores_records_from_markdown_backup_when_database_is_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir) as tmp_path:
                backup_path = tmp_path / "web_memos_backup.md"
                backup_path.write_text(
                    "\n".join(
                        [
                            "# 灵感便签盒备份",
                            "",
                            "# 灵感便签盒",
                            "## 2026-05-24",
                            "",
                            "从备份恢复的一条。",
                            "",
                            "- 分类：摘录",
                            "- 标签：摘录、测试",
                            "- 色卡：商务蓝",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                web_memo_db.init_db()
                records = web_memo_db.get_memos()

        self.assertEqual(1, len(records))
        self.assertEqual("2026-05-24", records[0]["memo_date"])
        self.assertEqual("从备份恢复的一条。", records[0]["content"])
        self.assertEqual("摘录", records[0]["category"])
        self.assertEqual(["摘录", "测试"], records[0]["tags"])

    def test_has_markdown_backup_records_detects_existing_backup_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir) as tmp_path:
                backup_path = tmp_path / "web_memos_backup.md"
                backup_path.write_text(
                    "\n".join(
                        [
                            "# 灵感便签盒备份",
                            "",
                            "# 灵感便签盒",
                            "## 2026-05-24",
                            "",
                            "本地备份里还有内容。",
                            "",
                            "- 分类：摘录",
                            "- 标签：摘录",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                has_records = web_memo_db.has_markdown_backup_records()

        self.assertTrue(has_records)

    def test_import_memo_records_merges_new_records_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir) as tmp_path:
                backup_path = tmp_path / "web_memos_backup.md"
                web_memo_db.init_db()
                web_memo_db.add_memo("2026-06-01", "local memo", classify=False)

                inserted = web_memo_db.import_memo_records(
                    [
                        {
                            "memo_date": "2026-06-01",
                            "content": "local memo",
                            "category": "local",
                            "tags": ["duplicate"],
                        },
                        {
                            "memo_date": "2026-06-02",
                            "content": "remote memo",
                            "category": "remote",
                            "tags": ["new"],
                        },
                    ]
                )
                records = web_memo_db.get_memos()
                backup_records = web_memo_db.parse_markdown_backup(backup_path.read_text(encoding="utf-8"))

        self.assertEqual(1, inserted)
        self.assertEqual(2, len(records))
        self.assertEqual(2, len(backup_records))
        self.assertIn("remote memo", [record["content"] for record in records])

    def test_archive_duplicate_memos_keeps_only_one_visible_card(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patched_web_memo_storage(tmpdir):
                web_memo_db.init_db()
                web_memo_db.add_memo("2026-06-07", "same memo", classify=False)
                web_memo_db.add_memo("2026-06-07", "same\nmemo", classify=False)

                archived = web_memo_db.archive_duplicate_memos()
                visible_records = web_memo_db.get_memos()
                all_records = web_memo_db.get_memos(include_archived=True)

        self.assertEqual(1, archived)
        self.assertEqual(1, len(visible_records))
        self.assertEqual(2, len(all_records))
        self.assertEqual(1, sum(1 for record in all_records if record["is_archived"]))

    def test_build_markdown_export_contains_dates_content_and_tags(self):
        records = [
            {
                "memo_date": "2026-05-23",
                "content": "能把事情讲清楚的人，已经替别人省掉了一半焦虑。",
                "category": "金句",
                "tags": ["沟通", "写作素材"],
                "palette_name": "商务蓝",
            }
        ]

        markdown = web_memo_db.build_markdown_export(records)

        self.assertIn("# 灵感便签盒", markdown)
        self.assertIn("## 2026-05-23", markdown)
        self.assertIn("能把事情讲清楚", markdown)
        self.assertIn("分类：金句", markdown)
        self.assertIn("标签：沟通、写作素材", markdown)
        self.assertIn("色卡：商务蓝", markdown)

    def test_build_pdf_export_returns_pdf_bytes(self):
        records = [
            {
                "memo_date": "2026-05-23",
                "content": "我来监督沙瑞金。",
                "category": "金句",
                "tags": ["测试"],
                "palette_name": "商务蓝",
            }
        ]

        pdf_bytes = web_memo_db.build_pdf_export(records)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 100)

    def test_palette_selection_cycles_through_available_palettes(self):
        palettes = [
            {"id": 1, "name": "A", "colors": ["#111111", "#222222", "#333333"]},
            {"id": 2, "name": "B", "colors": ["#444444", "#555555", "#666666"]},
        ]

        self.assertEqual("A", web_memo_db.pick_palette(0, palettes)["name"])
        self.assertEqual("B", web_memo_db.pick_palette(1, palettes)["name"])
        self.assertEqual("A", web_memo_db.pick_palette(2, palettes)["name"])

    def test_memo_card_can_use_position_palette_to_reduce_repeated_colors(self):
        record = {"memo_date": "2026-06-07", "content": "same memo", "tags": []}
        palettes = [
            {"id": 1, "name": "A", "colors": ["#111111", "#222222", "#333333"]},
            {"id": 2, "name": "B", "colors": ["#444444", "#555555", "#666666"]},
        ]

        first_html = web_memo_db.build_memo_card_html(record, palettes=palettes, palette_index=0)
        second_html = web_memo_db.build_memo_card_html(record, palettes=palettes, palette_index=1)

        self.assertIn("A", first_html)
        self.assertIn("B", second_html)

    def test_memo_card_uses_palette_pair_as_background_and_text_colors(self):
        record = {"memo_date": "2026-06-07", "content": "那不勒黄配曙绿", "tags": ["配色"]}
        palettes = [
            {"id": 37, "name": "那不勒黄曙绿", "colors": ["#F8CB1D", "#19663C", "#F6F1DA"]},
        ]

        yellow_card = web_memo_db.build_memo_card_html(record, palettes=palettes, palette_index=0)
        green_card = web_memo_db.build_memo_card_html(record, palettes=palettes, palette_index=1)

        self.assertIn("background:#F8CB1D", yellow_card)
        self.assertIn("--card-text:#19663C", yellow_card)
        self.assertIn("background:#19663C", green_card)
        self.assertIn("--card-text:#F8CB1D", green_card)

    def test_memo_card_css_uses_palette_text_variable_instead_of_fixed_black(self):
        records = [{"memo_date": "2026-06-07", "content": "配色测试", "tags": ["配色"]}]

        html = web_memo_db.build_memo_cards_html(records)

        self.assertIn("color: var(--card-text);", html)
        self.assertNotIn("linear-gradient", html)
        self.assertNotIn("color: #182230;", html)

    def test_build_memo_cards_html_renders_multiple_cards_without_leaking_html(self):
        records = [
            {
                "memo_date": "2026-05-24",
                "content": "第一条",
                "tags": ["摘录"],
                "palette_name": "商务蓝",
                "palette_colors": ["#1B3A5C", "#4A90D9", "#E8F0FE"],
            },
            {
                "memo_date": "2026-05-24",
                "content": '<article class="memo-card">不该变成结构</article>',
                "tags": ["摘录"],
                "palette_name": "莫兰迪灰绿",
                "palette_colors": ["#2D6A4F", "#95B8A6", "#EEF5EF"],
            },
        ]

        html = web_memo_db.build_memo_cards_html(records)

        self.assertEqual(2, html.count('<article class="memo-card"'))
        self.assertIn("memo-card-grid", html)
        self.assertEqual(3, html.count('class="memo-card-column"'))
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", html)
        self.assertNotIn("max-width: 1320px", html)
        self.assertIn("&lt;article class=&quot;memo-card&quot;&gt;", html)
        self.assertNotIn('<article class="memo-card">不该变成结构</article>', html)

    def test_memo_card_uses_current_palette_pool_instead_of_stored_snapshot(self):
        record = {
            "memo_date": "2026-06-07",
            "content": "same memo should follow current palettes",
            "tags": ["note"],
            "palette_name": "Deleted palette",
            "palette_colors": ["#AAAAAA", "#BBBBBB", "#CCCCCC"],
        }
        palettes = [
            {"id": 1, "name": "Current palette", "colors": ["#111111", "#222222", "#333333"]},
        ]

        html = web_memo_db.build_memo_card_html(record, palettes=palettes)

        self.assertIn("Current palette", html)
        self.assertIn("#111111", html)
        self.assertNotIn("linear-gradient", html)
        self.assertNotIn("Deleted palette", html)
        self.assertNotIn("#AAAAAA", html)

    def test_estimate_memo_cards_height_accounts_for_content_length(self):
        short_records = [{"content": "短句", "tags": []}]
        long_records = [{"content": "第一行\n第二行\n第三行\n第四行\n第五行", "tags": ["摘录"]}]

        self.assertGreater(
            web_memo_db.estimate_memo_cards_height(long_records),
            web_memo_db.estimate_memo_cards_height(short_records),
        )

    def test_page_uses_today_without_visible_date_input_and_native_three_columns(self):
        page_path = Path(__file__).resolve().parents[1] / "pages" / "01_10、🧾_灵感便签盒.py"
        page_source = page_path.read_text(encoding="utf-8")

        self.assertNotIn("date_input", page_source)
        self.assertNotIn("streamlit.components", page_source)
        self.assertIn("date.today().isoformat()", page_source)
        self.assertIn("st.columns(3", page_source)

    def test_page_exposes_manual_tag_controls(self):
        page_path = Path(__file__).resolve().parents[1] / "pages" / "01_10、🧾_灵感便签盒.py"
        page_source = page_path.read_text(encoding="utf-8")

        self.assertIn("st.multiselect(", page_source)
        self.assertIn("\"标签\",", page_source)
        self.assertIn("st.text_input(", page_source)
        self.assertIn("\"新增标签\",", page_source)
        self.assertIn("manual_tags=manual_tags", page_source)

    def test_page_syncs_web_memo_backup_to_github_after_writes(self):
        page_path = Path(__file__).resolve().parents[1] / "pages" / "01_10、🧾_灵感便签盒.py"
        page_source = page_path.read_text(encoding="utf-8")

        self.assertIn("github_backup_sync", page_source)
        self.assertIn("sync_web_memo_backup_to_github()", page_source)
        self.assertIn("GITHUB_BACKUP_TOKEN", page_source)

    def test_page_restores_web_memo_backup_from_github_before_init(self):
        page_path = Path(__file__).resolve().parents[1] / "pages" / "01_10、🧾_灵感便签盒.py"
        page_source = page_path.read_text(encoding="utf-8")

        self.assertIn("restore_web_memo_backup_from_github()", page_source)
        self.assertLess(
            page_source.index("restore_web_memo_backup_from_github()"),
            page_source.index("web_memo_db.init_db()"),
        )


    def test_page_merges_remote_web_memos_and_blocks_empty_overwrite(self):
        pages_dir = Path(__file__).resolve().parents[1] / "pages"
        page_path = next(pages_dir.glob("01_10*.py"))
        page_source = page_path.read_text(encoding="utf-8")

        self.assertIn("merge_remote_web_memos_from_github()", page_source)
        self.assertIn("read_file_from_github", page_source)
        self.assertIn("import_memo_records(remote_records)", page_source)
        self.assertIn("remote_records and not local_records", page_source)
        self.assertIn("web_memo_db.init_db()\nmerge_remote_web_memos_from_github()", page_source)

    def test_page_exposes_edit_archive_and_move_controls(self):
        pages_dir = Path(__file__).resolve().parents[1] / "pages"
        page_path = next(pages_dir.glob("01_10*.py"))
        page_source = page_path.read_text(encoding="utf-8")

        self.assertIn('button("↑"', page_source)
        self.assertIn('button("↓"', page_source)
        self.assertIn('button("✎"', page_source)
        self.assertIn('button("×"', page_source)
        self.assertIn('help="编辑"', page_source)
        self.assertIn('help="隐藏"', page_source)
        self.assertNotIn('button("编辑"', page_source)
        self.assertNotIn('button("隐藏"', page_source)
        self.assertIn("st.columns([0.18, 0.18, 0.18, 0.18, 1]", page_source)
        self.assertIn("update_memo(", page_source)
        self.assertIn("archive_memo(", page_source)
        self.assertIn("move_memo(", page_source)
        self.assertIn("editing_memo_id", page_source)
        self.assertIn("with st.container(border=True):", page_source)
        self.assertIn("build_memo_card_html(record, palette_index=index)", page_source)
        self.assertLess(
            page_source.index("with st.container(border=True):"),
            page_source.index('button("↑"'),
        )


if __name__ == "__main__":
    unittest.main()
