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

    def test_estimate_memo_cards_height_accounts_for_content_length(self):
        short_records = [{"content": "短句", "tags": []}]
        long_records = [{"content": "第一行\n第二行\n第三行\n第四行\n第五行", "tags": ["摘录"]}]

        self.assertGreater(
            web_memo_db.estimate_memo_cards_height(long_records),
            web_memo_db.estimate_memo_cards_height(short_records),
        )


if __name__ == "__main__":
    unittest.main()
