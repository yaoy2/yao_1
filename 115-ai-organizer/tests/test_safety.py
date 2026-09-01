import tempfile
import unittest
from pathlib import Path

from app.config import load_settings
from app.safety import (
    PathNotAllowedError,
    WriteDisabledError,
    assert_under_allowed_root,
    assert_write_blocked,
    is_under_root,
)


class SafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        env_path = Path(self.tmpdir.name) / ".env"
        env_path.write_text(
            "\n".join(
                [
                    "OPENLIST_BASE_URL=http://127.0.0.1:5244",
                    "OPENLIST_USERNAME=organizer-readonly",
                    "OPENLIST_PASSWORD=secret",
                    "ALLOWED_ROOT=/云下载",
                    "WRITE_MODE=false",
                ]
            ),
            encoding="utf-8",
        )
        self.settings = load_settings(env_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_path_guard_allows_yun_download_only(self):
        self.assertTrue(is_under_root("/云下载/电影", "/云下载"))
        self.assertTrue(is_under_root("/云下载", "/云下载"))
        self.assertFalse(is_under_root("/文档", "/云下载"))
        self.assertFalse(is_under_root("/云下载备份", "/云下载"))
        with self.assertRaises(PathNotAllowedError):
            assert_under_allowed_root("/我的接收", self.settings)

    def test_write_operations_are_blocked(self):
        for operation in ("mkdir", "move", "rename"):
            with self.assertRaises(WriteDisabledError):
                assert_write_blocked(operation, self.settings)

    def test_delete_is_always_forbidden(self):
        with self.assertRaises(WriteDisabledError) as ctx:
            assert_write_blocked("delete", self.settings)
        self.assertIn("禁止删除", str(ctx.exception))

    def test_write_mode_true_still_blocked_in_generic_entry(self):
        env_path = Path(self.tmpdir.name) / ".env2"
        env_path.write_text("WRITE_MODE=true\nALLOWED_ROOT=/云下载\n", encoding="utf-8")
        settings = load_settings(env_path)
        with self.assertRaises(WriteDisabledError) as ctx:
            assert_write_blocked("move", settings)
        self.assertIn("带确认码的审核清单执行器", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
