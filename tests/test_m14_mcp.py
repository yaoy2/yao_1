import tempfile
import unittest
import uuid
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
