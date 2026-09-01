import io
import json
import unittest
from unittest.mock import MagicMock, patch

from app.cli import cmd_probe
from app.config import Settings
from app.openlist_client import OpenListError


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


class ProbeCommandTest(unittest.TestCase):
    @patch("app.cli.OpenListClient")
    def test_empty_cached_listing_is_not_reported_as_success(self, client_type):
        client = MagicMock()
        client.list_dir.side_effect = [
            {"content": []},
            OpenListError("Refresh without permission"),
        ]
        client_type.return_value = client
        output = io.StringIO()

        with patch("sys.stdout", output), patch("sys.stderr", io.StringIO()):
            exit_code = cmd_probe(settings(), "/云下载")

        report = json.loads(output.getvalue())
        self.assertEqual(3, exit_code)
        self.assertEqual("empty_listing_refresh_denied", report["diagnosis"])
        self.assertEqual(2, client.list_dir.call_count)


if __name__ == "__main__":
    unittest.main()
