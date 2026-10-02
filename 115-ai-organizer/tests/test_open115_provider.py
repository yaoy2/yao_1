import unittest
from unittest.mock import MagicMock

from app.open115_provider import Open115ReadOnlyError, Open115ReadOnlyProvider


def response(payload: dict) -> MagicMock:
    value = MagicMock()
    value.status_code = 200
    value.json.return_value = payload
    return value


class Open115ReadOnlyProviderTest(unittest.TestCase):
    def provider(self, session: MagicMock) -> Open115ReadOnlyProvider:
        return Open115ReadOnlyProvider(
            access_token="test-token",
            mounted_root_id="root-1",
            scan_root_id="child-1",
            logical_root="/云下载",
            session=session,
            sleep_fn=lambda _: None,
            request_interval=0,
            page_size=2,
        )

    def test_validates_descendant_and_preserves_native_ids(self):
        session = MagicMock()
        session.get.side_effect = [
            response(
                {
                    "state": True,
                    "data": {"paths": [{"file_id": "0"}, {"file_id": "root-1"}]},
                }
            ),
            response(
                {
                    "state": True,
                    "count": 2,
                    "data": [
                        {"fid": "dir-9", "pid": "child-1", "fc": "0", "fn": "电影"},
                        {
                            "fid": "file-8",
                            "pid": "child-1",
                            "fc": "1",
                            "fn": "a.mp4",
                            "fs": 123,
                            "sha1": "abc",
                        },
                    ],
                }
            ),
            response(
                {
                    "state": True,
                    "count": 1,
                    "data": [
                        {"fid": "file-10", "pid": "dir-9", "fc": "1", "fn": "b.mkv"}
                    ],
                }
            ),
        ]
        provider = self.provider(session)

        provider.validate_scan_root()
        root = provider.list_dir("/云下载")
        child = provider.list_dir("/云下载/电影")

        self.assertEqual("file-8", root["content"][1]["file_id"])
        self.assertEqual("file-10", child["content"][0]["file_id"])
        self.assertEqual("115_open_official", root["source"])

    def test_rejects_scan_root_outside_mounted_root(self):
        session = MagicMock()
        session.get.return_value = response(
            {"state": True, "data": {"paths": [{"file_id": "different-root"}]}}
        )
        provider = self.provider(session)

        with self.assertRaises(Open115ReadOnlyError):
            provider.validate_scan_root()

    def test_paginates_without_exceeding_reported_count(self):
        session = MagicMock()
        session.get.side_effect = [
            response(
                {
                    "state": True,
                    "count": 3,
                    "data": [
                        {"fid": "1", "fc": "1", "fn": "a"},
                        {"fid": "2", "fc": "1", "fn": "b"},
                    ],
                }
            ),
            response(
                {
                    "state": True,
                    "count": 3,
                    "data": [{"fid": "3", "fc": "1", "fn": "c"}],
                }
            ),
        ]
        provider = Open115ReadOnlyProvider(
            access_token="test-token",
            mounted_root_id="root-1",
            scan_root_id="root-1",
            logical_root="/云下载",
            session=session,
            sleep_fn=lambda _: None,
            request_interval=0,
            page_size=2,
        )

        listing = provider.list_dir("/云下载")

        self.assertEqual(3, len(listing["content"]))
        self.assertEqual(2, session.get.call_count)

    def test_paginates_when_count_is_missing_or_invalid(self):
        for count in (None, "invalid", -1):
            with self.subTest(count=count):
                session = MagicMock()
                session.get.side_effect = [
                    response({"state": True, "count": count, "data": [
                        {"fid": "1", "fc": "1", "fn": "a"},
                        {"fid": "2", "fc": "1", "fn": "b"},
                    ]}),
                    response({"state": True, "count": count, "data": [
                        {"fid": "3", "fc": "1", "fn": "c"},
                    ]}),
                ]
                listing = self.provider(session).list_dir("/云下载")
                self.assertEqual(3, len(listing["content"]))
                self.assertEqual([0, 2], [
                    call.kwargs["params"]["offset"] for call in session.get.call_args_list
                ])

    def test_rejects_truncated_or_malformed_listing(self):
        for payload in (
            {"state": True, "count": 3, "data": [{"fid": "1", "fn": "a"}]},
            {"state": True, "count": 1, "data": []},
            {"state": True, "count": 0, "data": {}},
            {"state": True, "data": [None]},
            {"state": True},
        ):
            with self.subTest(payload=payload):
                session = MagicMock()
                session.get.return_value = response(payload)
                with self.assertRaises(Open115ReadOnlyError):
                    self.provider(session).list_dir("/云下载")

    def test_rejects_repeated_full_page(self):
        session = MagicMock()
        session.get.return_value = response({"state": True, "data": [
            {"fid": "1", "fn": "a"}, {"fid": "2", "fn": "b"},
        ]})
        with self.assertRaises(Open115ReadOnlyError):
            self.provider(session).list_dir("/云下载")
        self.assertEqual(2, session.get.call_count)

    def test_accepts_explicit_empty_listing(self):
        for data in (None, []):
            with self.subTest(data=data):
                session = MagicMock()
                session.get.return_value = response({"state": True, "count": 0, "data": data})
                self.assertEqual([], self.provider(session).list_dir("/云下载")["content"])
                self.assertEqual(1, session.get.call_count)

    def test_rejects_count_change_during_pagination(self):
        session = MagicMock()
        session.get.side_effect = [
            response({"state": True, "count": 3, "data": [
                {"fid": "1", "fn": "a"}, {"fid": "2", "fn": "b"},
            ]}),
            response({"state": True, "count": 4, "data": [
                {"fid": "3", "fn": "c"}, {"fid": "4", "fn": "d"},
            ]}),
        ]
        with self.assertRaises(Open115ReadOnlyError):
            self.provider(session).list_dir("/云下载")

    def test_rejects_partially_overlapping_pages(self):
        session = MagicMock()
        session.get.side_effect = [
            response({"state": True, "count": 4, "data": [
                {"fid": "1", "fn": "a"}, {"fid": "2", "fn": "b"},
            ]}),
            response({"state": True, "count": 4, "data": [
                {"fid": "2", "fn": "b"}, {"fid": "3", "fn": "c"},
            ]}),
        ]
        with self.assertRaisesRegex(Open115ReadOnlyError, "重复文件ID"):
            self.provider(session).list_dir("/云下载")

    def test_same_page_duplicate_ids_remain_available_for_scanner_accounting(self):
        session = MagicMock()
        session.get.return_value = response({"state": True, "count": 2, "data": [
            {"fid": "1", "fn": "a"}, {"fid": "1", "fn": "stale-a"},
        ]})
        listing = self.provider(session).list_dir("/云下载")
        self.assertEqual(["1", "1"], [item["file_id"] for item in listing["content"]])

    def test_does_not_cache_directories_from_incomplete_listing(self):
        session = MagicMock()
        session.get.return_value = response({"state": True, "count": 2, "data": [
            {"fid": "dir-1", "fc": "0", "fn": "电影"},
        ]})
        provider = self.provider(session)
        with self.assertRaises(Open115ReadOnlyError):
            provider.list_dir("/云下载")
        with self.assertRaises(Open115ReadOnlyError):
            provider.list_dir("/云下载/电影")
        self.assertEqual(1, session.get.call_count)


if __name__ == "__main__":
    unittest.main()
