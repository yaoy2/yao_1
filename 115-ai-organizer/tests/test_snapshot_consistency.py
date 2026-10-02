import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.config import Settings
from app.db import (
    connect,
    current_snapshot_start,
    db_session,
    file_stats,
    init_db,
    list_plans,
    set_plan_approved,
    set_plan_execute_status,
    upsert_file,
)
from app.planner import rebuild_plans
from app.scanner import scan


class SnapshotConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.settings = Settings(
            openlist_base_url="http://127.0.0.1:5244",
            openlist_username="test",
            openlist_password="",
            openlist_mount_path="/root",
            allowed_root="/root",
            write_mode=False,
            default_max_files=50,
            default_scan_depth=8,
            default_scan_dir="/root",
            db_path=root / "index.sqlite",
            log_path=root / "organizer.log",
        )
        init_db(self.settings.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    @staticmethod
    def _file(name, file_id="", size=10):
        return {"name": name, "file_id": file_id, "size": size, "is_dir": False}

    def _scan_files(self, *items):
        return scan(self.settings, list_fn=lambda path: {"content": list(items)})

    def test_rebuild_excludes_historical_series_members(self):
        first = self._file("Travel 第01集.mp4", "file-1")
        second = self._file("Travel 第02集.mp4", "file-2")
        self._scan_files(first, second)
        self.assertEqual(2, rebuild_plans(self.settings))
        with closing(connect(self.settings.db_path)) as conn:
            historical_plan = dict(
                conn.execute("SELECT * FROM organize_plans WHERE file_id = 'file-2'").fetchone()
            )
            self.assertEqual("系列", historical_plan["category"])

        self._scan_files(first)
        self.assertEqual(1, rebuild_plans(self.settings))
        with closing(connect(self.settings.db_path)) as conn:
            plans = list_plans(conn)
            self.assertEqual(["Travel 第01集.mp4"], [row["original_name"] for row in plans])
            self.assertEqual("待识别", plans[0]["category"])
            self.assertEqual("low", plans[0]["confidence"])
            unchanged_history = dict(
                conn.execute("SELECT * FROM organize_plans WHERE file_id = 'file-2'").fetchone()
            )
            self.assertEqual(historical_plan, unchanged_history)

    def test_scan_without_ids_replaces_current_snapshot(self):
        self._scan_files(self._file("old.mp4", "old-id"))
        with db_session(self.settings.db_path) as conn:
            set_plan_approved(conn, [list_plans(conn)[0]["id"]], True)

        result = self._scan_files(self._file("current.mp4", size=17))
        self.assertEqual("stopped_no_native_id", result.status)
        self.assertEqual(1, rebuild_plans(self.settings))
        with closing(connect(self.settings.db_path)) as conn:
            stats = file_stats(conn)
            self.assertEqual(1, stats["file_count"])
            self.assertEqual(17, stats["total_size"])
            self.assertEqual({"待识别": 1}, stats["categories"])
            self.assertEqual("stopped_no_native_id", stats["latest_run"]["status"])
            self.assertEqual(["current.mp4"], [row["original_name"] for row in list_plans(conn)])
            self.assertEqual([], list_plans(conn, approved="approved"))
            self.assertEqual(stats["latest_run"]["started_at"], current_snapshot_start(conn))

        self._scan_files(self._file("next.mp4", "next-id", size=23))
        with closing(connect(self.settings.db_path)) as conn:
            self.assertEqual(["next.mp4"], [row["original_name"] for row in list_plans(conn)])
            self.assertEqual(23, file_stats(conn)["total_size"])

    def test_failed_scan_preserves_index_approval_and_error_record(self):
        self._scan_files(self._file("original.mp4", "stable-id"))
        with db_session(self.settings.db_path) as conn:
            plan_id = list_plans(conn)[0]["id"]
            set_plan_approved(conn, [plan_id], True)
            set_plan_execute_status(conn, plan_id, "success")
            original_files = [dict(row) for row in conn.execute("SELECT * FROM files ORDER BY id")]
            original_plans = list_plans(conn)
            original_snapshot = current_snapshot_start(conn)

        failure = RuntimeError("synthetic directory listing failure")
        visited = []

        def partial_tree(path):
            visited.append(path)
            if path != "/root":
                raise failure
            return {"content": [
                self._file("renamed.mp4", "stable-id", size=99),
                self._file("uncommitted.mp4", "new-id"),
                {"name": "child", "file_id": "child-id", "is_dir": True},
            ]}

        with self.assertRaises(RuntimeError) as caught:
            scan(self.settings, list_fn=partial_tree)
        self.assertIs(failure, caught.exception)
        self.assertEqual(["/root", "/root/child"], visited)
        with closing(connect(self.settings.db_path)) as conn:
            self.assertEqual(
                original_files,
                [dict(row) for row in conn.execute("SELECT * FROM files ORDER BY id")],
            )
            self.assertEqual(original_plans, list_plans(conn))
            self.assertEqual(original_snapshot, current_snapshot_start(conn))
            runs = [dict(row) for row in conn.execute("SELECT * FROM scan_runs ORDER BY id")]
            self.assertEqual(["ok", "error"], [row["status"] for row in runs])
            self.assertEqual(str(failure), runs[-1]["error"])
            self.assertTrue(runs[-1]["finished_at"])
            stats = file_stats(conn)
            self.assertEqual(1, stats["file_count"])
            self.assertEqual(10, stats["total_size"])
            self.assertEqual("error", stats["latest_run"]["status"])

    def test_first_failed_scan_keeps_error_without_partial_index(self):
        def unavailable(path):
            raise RuntimeError("unavailable")

        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            scan(self.settings, list_fn=unavailable)
        with closing(connect(self.settings.db_path)) as conn:
            self.assertEqual("", current_snapshot_start(conn))
            self.assertEqual(0, file_stats(conn)["total_items"])
            self.assertEqual([], list_plans(conn))
            self.assertEqual("error", file_stats(conn)["latest_run"]["status"])

    def test_manually_indexed_files_remain_available_without_scan_run(self):
        with db_session(self.settings.db_path) as conn:
            upsert_file(conn, {
                "name": "manual.mp4",
                "full_path": "/root/manual.mp4",
                "extension": ".mp4",
                "size": 7,
            })
        self.assertEqual(1, rebuild_plans(self.settings))
        with closing(connect(self.settings.db_path)) as conn:
            self.assertEqual("", current_snapshot_start(conn))
            self.assertEqual(1, file_stats(conn)["file_count"])
            self.assertEqual(["manual.mp4"], [row["original_name"] for row in list_plans(conn)])


if __name__ == "__main__":
    unittest.main()
