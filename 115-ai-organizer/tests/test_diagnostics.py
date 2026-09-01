import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock

from app.diagnostics import ListingDiagnosticError, diagnose_open115_listing


class ListingDiagnosticsTest(unittest.TestCase):
    def make_openlist_data(self, addition: dict) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(temp_dir.name)
        with closing(sqlite3.connect(data_dir / "data.db")) as conn:
            conn.execute(
                "CREATE TABLE x_storages (mount_path TEXT, driver TEXT, addition TEXT)"
            )
            conn.execute(
                "INSERT INTO x_storages VALUES (?, ?, ?)",
                ("/云下载", "115 Open", json.dumps(addition)),
            )
            conn.commit()
        return temp_dir, data_dir

    @staticmethod
    def response(payload: dict) -> MagicMock:
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        return response

    def test_empty_listing_with_private_sample_is_diagnosed(self):
        temp_dir, data_dir = self.make_openlist_data(
            {"access_token": "test-secret-token", "root_folder_id": "123"}
        )
        self.addCleanup(temp_dir.cleanup)
        session = MagicMock()
        session.get.side_effect = [
            self.response({"state": True, "data": []}),
            self.response(
                {
                    "state": True,
                    "count": 2,
                    "data": [
                        {"is_private": 1, "file_name": "do-not-print-a"},
                        {"is_private": 1, "file_name": "do-not-print-b"},
                    ],
                }
            ),
        ]

        report = diagnose_open115_listing(
            data_dir,
            "/云下载",
            session=session,
            sleep_fn=lambda _: None,
        )

        self.assertEqual("hidden_items_excluded_from_listing", report["diagnosis"])
        self.assertEqual(2, report["hidden_folder_sample"]["private_count"])
        rendered = json.dumps(report)
        self.assertNotIn("test-secret-token", rendered)
        self.assertNotIn("do-not-print", rendered)

    def test_available_listing_skips_hidden_search(self):
        temp_dir, data_dir = self.make_openlist_data(
            {"access_token": "test-token", "root_folder_id": "123"}
        )
        self.addCleanup(temp_dir.cleanup)
        session = MagicMock()
        session.get.return_value = self.response(
            {"state": True, "count": 1, "data": [{"fid": "9"}]}
        )

        report = diagnose_open115_listing(
            data_dir,
            "/云下载",
            session=session,
            sleep_fn=lambda _: None,
        )

        self.assertEqual("listing_available", report["diagnosis"])
        self.assertIsNone(report["hidden_folder_sample"])
        self.assertEqual(1, session.get.call_count)

    def test_missing_token_error_does_not_echo_storage_json(self):
        temp_dir, data_dir = self.make_openlist_data(
            {"root_folder_id": "123", "private_note": "must-not-leak"}
        )
        self.addCleanup(temp_dir.cleanup)

        with self.assertRaises(ListingDiagnosticError) as raised:
            diagnose_open115_listing(data_dir, "/云下载", sleep_fn=lambda _: None)

        self.assertNotIn("must-not-leak", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
