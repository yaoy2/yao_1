import importlib
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from docx import Document
from streamlit.testing.v1 import AppTest

from utils import ding_minutes, github_backup_sync


def make_docx(path, paragraphs):
    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    doc.save(path)


class DingMinutesTest(unittest.TestCase):
    def test_default_watch_dir_points_to_downloads(self):
        self.assertEqual(
            r"C:\Users\Yao\Downloads",
            ding_minutes.DEFAULT_CONFIG["watch_dir"],
        )

    def test_matches_ding_docx_rules(self):
        self.assertTrue(ding_minutes.matches_ding_docx("export_1779631538223.docx"))
        self.assertTrue(ding_minutes.matches_ding_docx("dt20260524.docx"))
        self.assertTrue(ding_minutes.matches_ding_docx("DT_meeting.docx"))
        self.assertTrue(ding_minutes.matches_ding_docx("会议原文.docx"))
        self.assertTrue(ding_minutes.matches_ding_docx("2026-05-28_原文_座谈.docx"))
        self.assertTrue(ding_minutes.matches_ding_docx("2025-12-24 10_50 记录_原文.docx"))
        self.assertTrue(ding_minutes.matches_ding_docx("钉钉录音转文字.docx"))
        self.assertFalse(ding_minutes.matches_ding_docx("meeting.docx"))
        self.assertFalse(ding_minutes.matches_ding_docx("原文.txt"))
        self.assertFalse(ding_minutes.matches_ding_docx("export_1779631538223.txt"))
        self.assertFalse(ding_minutes.matches_ding_docx("~$export_1779631538223.docx"))
        self.assertFalse(ding_minutes.matches_ding_docx("~$会议原文.docx"))

    def test_build_scan_window_uses_previous_1900_to_current_1900(self):
        now = datetime(2026, 5, 24, 20, 30)

        start, end = ding_minutes.build_scan_window(now=now)

        self.assertEqual(datetime(2026, 5, 23, 19, 0), start)
        self.assertEqual(datetime(2026, 5, 24, 19, 0), end)

    def test_build_scan_window_before_1900_uses_yesterday_window(self):
        now = datetime(2026, 5, 24, 18, 30)

        start, end = ding_minutes.build_scan_window(now=now)

        self.assertEqual(datetime(2026, 5, 22, 19, 0), start)
        self.assertEqual(datetime(2026, 5, 23, 19, 0), end)

    def test_database_inserts_lists_and_updates_remark(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "ding_minutes.db")
            cloud_path = os.path.join(tmpdir, "ding_minutes_cloud.json")
            with (
                patch.object(ding_minutes, "DB_PATH", db_path),
                patch.object(ding_minutes, "CLOUD_EXPORT_PATH", cloud_path),
            ):
                ding_minutes.init_db()
                record_id = ding_minutes.upsert_file_record(
                    {
                        "file_name": "export_1.docx",
                        "file_path": r"E:\GoogleDrive\Ding2026\export_1.docx",
                        "created_at_file": "2026-05-24T18:00:00",
                        "modified_at_file": "2026-05-24T18:01:00",
                        "file_size": 123,
                        "content_hash": "hash-1",
                        "original_text": "原始转写",
                    }
                )
                duplicate_id = ding_minutes.upsert_file_record(
                    {
                        "file_name": "export_1.docx",
                        "file_path": r"E:\GoogleDrive\Ding2026\export_1.docx",
                        "created_at_file": "2026-05-24T18:00:00",
                        "modified_at_file": "2026-05-24T18:01:00",
                        "file_size": 123,
                        "content_hash": "hash-1",
                        "original_text": "原始转写",
                    }
                )
                ding_minutes.update_remark(record_id, "后续写新闻稿")

                records = ding_minutes.get_records()

        self.assertEqual(record_id, duplicate_id)
        self.assertEqual(1, len(records))
        self.assertEqual("后续写新闻稿", records[0]["remark"])

    def test_scan_once_processes_matching_files_in_window_with_fake_ai(self):
        class FakeClient:
            def summarize(self, text):
                return "整理稿：" + text[:20]

        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir) / "Ding2026"
            watch_dir.mkdir()
            matching_path = watch_dir / "export_1779631538223.docx"
            outside_name_path = watch_dir / "meeting.docx"
            make_docx(matching_path, ["今天讨论了专业建设。", "后续需要整理材料。"])
            make_docx(outside_name_path, ["不应被处理"])
            db_path = os.path.join(tmpdir, "ding_minutes.db")
            cloud_path = os.path.join(tmpdir, "ding_minutes_cloud.json")

            with (
                patch.object(ding_minutes, "DB_PATH", db_path),
                patch.object(ding_minutes, "CLOUD_EXPORT_PATH", cloud_path),
            ):
                result = ding_minutes.scan_once(
                    config={"watch_dir": str(watch_dir), "model": "deepseek-v4-pro"},
                    now=datetime(2026, 5, 24, 20, 0),
                    ai_client=FakeClient(),
                    stat_func=lambda path: ding_minutes.FileStat(
                        created_at=datetime(2026, 5, 24, 18, 30),
                        modified_at=datetime(2026, 5, 24, 18, 35),
                        size=os.path.getsize(path),
                    ),
                )
                records = ding_minutes.get_records()

        self.assertEqual(1, result["processed"])
        self.assertEqual(1, len(records))
        self.assertEqual("done", records[0]["status"])
        self.assertIn("专业建设", records[0]["original_text"])
        self.assertIn("整理稿", records[0]["ai_summary"])

    def test_generate_summary_for_record_updates_pending_record(self):
        class FakeClient:
            def summarize(self, text):
                return "重新整理：" + text

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "ding_minutes.db")
            cloud_path = os.path.join(tmpdir, "ding_minutes_cloud.json")
            with (
                patch.object(ding_minutes, "DB_PATH", db_path),
                patch.object(ding_minutes, "CLOUD_EXPORT_PATH", cloud_path),
            ):
                ding_minutes.init_db()
                record_id = ding_minutes.upsert_file_record(
                    {
                        "file_name": "dt001.docx",
                        "file_path": r"E:\GoogleDrive\Ding2026\dt001.docx",
                        "created_at_file": "2026-05-24T18:00:00",
                        "modified_at_file": "2026-05-24T18:01:00",
                        "file_size": 123,
                        "content_hash": "hash-retry",
                        "original_text": "需要重新整理的原文",
                    }
                )

                ding_minutes.generate_summary_for_record(record_id, FakeClient(), "deepseek-v4-pro")
                record = ding_minutes.get_records()[0]

        self.assertEqual("done", record["status"])
        self.assertEqual("重新整理：需要重新整理的原文", record["ai_summary"])

    def test_update_cloud_remark_edits_synced_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = os.path.join(tmpdir, "ding_minutes_cloud.json")
            Path(export_path).write_text(
                """
{
  "generated_at": "2026-05-25T20:00:00",
  "record_count": 1,
  "records": [
    {
      "id": 7,
      "file_name": "export_7.docx",
      "status": "done",
      "remark": ""
    }
  ]
}
""".strip()
                + "\n",
                encoding="utf-8",
            )

            ding_minutes.update_cloud_remark(7, "分类：学生座谈", path=export_path)
            payload = ding_minutes.load_cloud_export(export_path)

        self.assertEqual("分类：学生座谈", payload["records"][0]["remark"])

    def test_recorder_page_is_retired_without_data_access_or_operational_controls(self):
        page_path = Path(__file__).resolve().parents[1] / "pages" / "02_11_recorder.py"

        with ExitStack() as stack:
            for function in ("init_db", "load_config", "get_records", "load_cloud_export", "scan_once"):
                stack.enter_context(patch.object(ding_minutes, function, side_effect=AssertionError("no data access")))
            for function in ("download_file_from_github", "sync_file_to_github"):
                stack.enter_context(patch.object(github_backup_sync, function, side_effect=AssertionError("no remote sync")))
            app = AppTest.from_file(str(page_path), default_timeout=10).run()
            app.run()

        self.assertFalse(app.exception)
        self.assertEqual("M11 · Recorder_笔记 ❌", app.title[0].value)
        self.assertIn("已停用", app.warning[0].value)
        self.assertIn("archived", app.caption[-1].value)
        self.assertEqual(["回到主页"], [button.label for button in app.button])
        self.assertEqual(0, len(app.text_input))
        self.assertEqual(0, len(app.text_area))
        self.assertEqual(0, len(app.metric))

    def test_retired_recorder_cli_entrypoints_do_not_scan_export_or_sync(self):
        with ExitStack() as stack:
            for function in ("init_db", "scan_once", "sync_cloud_export", "get_records"):
                stack.enter_context(patch.object(ding_minutes, function, side_effect=AssertionError("no scan or export")))
            stack.enter_context(patch.object(github_backup_sync, "sync_file_to_github", side_effect=AssertionError("no remote sync")))
            for module_name in ("scripts.scan_ding_minutes", "scripts.sync_recorder_cloud"):
                with self.subTest(entrypoint=module_name):
                    output = io.StringIO()
                    with redirect_stdout(output):
                        module = importlib.import_module(module_name)
                        result = module.main()
                    self.assertEqual(0, result)
                    self.assertIn("Recorder 已停用", output.getvalue())

    @unittest.skipUnless(os.name == "nt", "Windows batch entry point")
    def test_daily_recorder_launcher_exits_without_creating_files(self):
        batch_path = Path(__file__).resolve().parents[1] / "每日Recorder扫描.bat"
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", str(batch_path)],
                cwd=tmpdir, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Recorder is retired", result.stdout)
            self.assertEqual([], list(Path(tmpdir).iterdir()))


if __name__ == "__main__":
    unittest.main()
