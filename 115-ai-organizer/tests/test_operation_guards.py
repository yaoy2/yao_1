import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from app.config import Settings
from app.db import db_session, set_plan_approved, upsert_plan
from app.operations import (
    Open115Writer,
    OperationError,
    approve_safe_plans,
    build_manifest,
    confirmation_code,
    execute_manifest,
)
from app.scanner import scan


class OperationScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        root = Path(self.tmpdir.name)
        self.settings = Settings(
            openlist_base_url="http://example.invalid", openlist_username="", openlist_password="",
            openlist_mount_path="/云下载", allowed_root="/云下载", write_mode=False,
            default_max_files=50, default_scan_depth=2, default_scan_dir="/云下载",
            db_path=root / "index.sqlite", log_path=root / "organizer.log",
        )
        self.file = {"name": "会议录屏_2024.mp4", "file_id": "file-1", "parent_id": "123",
                     "is_dir": False, "size": 200, "hash_info": {"sha1": "unique-hash"}}
        scan(self.settings, list_fn=lambda _: {"content": [self.file]}, scan_root_id="123")
        approve_safe_plans(self.settings)
        self.manifest = build_manifest(self.settings, scan_root_id="123", scan_root_path="/云下载")
        self.writer = MagicMock(scan_root_id="123")
        self.writer._item_id.side_effect = lambda item: item["fid"]
        self.writer._item_name.side_effect = lambda item: item["fn"]
        self.writer.list_folder.return_value = [{"fid": "file-1", "fn": self.file["name"]}]
        self.writer.ensure_directory.return_value = "target-1"
        self.writer.find_child.return_value = None
        self.writer.verify_item.return_value = True

    def execute(self, manifest=None, settings=None):
        manifest = manifest if manifest is not None else self.manifest
        manifest["confirmation_code"] = confirmation_code(manifest)
        return execute_manifest(settings or self.settings, manifest, manifest["confirmation_code"], self.writer)

    def assert_no_writes(self):
        self.writer.ensure_directory.assert_not_called()
        self.writer.rename.assert_not_called()
        self.writer.move.assert_not_called()

    def test_subtree_manifest_blocks_files_from_parent_directory(self):
        manifest = build_manifest(self.settings, scan_root_id="456", scan_root_path="/云下载/子目录")
        self.assertEqual([], manifest["operations"])
        self.assertEqual(1, manifest["blocked_count"])
        self.assertIn("来源路径超出扫描根目录", manifest["blocked"][0]["reasons"])

    def test_blocked_outside_source_does_not_reserve_inside_target(self):
        inside = {**self.file, "file_id": "file-2", "parent_id": "456",
                  "hash_info": {"sha1": "different-hash"}}
        tree = {
            "/云下载": [self.file, {"name": "子目录", "file_id": "456", "is_dir": True}],
            "/云下载/子目录": [inside],
        }
        scan(self.settings, list_fn=lambda path: {"content": tree[path]}, scan_root_id="123")
        approve_safe_plans(self.settings)
        manifest = build_manifest(self.settings, scan_root_id="456", scan_root_path="/云下载/子目录")
        self.assertEqual(1, manifest["operation_count"])
        self.assertEqual(1, manifest["blocked_count"])
        self.assertEqual("file-2", manifest["operations"][0]["file_id"])

    def test_execution_rejects_legacy_manifest_with_source_outside_selected_root(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["scan_root_path"] = "/云下载/子目录"
        with self.assertRaisesRegex(OperationError, "来源路径超出"):
            self.execute(manifest)
        self.assert_no_writes()
        self.writer.list_folder.assert_not_called()

    def test_execution_rechecks_current_allowed_root(self):
        with self.assertRaisesRegex(OperationError, "超出当前允许范围"):
            self.execute(settings=replace(self.settings, allowed_root="/云下载/子目录"))
        self.assert_no_writes()

    def test_execution_rejects_target_parts_that_escape_root(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["operations"][0]["target_parent_parts"] = ["已整理", "..", "..", "私人文件"]
        with self.assertRaisesRegex(OperationError, "目标目录或文件名无效"):
            self.execute(manifest)
        self.assert_no_writes()

    def test_execution_rejects_declared_target_different_from_actual_parts(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["operations"][0]["target_path"] = "/云下载/已整理/其他/另一个.mp4"
        with self.assertRaisesRegex(OperationError, "目标路径与实际操作目录不一致"):
            self.execute(manifest)
        self.assert_no_writes()

    def test_execution_rejects_source_path_changed_after_manifest_creation(self):
        with db_session(self.settings.db_path) as conn:
            conn.execute("UPDATE files SET full_path='/私人文件/会议录屏_2024.mp4' WHERE file_id='file-1'")
        result = self.execute()
        self.assertEqual(1, result.failed)
        self.assert_no_writes()

    def test_old_manifest_cannot_execute_after_changed_target_is_reapproved(self):
        with db_session(self.settings.db_path) as conn:
            row = dict(conn.execute("SELECT * FROM organize_plans").fetchone())
            row["suggested_path"] = f"/普通视频/新分组/{row['suggested_name']}"
            plan_id = upsert_plan(conn, row)
            set_plan_approved(conn, [plan_id], True)
        result = self.execute()
        self.assertEqual(1, result.failed)
        self.assertIn("生成清单后发生变化", result.errors[0]["error"])
        self.assert_no_writes()
        self.writer.list_folder.assert_not_called()
        with db_session(self.settings.db_path) as conn:
            current = conn.execute("SELECT execute_status FROM organize_plans WHERE id=?", (plan_id,)).fetchone()
            self.assertEqual("not_executed", current["execute_status"])

    def test_execution_rejects_plan_missing_from_latest_scan(self):
        scan(self.settings, list_fn=lambda _: {"content": []}, scan_root_id="123")
        result = self.execute()
        self.assertEqual(1, result.failed)
        self.assertIn("当前扫描快照", result.errors[0]["error"])
        self.assert_no_writes()

    def test_completed_plans_are_neither_reapproved_nor_reemitted(self):
        for status in ("success", "already_done"):
            with self.subTest(status=status):
                with db_session(self.settings.db_path) as conn:
                    conn.execute("UPDATE organize_plans SET execute_status=?", (status,))
                self.assertEqual({"eligible": 0, "approved": 0}, approve_safe_plans(self.settings))
                manifest = build_manifest(self.settings, scan_root_id="123", scan_root_path="/云下载")
                self.assertEqual([], manifest["operations"])

    def test_reexecuting_successful_manifest_skips_remote_writes(self):
        self.assertEqual(1, self.execute().succeeded)
        self.writer.reset_mock()
        second = self.execute()
        self.assertEqual(1, second.skipped)
        self.assertEqual(0, second.failed)
        self.assert_no_writes()
        self.writer.list_folder.assert_not_called()

    def test_stale_manifest_does_not_erase_previous_success(self):
        self.assertEqual(1, self.execute().succeeded)
        scan(self.settings, list_fn=lambda _: {"content": []}, scan_root_id="123")
        self.writer.reset_mock()
        self.assertEqual(1, self.execute().failed)
        self.assert_no_writes()
        with db_session(self.settings.db_path) as conn:
            current = conn.execute("SELECT execute_status FROM organize_plans").fetchone()
            self.assertEqual("success", current["execute_status"])

    def test_source_rename_collision_stops_before_directory_creation(self):
        new_name = "整理后的录屏.mp4"
        with db_session(self.settings.db_path) as conn:
            conn.execute("UPDATE organize_plans SET suggested_name=?, suggested_path=?",
                         (new_name, f"/普通视频/{new_name}"))
        self.manifest = build_manifest(self.settings, scan_root_id="123", scan_root_path="/云下载")
        self.writer.list_folder.return_value.append({"fid": "file-2", "fn": new_name})
        result = self.execute()
        self.assertEqual(1, result.failed)
        self.assertIn("来源目录已有", result.errors[0]["error"])
        self.assert_no_writes()


class WriterPaginationTest(unittest.TestCase):
    @staticmethod
    def page(start, count):
        return [{"fid": str(i), "fn": f"item-{i}.mp4", "fc": "1"}
                for i in range(start, start + count)]

    def writer(self, pages, **kwargs):
        writer = Open115Writer("fake-token", "123", request_interval=0, **kwargs)
        writer._request = MagicMock(side_effect=pages)
        return writer

    def test_missing_or_invalid_count_keeps_paging_and_finds_collision(self):
        for count in (None, "invalid"):
            with self.subTest(count=count):
                writer = self.writer([{"data": self.page(1, 200), "count": count},
                                      {"data": self.page(201, 1), "count": count}])
                self.assertEqual("201", writer.find_child("123", "item-201.mp4")["fid"])
                self.assertEqual(2, writer._request.call_count)

    def test_reported_total_stops_without_extra_request(self):
        writer = self.writer([{"data": self.page(1, 200), "count": 200}])
        self.assertEqual(200, len(writer.list_folder("123")))
        self.assertEqual(1, writer._request.call_count)

    def test_explicit_empty_directory_is_valid(self):
        for data in (None, []):
            with self.subTest(data=data):
                writer = self.writer([{"data": data, "count": 0}])
                self.assertEqual([], writer.list_folder("123"))
                self.assertEqual(1, writer._request.call_count)

    def test_short_page_before_total_is_rejected(self):
        writer = self.writer([{"data": self.page(1, 1), "count": 2}])
        with self.assertRaisesRegex(OperationError, "提前结束"):
            writer.find_child("123", "missing.mp4")

    def test_invalid_data_is_rejected(self):
        for data in (None, {}, ["invalid"]):
            with self.subTest(data=data):
                writer = self.writer([{"data": data}])
                with self.assertRaisesRegex(OperationError, "列表格式异常"):
                    writer.list_folder("123")

    def test_repeated_page_stops_instead_of_looping(self):
        page = {"data": self.page(1, 200)}
        writer = self.writer([page, page])
        with self.assertRaisesRegex(OperationError, "重复ID"):
            writer.list_folder("123")
        self.assertEqual(2, writer._request.call_count)

    def test_unknown_total_has_a_bounded_entry_limit(self):
        writer = self.writer([{"data": self.page(1, 200)}, {"data": self.page(201, 1)}],
                             max_directory_entries=200)
        with self.assertRaisesRegex(OperationError, "安全上限"):
            writer.list_folder("123")
        self.assertEqual(2, writer._request.call_count)

    def test_changing_total_is_rejected(self):
        writer = self.writer([{"data": self.page(1, 200), "count": 202},
                              {"data": self.page(201, 1), "count": 201}])
        with self.assertRaisesRegex(OperationError, "分页期间发生变化"):
            writer.list_folder("123")


if __name__ == "__main__":
    unittest.main()
