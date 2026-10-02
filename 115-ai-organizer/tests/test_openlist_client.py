import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from app.config import Settings
from app.db import connect, file_stats
from app.openlist_client import OpenListClient, OpenListError, extract_native_id, to_api_path
from app.safety import PathNotAllowedError, WriteDisabledError
from app.scanner import scan


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

    def test_to_api_path_strips_readonly_base_path(self):
        self.assertEqual("/", to_api_path("/云下载", "/云下载"))
        self.assertEqual("/电影", to_api_path("/云下载/电影", "/云下载"))
        self.assertEqual("/云下载", to_api_path("/云下载", "/"))
        self.assertEqual("/云下载", to_api_path("/云下载", ""))

    def test_native_id_from_common_keys(self):
        self.assertEqual("99", extract_native_id({"fid": "99", "name": "a.mkv"}))
        self.assertEqual("", extract_native_id({"name": "a.mkv", "id": ""}))


class OpenListPaginationTest(unittest.TestCase):
    @staticmethod
    def _item(number):
        return {"id": str(number), "name": f"clip-{number}.mp4", "is_dir": False, "size": 10}

    def _client(self, *listings):
        client = OpenListClient(settings())
        client.token = "test-token"
        client.list_dir = MagicMock(side_effect=listings)
        return client

    def test_all_pages_use_existing_list_api(self):
        session = MagicMock()
        responses = []
        items = [self._item(i) for i in range(1, 4)]
        for page in (items[:2], items[2:]):
            response = MagicMock(status_code=200)
            response.json.return_value = {"code": 200, "data": {"content": page, "total": "3"}}
            responses.append(response)
        session.request.side_effect = responses
        client = OpenListClient(settings(), session=session)
        client.token = "test-token"
        client._user_loaded = True
        client.user_base_path = "/云下载"

        listing = client.list_all("/云下载", per_page=2)

        self.assertEqual(items, listing["content"])
        self.assertEqual(3, listing["total"])
        self.assertEqual([1, 2], [call.kwargs["json"]["page"] for call in session.request.call_args_list])
        for call in session.request.call_args_list:
            self.assertTrue(call.args[1].endswith("/api/fs/list"))
            self.assertEqual("/", call.kwargs["json"]["path"])
            self.assertEqual(2, call.kwargs["json"]["per_page"])

    def test_missing_total_continues_until_short_page(self):
        first = [self._item(1), self._item(2)]
        for last in ([], [self._item(3)]):
            with self.subTest(last=last):
                client = self._client({"content": first}, {"content": last})
                listing = client.list_all("/云下载", per_page=2)
                self.assertEqual(first + last, listing["content"])
                self.assertEqual(len(first + last), listing["total"])
                self.assertEqual(2, client.list_dir.call_count)

    def test_empty_directory_is_valid(self):
        for total in (None, 0):
            with self.subTest(total=total):
                client = self._client({"content": [], "total": total})
                self.assertEqual([], client.list_all("/云下载")["content"])
                self.assertEqual(1, client.list_dir.call_count)

    def test_explicit_null_content_requires_zero_total(self):
        for total in (0, "0"):
            with self.subTest(total=total):
                client = self._client({"content": None, "total": total})
                self.assertEqual([], client.list_all("/云下载")["content"])
                self.assertEqual(1, client.list_dir.call_count)
        for listing in ({"total": 0}, {"content": None}, {"content": None, "total": 1}):
            with self.subTest(listing=listing):
                client = self._client(listing)
                with self.assertRaisesRegex(OpenListError, "列表格式异常"):
                    client.list_all("/云下载")

    def test_rejects_short_page_before_known_total(self):
        client = self._client({"content": [self._item(1)], "total": 3})
        with self.assertRaisesRegex(OpenListError, "分页提前结束"):
            client.list_all("/云下载", per_page=2)

    def test_rejects_malformed_listing(self):
        for listing in (None, [], {}, {"content": None}, {"content": {}}, {"content": [None]}):
            with self.subTest(listing=listing):
                client = self._client(listing)
                with self.assertRaisesRegex(OpenListError, "列表格式异常"):
                    client.list_all("/云下载")

    def test_rejects_invalid_total(self):
        for total in ("unknown", -1, True, 1.5):
            with self.subTest(total=total):
                client = self._client({"content": [], "total": total})
                with self.assertRaisesRegex(OpenListError, "总数格式异常"):
                    client.list_all("/云下载")

    def test_rejects_repeated_page(self):
        page = {"content": [self._item(1), self._item(2)]}
        client = self._client(page, page)
        with self.assertRaisesRegex(OpenListError, "重复返回同一页"):
            client.list_all("/云下载", per_page=2)
        self.assertEqual(2, client.list_dir.call_count)

    def test_rejects_native_id_overlap_between_different_pages(self):
        client = self._client(
            {"content": [self._item(1), self._item(2)], "total": 4},
            {"content": [self._item(2), self._item(3)], "total": 4},
        )
        with self.assertRaisesRegex(OpenListError, "分页之间返回重复文件 ID"):
            client.list_all("/云下载", per_page=2)
        self.assertEqual(2, client.list_dir.call_count)

    def test_repeated_id_within_single_page_is_left_for_scanner(self):
        items = [self._item(1), {**self._item(1), "name": "alias.mp4"}]
        client = self._client({"content": items, "total": 2})
        self.assertEqual(items, client.list_all("/云下载", per_page=2)["content"])

    def test_rejects_changed_or_inconsistent_total(self):
        first = {"content": [self._item(1), self._item(2)], "total": 3}
        for second in (
            {"content": [self._item(3)], "total": 4},
            {"content": [self._item(3), self._item(4)], "total": 3},
        ):
            with self.subTest(second=second):
                client = self._client(first, second)
                with self.assertRaises(OpenListError):
                    client.list_all("/云下载", per_page=2)

    def test_directory_entry_limit_is_enforced(self):
        client = self._client(
            {"content": [self._item(1), self._item(2)]},
            {"content": [self._item(3), self._item(4)]},
        )
        with self.assertRaisesRegex(OpenListError, "安全上限 3"):
            client.list_all("/云下载", per_page=2, max_directory_entries=3)
        self.assertEqual(2, client.list_dir.call_count)

    def test_default_scanner_reads_beyond_first_200_items(self):
        for max_files in (0, 201):
            with self.subTest(max_files=max_files), tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                scan_settings = replace(settings(), db_path=root / "index.sqlite", log_path=root / "test.log")
                items = [self._item(i) for i in range(1, 202)]
                client = self._client(
                    {"content": items[:200], "total": 201},
                    {"content": items[200:], "total": 201},
                )
                result = scan(scan_settings, client=client, max_files=max_files)
                self.assertEqual("ok", result.status)
                self.assertEqual(201, result.file_count)
                self.assertEqual(2, client.list_dir.call_count)
                with closing(connect(scan_settings.db_path)) as conn:
                    self.assertEqual(201, file_stats(conn)["file_count"])


if __name__ == "__main__":
    unittest.main()
