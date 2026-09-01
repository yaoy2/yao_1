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


if __name__ == "__main__":
    unittest.main()
