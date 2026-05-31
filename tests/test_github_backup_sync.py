import base64
import tempfile
import unittest
from pathlib import Path

from utils import github_backup_sync


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.get_calls = []
        self.put_calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.get_calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return FakeResponse(200, {"sha": "old-sha"})

    def put(self, url, headers=None, json=None, timeout=None):
        self.put_calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse(200, {"content": {"path": "data/budget_ledger_backup.md"}})


class FakeDownloadSession:
    def __init__(self, status_code=200, content="backup text"):
        self.status_code = status_code
        self.content = content
        self.get_calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.get_calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if self.status_code == 200:
            payload = {"content": base64.b64encode(self.content.encode("utf-8")).decode("ascii")}
        else:
            payload = {}
        return FakeResponse(self.status_code, payload)


class GithubBackupSyncTest(unittest.TestCase):
    def test_missing_token_skips_without_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "backup.md"
            local_path.write_text("backup", encoding="utf-8")

            result = github_backup_sync.sync_file_to_github(
                local_path,
                "data/budget_ledger_backup.md",
                "data: sync backup",
                secrets={},
                environ={},
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual("missing_token", result["reason"])

    def test_sync_file_updates_github_contents_api(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "backup.md"
            local_path.write_text("预算备份", encoding="utf-8")
            session = FakeSession()

            result = github_backup_sync.sync_file_to_github(
                local_path,
                "data/budget_ledger_backup.md",
                "data: sync backup",
                secrets={"github_backup_token": "token-1"},
                environ={},
                session=session,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(1, len(session.get_calls))
        self.assertEqual(1, len(session.put_calls))
        payload = session.put_calls[0]["json"]
        self.assertEqual("data: sync backup", payload["message"])
        self.assertEqual("main", payload["branch"])
        self.assertEqual("old-sha", payload["sha"])
        self.assertEqual("预算备份", base64.b64decode(payload["content"]).decode("utf-8"))

    def test_download_file_skips_when_token_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "backup.md"

            result = github_backup_sync.download_file_from_github(
                local_path,
                "data/web_memos_backup.md",
                secrets={},
                environ={},
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual("missing_token", result["reason"])

    def test_download_file_writes_github_content_to_local_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "backup.md"
            session = FakeDownloadSession(content="# 灵感便签盒备份\n\ncontent")

            result = github_backup_sync.download_file_from_github(
                local_path,
                "data/web_memos_backup.md",
                secrets={"github_backup_token": "token-1"},
                environ={},
                session=session,
            )

            restored_text = local_path.read_text(encoding="utf-8")

        self.assertTrue(result["ok"])
        self.assertEqual("# 灵感便签盒备份\n\ncontent", restored_text)
        self.assertEqual(1, len(session.get_calls))
        self.assertEqual({"ref": "main"}, session.get_calls[0]["params"])


if __name__ == "__main__":
    unittest.main()
