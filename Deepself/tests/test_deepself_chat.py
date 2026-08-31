import unittest

import requests

from Deepself.deepself_chat import (
    PROVIDERS,
    ChatAPIError,
    build_request_payload,
    build_system_prompt,
    call_chat_completion,
    get_api_key,
    trim_history,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"choices": [{"message": {"content": "收到，我来处理。"}}]}

    def json(self):
        return self._payload


class DeepselfChatTests(unittest.TestCase):
    def test_get_api_key_supports_sections_and_environment(self):
        self.assertEqual(
            "secret-a",
            get_api_key("deepseek", secrets={"deepseek": {"api_key": "secret-a"}}, environ={}),
        )
        self.assertEqual(
            "secret-b",
            get_api_key("kimi", secrets={}, environ={"MOONSHOT_API_KEY": "secret-b"}),
        )
        self.assertEqual(
            "secret-c",
            get_api_key("glm", secrets={"ZHIPU_API_KEY": "secret-c"}, environ={}),
        )

    def test_build_payload_omits_sampling_parameters(self):
        payload = build_request_payload(
            model="model-x",
            messages=[{"role": "user", "content": "对方说今天来不了"}],
            system_prompt="reply naturally",
        )
        self.assertNotIn("temperature", payload)
        self.assertNotIn("top_p", payload)
        self.assertEqual("system", payload["messages"][0]["role"])
        self.assertEqual("user", payload["messages"][-1]["role"])

    def test_trim_history_drops_metadata_and_old_messages(self):
        messages = [
            {"role": "user", "content": f"u{i}", "provider": "private"}
            if i % 2 == 0
            else {"role": "assistant", "content": f"a{i}", "model": "private"}
            for i in range(20)
        ]
        trimmed = trim_history(messages, max_messages=4)
        self.assertEqual(4, len(trimmed))
        self.assertEqual({"role", "content"}, set(trimmed[0]))

    def test_system_prompt_requests_direct_reply_without_impersonation(self):
        prompt = build_system_prompt("风格", "回复规则", tone="锋利")
        self.assertIn("只输出回复正文", prompt)
        self.assertIn("不是 Sir 本人", prompt)
        self.assertIn("锋利", prompt)

    def test_each_provider_uses_expected_endpoint_and_never_sends_temperature(self):
        for provider_key, spec in PROVIDERS.items():
            captured = {}

            def fake_post(url, **kwargs):
                captured["url"] = url
                captured.update(kwargs)
                return FakeResponse()

            reply = call_chat_completion(
                provider_key,
                api_key="test-key",
                model=spec.default_model,
                messages=[{"role": "user", "content": "测试"}],
                system_prompt="system",
                post=fake_post,
            )
            self.assertEqual("收到，我来处理。", reply)
            self.assertEqual(spec.api_url, captured["url"])
            self.assertNotIn("temperature", captured["json"])
            self.assertEqual("Bearer test-key", captured["headers"]["Authorization"])

    def test_http_errors_are_user_safe(self):
        def fake_post(*_args, **_kwargs):
            return FakeResponse(status_code=401, payload={"error": {"message": "echoed private prompt"}})

        with self.assertRaises(ChatAPIError) as caught:
            call_chat_completion(
                "deepseek",
                api_key="test-key",
                model="model-x",
                messages=[{"role": "user", "content": "private prompt"}],
                system_prompt="system",
                post=fake_post,
            )
        self.assertNotIn("private prompt", str(caught.exception))
        self.assertNotIn("test-key", str(caught.exception))
        self.assertIn("鉴权失败", str(caught.exception))

    def test_timeout_is_translated(self):
        def fake_post(*_args, **_kwargs):
            raise requests.Timeout()

        with self.assertRaisesRegex(ChatAPIError, "响应超时"):
            call_chat_completion(
                "kimi",
                api_key="test-key",
                model="model-x",
                messages=[{"role": "user", "content": "测试"}],
                system_prompt="system",
                post=fake_post,
            )


if __name__ == "__main__":
    unittest.main()
