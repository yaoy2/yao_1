import unittest
from prepare import apply_keys, initial_config, schema_defaults


class InitialSettingsTests(unittest.TestCase):
    def test_only_local_ports_and_no_account_enabled(self):
        cfg = initial_config('ExampleOnly1', 'ExampleOnly2')
        self.assertEqual(cfg['dashboard']['host'], '127.0.0.1')
        self.assertEqual(cfg['platform'][0]['ws_reverse_host'], '127.0.0.1')
        self.assertFalse(cfg['platform'][0]['enable'])
        self.assertFalse(cfg['provider'][0]['enable'])
        self.assertEqual(cfg['platform_settings']['id_whitelist'], ['whale-setup-pending:FriendMessage:no-user'])
        self.assertEqual(cfg['provider_settings']['computer_use_runtime'], 'none')

    def test_unique_salted_password_and_tokens(self):
        a = initial_config('ExampleOnly1', 'bridge-a')['dashboard']
        b = initial_config('ExampleOnly1', 'bridge-b')['dashboard']
        self.assertNotEqual(a['pbkdf2_password'], b['pbkdf2_password'])
        self.assertNotEqual(a['jwt_secret'], b['jwt_secret'])

    def test_preset_updates_grouped_and_legacy_settings(self):
        cfg = {'enabled': True, 'group': {'enabled': True, 'other': 7}}
        apply_keys(cfg, {'enabled': False})
        self.assertEqual(cfg, {'enabled': False, 'group': {'enabled': False, 'other': 7}})

    def test_unknown_preset_rejected(self):
        with self.assertRaises(ValueError):
            apply_keys({'enabled': False}, {'typo': True})

    def test_nested_schema_defaults(self):
        schema = {'group': {'type': 'object', 'items': {'enabled': {'default': False}}}}
        self.assertEqual(schema_defaults(schema), {'group': {'enabled': False}})


if __name__ == '__main__':
    unittest.main()
