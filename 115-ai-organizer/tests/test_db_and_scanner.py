import tempfile
import unittest
from pathlib import Path

from app.config import load_settings
from app.db import connect, file_stats, init_db, list_plans, set_plan_approved
from app.openlist_client import extract_native_id
from app.scanner import scan


def fake_tree(path: str):
    catalog = {
        "/云下载": [
            {"name": "电影", "is_dir": True, "size": 0},
            {"name": "random_clip.mp4", "is_dir": False, "size": 123, "modified": "2026-01-01T00:00:00Z"},
        ],
        "/云下载/电影": [
            {
                "name": "流浪地球2.2023.1080p.BluRay.mkv",
                "is_dir": False,
                "size": 1024,
                "id": "115fid-earth",
                "created": "2023-01-01T00:00:00Z",
                "modified": "2023-01-02T00:00:00Z",
                "hash_info": {"sha1": "abc"},
            },
            {
                "name": "三体.2023.S01E01.mkv",
                "is_dir": False,
                "size": 2048,
                "id": "115fid-threebody",
            },
        ],
    }
    return {"content": catalog.get(path, [])}


class DbAndScannerTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.db_path = root / "115_index.sqlite"
        env_path = root / ".env"
        env_path.write_text(
            "\n".join(
                [
                    "OPENLIST_BASE_URL=http://127.0.0.1:5244",
                    "OPENLIST_USERNAME=organizer-readonly",
                    "OPENLIST_PASSWORD=secret",
                    "ALLOWED_ROOT=/云下载",
                    "DEFAULT_SCAN_DIR=/云下载",
                    f"DB_PATH={self.db_path}",
                    f"LOG_PATH={root / 'organizer.log'}",
                    "WRITE_MODE=false",
                ]
            ),
            encoding="utf-8",
        )
        self.settings = load_settings(env_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_scan_limit_and_incremental_upsert(self):
        first = scan(self.settings, scan_dir="/云下载", max_depth=3, max_files=2, list_fn=fake_tree)
        self.assertEqual(2, first.file_count)
        self.assertTrue(first.native_file_id_found)

        conn = connect(self.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM files WHERE is_directory = 0").fetchone()["n"]
            self.assertEqual(2, count)
        finally:
            conn.close()

        second = scan(self.settings, scan_dir="/云下载", max_depth=3, max_files=50, list_fn=fake_tree)
        self.assertGreaterEqual(second.file_count, 2)
        conn = connect(self.db_path)
        try:
            files = conn.execute(
                "SELECT full_path, file_id, file_id_source FROM files WHERE is_directory = 0 ORDER BY full_path"
            ).fetchall()
            paths = [row["full_path"] for row in files]
            self.assertEqual(len(paths), len(set(paths)))
            native = [row for row in files if row["file_id_source"] == "native"]
            self.assertGreaterEqual(len(native), 2)
            stats = file_stats(conn)
            self.assertEqual(len(files), stats["file_count"])
            self.assertGreater(stats["total_size"], 0)
        finally:
            conn.close()

    def test_scan_stops_without_fabricating_file_id(self):
        def no_id_tree(path: str):
            return {
                "content": [
                    {"name": "a.mp4", "is_dir": False, "size": 1},
                    {"name": "b.mp4", "is_dir": False, "size": 2},
                ]
            }

        result = scan(self.settings, scan_dir="/云下载", max_depth=1, max_files=50, list_fn=no_id_tree)
        self.assertEqual("stopped_no_native_id", result.status)
        self.assertFalse(result.native_file_id_found)
        conn = connect(self.db_path)
        try:
            rows = conn.execute("SELECT file_id, file_id_source, name FROM files WHERE is_directory = 0").fetchall()
            self.assertEqual(2, len(rows))
            for row in rows:
                self.assertEqual("", row["file_id"])
                self.assertEqual("missing", row["file_id_source"])
                self.assertNotEqual(row["name"], row["file_id"])
        finally:
            conn.close()

    def test_plans_and_local_approval(self):
        scan(self.settings, scan_dir="/云下载", max_depth=3, max_files=50, list_fn=fake_tree)
        conn = connect(self.db_path)
        try:
            plans = list_plans(conn)
            self.assertGreaterEqual(len(plans), 2)
            categories = {row["category"] for row in plans}
            self.assertTrue({"电影", "电视剧", "待识别"} & categories)
            first_id = plans[0]["id"]
            set_plan_approved(conn, [first_id], True)
            conn.commit()
            approved = list_plans(conn, approved="approved")
            self.assertEqual(1, len(approved))
            self.assertEqual("not_executed", approved[0]["execute_status"])
        finally:
            conn.close()

    def test_extract_native_id_does_not_use_filename(self):
        self.assertEqual("fid-1", extract_native_id({"name": "movie.mkv", "id": "fid-1"}))
        self.assertEqual("", extract_native_id({"name": "movie.mkv", "size": 10}))

    def test_native_id_tracks_rename_without_duplicate_row(self):
        def first_tree(path: str):
            return {"content": [{
                "name": "old.mkv", "file_id": "stable-1", "parent_id": "root-1",
                "is_dir": False, "size": 10,
            }]}

        def renamed_tree(path: str):
            return {"content": [{
                "name": "new.mkv", "file_id": "stable-1", "parent_id": "root-2",
                "is_dir": False, "size": 10,
            }]}

        scan(self.settings, scan_dir="/云下载", max_files=0, list_fn=first_tree, scan_root_id="root-1")
        scan(self.settings, scan_dir="/云下载", max_files=0, list_fn=renamed_tree, scan_root_id="root-1")
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT name, full_path, parent_id FROM files WHERE file_id = 'stable-1'"
            ).fetchall()
            self.assertEqual(1, len(rows))
            self.assertEqual("new.mkv", rows[0]["name"])
            self.assertEqual("/云下载/new.mkv", rows[0]["full_path"])
            self.assertEqual("root-2", rows[0]["parent_id"])
        finally:
            conn.close()

    def test_scan_counts_repeated_native_id_once(self):
        def repeated_tree(path: str):
            return {"content": [
                {"name": "first.mkv", "file_id": "same-id", "parent_id": "root", "is_dir": False, "size": 10},
                {"name": "stale-copy.mkv", "file_id": "same-id", "parent_id": "root", "is_dir": False, "size": 10},
            ]}

        result = scan(
            self.settings,
            scan_dir="/云下载",
            max_files=0,
            list_fn=repeated_tree,
            scan_root_id="root",
        )
        self.assertEqual(1, result.file_count)
        self.assertEqual(2, result.native_id_count)
        self.assertEqual(1, result.duplicate_native_id_count)
        self.assertEqual(1, result.as_dict()["unique_native_id_count"])


if __name__ == "__main__":
    unittest.main()
