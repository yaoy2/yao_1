"""Windows junction regressions using only independently created test folders."""

import base64
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tests.test_mail_filing_worker import source
from tests.test_mail_workbench_sync import fixture
from utils.mail_filing import export_message


@unittest.skipUnless(os.name == "nt", "Windows directory-handle and junction regression")
class FilingWindowsPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mail-filing-path-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.destination = self.base / "destination"
        self.outside = self.base / "outside-destination"
        self.destination.mkdir()
        self.outside.mkdir()
        self.message = fixture()["messages"][0]
        self.value = source(self.message)

    def export(self):
        return export_message(self.destination, self.destination, self.message,
                              source_reader=Mock(return_value=self.value))

    def assert_test_path(self, path):
        self.assertTrue(Path(path).resolve().is_relative_to(self.base))

    def make_junction(self, path, target):
        self.assert_test_path(path)
        self.assert_test_path(target)
        quote = lambda value: str(value).replace("'", "''")
        command = ("New-Item -ItemType Junction -Path '" + quote(path)
                   + "' -Value '" + quote(target) + "' -ErrorAction Stop | Out-Null")
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=20,
        )
        self.assertEqual(0, completed.returncode, "Could not create the isolated test junction")

    def attack_directory(self, parent, record):
        """The previous implementation allowed this rename-and-junction swap."""
        retained = parent.with_name(parent.name + "-retained")
        self.assert_test_path(parent)
        self.assert_test_path(retained)
        record["attempted"] = True
        try:
            parent.rename(retained)
        except OSError as exc:
            record["blocked"] = True
            record["winerror"] = getattr(exc, "winerror", None)
            return
        self.make_junction(parent, self.outside)
        record["replaced"] = True

    def assert_no_leaked_handles(self):
        # TemporaryDirectory would also clean up at teardown. Doing it here
        # explicitly checks that every ancestor/output directory handle closed.
        self.temporary.cleanup()
        self.assertFalse(self.base.exists())

    def test_directory_replacement_before_temporary_open_is_blocked(self):
        real_open = Path.open
        record = {"attempted": False, "blocked": False, "replaced": False}

        def raced_open(path, *args, **kwargs):
            if (not record["attempted"] and path.name.startswith(".filing-")
                    and args and args[0] == "xb"):
                self.attack_directory(path.parent, record)
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "open", raced_open):
            result = self.export()
        self.assertTrue(record["attempted"], "The regression must exercise the former race window")
        self.assertTrue(record["blocked"], "Pinned Windows handles should block renaming the output directory")
        self.assertFalse(record["replaced"])
        self.assertIn(record["winerror"], {5, 32, 33})
        self.assertEqual([], list(self.outside.iterdir()))
        self.assertEqual(("success", 1), (result["status"], result["saved_count"]))
        file_path = self.destination / result["files"][0]["path"]
        self.assertEqual(b"real-attachment", file_path.read_bytes())
        self.assertEqual(self.destination, file_path.parent)
        self.assertEqual(".", result["destination"])
        self.assertTrue(file_path.resolve().is_relative_to(self.destination))
        self.assert_no_leaked_handles()

    def test_directory_remains_pinned_until_final_rename(self):
        real_rename = os.rename
        record = {"attempted": False, "blocked": False, "replaced": False}

        def raced_rename(old, new, *args, **kwargs):
            old = Path(old)
            if not record["attempted"] and old.name.startswith(".filing-"):
                self.attack_directory(old.parent, record)
            return real_rename(old, new, *args, **kwargs)

        with patch.object(os, "rename", raced_rename):
            result = self.export()
        self.assertTrue(record["attempted"])
        self.assertTrue(record["blocked"])
        self.assertFalse(record["replaced"])
        self.assertEqual([], list(self.outside.iterdir()))
        self.assertEqual("success", result["status"])
        self.assertEqual([], list(self.destination.rglob("*.partial")))
        self.assert_no_leaked_handles()

    def test_preexisting_output_junction_is_rejected(self):
        directory = self.destination / "材料.xlsx"
        self.make_junction(directory, self.outside)
        result = self.export()
        self.assertEqual(("error", 0), (result["status"], result["saved_count"]))
        self.assertIn("DESTINATION_UNSAFE", result["error_codes"])
        self.assertEqual([], list(self.outside.iterdir()))
        self.assert_no_leaked_handles()

    def test_preexisting_destination_root_junction_is_rejected(self):
        linked_root = self.base / "linked-root"
        self.make_junction(linked_root, self.destination)
        result = export_message(self.destination, linked_root, self.message,
                                source_reader=Mock(return_value=self.value))
        self.assertEqual(("error", 0), (result["status"], result["saved_count"]))
        self.assertIn("DESTINATION_UNSAFE", result["error_codes"])
        self.assertEqual([], list(self.destination.iterdir()))
        self.assert_no_leaked_handles()

    def test_copy_failure_releases_all_pinned_handles(self):
        real_open = Path.open

        def failed_open(path, *args, **kwargs):
            if path.name.startswith(".filing-") and args and args[0] == "xb":
                raise OSError("simulated test-only disk failure")
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "open", failed_open):
            result = self.export()
        self.assertEqual(("error", 0), (result["status"], result["saved_count"]))
        self.assertIn("FILE_COPY_FAILED", result["error_codes"])
        self.assertEqual([], list(self.outside.iterdir()))
        self.assert_no_leaked_handles()


if __name__ == "__main__":
    unittest.main()
