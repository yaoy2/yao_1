import tempfile
import unittest
import uuid
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path, PurePosixPath
from unittest.mock import AsyncMock, patch

try:
    import httpx
    from cryptography.fernet import Fernet
    from fastmcp import Client
    from fastmcp.server.auth import AccessToken
    from fastmcp.server.auth.providers.github import GitHubProvider
except ImportError:
    raise unittest.SkipTest("M14 MCP tests require integrations/m14/requirements.txt")

from scripts.m14_mcp import build_auth, create_server
from tests.test_todo_chat import FakeGitHub, service


class M14McpTest(unittest.IsolatedAsyncioTestCase):
    def test_container_payload_can_import_and_save_a_todo(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "integrations/m14/Dockerfile").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory)
            for line in dockerfile.replace("\\\n", " ").splitlines():
                parts = shlex.split(line)
                if not parts or parts[0] != "COPY":
                    continue
                destination = staged / PurePosixPath(parts[-1]).relative_to("/app")
                for source in parts[1:-1]:
                    target = destination / Path(source).name if parts[-1].endswith("/") else destination
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(root / source, target)
            check = textwrap.dedent('''
                import base64, hashlib, sys, uuid
                from types import SimpleNamespace
                sys.path.insert(0, sys.argv[1])
                from scripts.m14_mcp import create_server, TodoChatService
                from utils import todo_db
                class FakeGitHub:
                    def __init__(self):
                        self.content = todo_db.build_markdown_backup([])
                    @property
                    def sha(self):
                        return hashlib.sha256(self.content.encode()).hexdigest()
                    def get(self, *args, **kwargs):
                        payload = {"sha": self.sha, "content": base64.b64encode(self.content.encode()).decode()}
                        return SimpleNamespace(status_code=200, json=lambda: payload)
                    def put(self, *args, json, **kwargs):
                        assert json["sha"] == self.sha
                        self.content = base64.b64decode(json["content"]).decode()
                        return SimpleNamespace(status_code=200, json=lambda: {"content": {"sha": self.sha}})
                service = TodoChatService(environ={"GITHUB_BACKUP_TOKEN": "fixture-only"}, session=FakeGitHub())
                create_server(service)
                assert service.add("Package smoke test", str(uuid.uuid4()))["created"] == 1
                assert service.list()["total"] == 1
            ''')
            result = subprocess.run([sys.executable, "-I", "-B", "-c", check, str(staged)], cwd=staged,
                                    capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)

    async def test_mcp_tools_use_existing_m14_logic(self):
        remote = FakeGitHub()
        async with Client(create_server(service(remote))) as client:
            tools = await client.list_tools()
            self.assertEqual({"m14_list_todos", "m14_add_todos", "m14_update_todo"}, {t.name for t in tools})
            added = await client.call_tool("m14_add_todos", {
                "content": "提醒我明天下午3点交材料", "request_id": str(uuid.uuid4())})
            self.assertFalse(added.is_error)
            listed = await client.call_tool("m14_list_todos", {})
            item = listed.data["items"][0]
            await client.call_tool("m14_update_todo", {
                "uid": item["uid"], "expected_revision": item["revision"], "done": True})
            self.assertEqual([], (await client.call_tool("m14_list_todos", {})).data["items"])
            self.assertEqual(2, remote.writes)

    async def test_http_requires_auth_and_exposes_oauth_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = build_auth(self.config(directory))
            app = create_server(service(FakeGitHub()), auth=auth).http_app()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://m14.example.com") as client:
                response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
                self.assertEqual(401, response.status_code)
                self.assertIn("resource_metadata", response.headers.get("www-authenticate", ""))
                metadata = await client.get("/.well-known/oauth-authorization-server")
                self.assertEqual(200, metadata.status_code)
                self.assertIn("S256", metadata.json()["code_challenge_methods_supported"])

    async def test_other_github_accounts_are_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = build_auth(self.config(directory))
            for subject, allowed in (("123", True), ("999", False), ("", False)):
                token = AccessToken(token="test-token", client_id="test", scopes=["read:user"], claims={"sub": subject})
                with patch.object(GitHubProvider, "verify_token", new=AsyncMock(return_value=token)):
                    self.assertEqual(allowed, await auth.verify_token("not-a-real-token") is not None)

    def test_missing_http_config_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "缺少配置"):
            build_auth({})

    @staticmethod
    def config(directory):
        return {"M14_PUBLIC_URL": "https://m14.example.com", "M14_GITHUB_CLIENT_ID": "test-client",
                "M14_GITHUB_CLIENT_SECRET": "test-secret", "M14_GITHUB_USER_ID": "123",
                "M14_JWT_SIGNING_KEY": "test-signing-key-with-more-than-32-characters",
                "M14_STORAGE_KEY": Fernet.generate_key().decode(), "M14_AUTH_STATE_DIR": directory}


if __name__ == "__main__":
    unittest.main()
