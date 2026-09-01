import unittest
from unittest.mock import MagicMock

from app.config import Settings
from app.openlist_client import OpenListClient, extract_native_id
from app.safety import PathNotAllowedError, WriteDisabledError


def settings() -> Settings:
    return Settings(
        openlist_base_url="http://127.0.0.1:5244",
        openlist_username="organizer-readonly",
        openlist_password="secret",
        openlist_mount_path="/云下载",
        allowed_root="/云下载",
        write_mode=False,
        default_max_files=50,
        default_scan_depth=8,
        default_scan_dir="/云下载",
        db_path="data/115_index.sqlite",
        log_path="logs/organizer.log",
    )


class OpenListClientTest(unittest.TestCase):
    def test_list_dir_rejects_outside_root(self):
        client = OpenListClient(settings())
        with self.assertRaises(PathNotAllowedError):
            client.list_dir("/文档")

    def test_write_methods_are_not_callable(self):
        client = OpenListClient(settings())
        with self.assertRaises(WriteDisabledError):
            client.mkdir("/云下载/new")
        with self.assertRaises(WriteDisabledError):
            client.move("/云下载/a", "/云下载/b")
        with self.assertRaises(WriteDisabledError):
            client.rename("/云下载/a", "b")
        with self.assertRaises(WriteDisabledError):
            client.delete("/云下载/a")

    def test_login_reads_token(self):
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"code": 200, "data": {"token": "abc"}}
        session.request.return_value = response
        client = OpenListClient(settings(), session=session)
        token = client.login()
        self.assertEqual("abc", token)
        self.assertEqual("abc", client.token)

    def test_native_id_from_common_keys(self):
        self.assertEqual("99", extract_native_id({"fid": "99", "name": "a.mkv"}))
        self.assertEqual("", extract_native_id({"name": "a.mkv", "id": ""}))


if __name__ == "__main__":
    unittest.main()
