import unittest

from integrations.cyber_qq.gpt_qq.prepare import initial_config, isolate_napcat


class PrepareTests(unittest.TestCase):
    def test_private_owner_only_and_no_old_persona(self):
        cfg = initial_config("12345678", "test-api-key", "test-password", "test-bridge")
        access = cfg["platform_settings"]
        self.assertEqual(access["id_whitelist"], ["gpt-qq:FriendMessage:12345678"])
        self.assertFalse(access["wl_ignore_admin_on_group"])
        self.assertFalse(access["wl_ignore_admin_on_friend"])
        self.assertEqual(cfg["agent_runner"]["config"]["persona"]["persona_id"], "gpt-qq")
        self.assertEqual(cfg["provider_settings"]["computer_use_runtime"], "none")

    def test_openai_parameters_and_isolated_ports(self):
        cfg = initial_config("12345678", "test-api-key", "test-password", "test-bridge")
        self.assertEqual(cfg["provider_sources"][0]["api_base"], "https://api.openai.com/v1")
        self.assertEqual(cfg["provider"][0]["model"], "gpt-6.1-sol")
        extra = cfg["provider"][0]["custom_extra_body"]
        self.assertNotIn("thinking", extra)
        self.assertNotIn("max_tokens", extra)
        self.assertFalse(extra["store"])
        self.assertEqual(cfg["platform"][0]["ws_reverse_port"], 6199)
        self.assertEqual(cfg["dashboard"]["host"], "127.0.0.1")

    def test_invalid_owner_fails_closed(self):
        for owner in ("", "*", "123", "abc"):
            with self.assertRaises(ValueError):
                initial_config(owner, "test-key", "test-password", "test-bridge")

    def test_both_qq_data_locations_are_isolated(self):
        old = ("let e = this.context.wrapper.NodeQQNTWrapperUtil.getNTUserDataInfoConfig();\n"
               "let e = t.NodeQQNTWrapperUtil.getNTUserDataInfoConfig();")
        result = isolate_napcat(old)
        self.assertEqual(result.count("process.env.NAPCAT_QQ_DATA_DIR"), 2)
        self.assertNotIn("getNTUserDataInfoConfig", result)
        with self.assertRaises(ValueError):
            isolate_napcat(old + "\n" + old)
        with self.assertRaises(ValueError):
            isolate_napcat(result)


if __name__ == "__main__":
    unittest.main()
