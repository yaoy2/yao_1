import base64
import importlib.util
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from utils import github_backup_sync as sync
from utils.data_sync_validation import equivalent_backup, validate_backup
from tests.test_github_backup_sync import FakeDownloadSession, FakeResponse, FakeSession

SECRETS = {"github_backup_token": "test"}


class SyncSafetyTest(unittest.TestCase):
    def test_upload_requires_baseline_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "a.md"
            local.write_text("local", encoding="utf-8")
            session = FakeSession()
            with self.assertRaisesRegex(RuntimeError, "同步基线"):
                sync.sync_file_to_github(local, "data/a.md", "m", SECRETS, {}, session)
            self.assertFalse(session.get_calls or session.put_calls)

    def test_stale_baseline_never_uses_latest_remote_sha_to_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "a.md"
            local.write_text("edit", encoding="utf-8")
            sync.remember_local_sync_baseline(local, "data/a.md", "base", "earlier-sha", SECRETS, {})
            session = FakeSession()
            with self.assertRaisesRegex(RuntimeError, "远端数据已更新"):
                sync.sync_file_to_github(local, "data/a.md", "m", SECRETS, {}, session)
            self.assertFalse(session.put_calls)
            self.assertEqual("edit", local.read_text(encoding="utf-8"))

    def test_unknown_local_and_edited_local_survive_pull(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "a.md"
            local.write_text("private edit", encoding="utf-8")
            for baseline in (False, True):
                if baseline:
                    sync.remember_local_sync_baseline(local, "data/a.md", "old", "old-sha", SECRETS, {})
                with self.assertRaisesRegex(RuntimeError, "本机文件"):
                    sync.download_file_from_github(local, "data/a.md", SECRETS, {}, FakeDownloadSession(content="new"))
                self.assertEqual("private edit", local.read_text(encoding="utf-8"))

    def test_readonly_local_can_refresh_and_baseline_is_source_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "a.md"
            local.write_text("old", encoding="utf-8")
            sync.remember_local_sync_baseline(local, "data/a.md", "old", "old-sha", SECRETS, {})
            sync.download_file_from_github(local, "data/a.md", SECRETS, {}, FakeDownloadSession(content="new"))
            self.assertEqual("new", sync.get_local_sync_baseline(local, "data/a.md", SECRETS, {})["content"])
            self.assertIsNone(sync.get_local_sync_baseline(local, "data/b.md", SECRETS, {}))
            self.assertIsNone(sync.get_local_sync_baseline(local, "data/a.md", {**SECRETS, "github_backup_branch": "other"}, {}))

    def test_missing_sha_and_invalid_base64_stop_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "a.md"
            for payload in ({"content": "eA=="}, {"sha": "s", "content": "invalid%%"}):
                session = FakeSession()
                session.get = lambda *args, **kwargs: FakeResponse(200, payload)
                with self.assertRaises(Exception):
                    sync.download_file_from_github(local, "data/a.md", SECRETS, {}, session)
                self.assertFalse(local.exists())

    def test_path_traversal_and_absolute_paths_never_reach_network(self):
        session = FakeSession()
        for path in ("../secrets.toml", "data/../secret", "data//secret", "E:/data/x", "data/x/../../y"):
            with self.assertRaises(ValueError):
                sync.read_file_from_github(path, SECRETS, {}, session)
        self.assertFalse(session.get_calls)

    def test_baseline_integrity_failure_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "a.md"
            sync.remember_local_sync_baseline(local, "data/a.md", "old", "s", SECRETS, {})
            statefile = next((local.parent / ".sync-state").glob("*.json"))
            state = json.loads(statefile.read_text(encoding="utf-8"))
            state["content"] = "changed"
            statefile.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "基线损坏"):
                sync.get_local_sync_baseline(local, "data/a.md", SECRETS, {})

    def test_conflict_after_read_does_not_advance_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "a.md"
            local.write_text("edit", encoding="utf-8")
            sync.remember_local_sync_baseline(local, "data/a.md", "base", "old-sha", SECRETS, {})
            session = FakeSession()
            session.put = lambda *args, **kwargs: FakeResponse(409)
            with self.assertRaisesRegex(RuntimeError, "409"):
                sync.sync_file_to_github(local, "data/a.md", "m", SECRETS, {}, session)
            self.assertEqual("base", sync.get_local_sync_baseline(local, "data/a.md", SECRETS, {})["content"])

    def test_json_corruption_and_nonfinite_are_rejected(self):
        for content in ("", "{", "[NaN]", '"text"'):
            with self.assertRaises(ValueError):
                validate_backup("data/llm_budget_records.json", content)
        self.assertTrue(equivalent_backup("data/llm_budget_records.json", "[]", "[ ]"))

    def test_startup_pull_does_not_move_baseline_ahead_of_existing_database(self):
        from utils import budget_db
        import sqlite3
        spec = importlib.util.spec_from_file_location("safe_sync_db_cli", Path(__file__).resolve().parents[1] / "scripts/data_repo_sync.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        path = "data/budget_ledger_backup.md"
        with tempfile.TemporaryDirectory() as directory, patch.object(cli, "ROOT", Path(directory)):
            local = Path(directory) / path
            local.parent.mkdir()
            old = budget_db.build_markdown_backup([])
            local.write_text(old, encoding="utf-8")
            with closing(sqlite3.connect(local.parent / "budget.db")) as db:
                db.execute("CREATE TABLE expense_records (id INTEGER PRIMARY KEY)")
                db.commit()
            sync.remember_local_sync_baseline(local, path, old, "old-sha", SECRETS, {})
            remote = {"ok": True, "sha": "new-sha", "content": old}
            with patch.object(sync, "read_file_from_github", return_value=remote), patch.object(cli, "local_secrets", return_value=SECRETS):
                self.assertEqual(0, cli.main(["pull", path]))
            self.assertEqual("old-sha", sync.get_local_sync_baseline(local, path, SECRETS, {})["sha"])
            self.assertEqual(old, local.read_text(encoding="utf-8"))

    def test_success_without_new_version_is_not_reported_as_confirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "a.md"
            local.write_text("x", encoding="utf-8")
            session = FakeSession()
            session.put = lambda *args, **kwargs: FakeResponse(200, {"content": {}})
            with self.assertRaisesRegex(RuntimeError, "版本尚未确认"):
                sync.sync_file_to_github(local, "data/a.md", "m", SECRETS, {}, session, expected_sha="old-sha")
            self.assertIsNone(sync.get_local_sync_baseline(local, "data/a.md", SECRETS, {}))

    def test_bulk_pull_preflights_all_files_before_mutating(self):
        spec = importlib.util.spec_from_file_location("safe_sync_cli", Path(__file__).resolve().parents[1] / "scripts/data_repo_sync.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        paths = ["data/llm_budget_records.json", "data/llm_budget_accounts.json"]
        with tempfile.TemporaryDirectory() as directory, patch.object(cli, "ROOT", Path(directory)):
            data = Path(directory) / "data"
            data.mkdir()
            (data / "llm_budget_accounts.json").write_text('{"local": 1}', encoding="utf-8")
            def remote(path, *args, **kwargs):
                return {"ok": True, "sha": "s", "content": "[]" if "records" in path else "{}"}
            with patch.object(sync, "read_file_from_github", remote), patch.object(cli, "local_secrets", return_value=SECRETS):
                self.assertEqual(1, cli.main(["pull", *paths]))
            self.assertFalse((data / "llm_budget_records.json").exists())
            self.assertEqual('{"local": 1}', (data / "llm_budget_accounts.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
