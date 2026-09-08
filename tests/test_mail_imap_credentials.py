import ctypes
import imaplib
import json
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import mail_imap_setup as setup
from utils import mail_imap_credentials as credentials


TARGET = credentials.TARGET_PREFIX + "mail.example.edu/staff@example.edu"
ACCOUNT = "staff@example.edu"
SECRET = "fake-only-测试🔐-do-not-log"


class FakeCredentialAPI:
    def __init__(self):
        self.saved = None
        self.freed = False
        self.fail_read = False
        self.fail_write = False

    def CredWriteW(self, pointer, flags):
        if self.fail_write:
            return False
        value = ctypes.cast(pointer, ctypes.POINTER(credentials.CREDENTIALW)).contents
        self.saved = {"target": value.TargetName, "username": value.UserName,
                      "blob": ctypes.string_at(value.CredentialBlob, value.CredentialBlobSize),
                      "size": value.CredentialBlobSize, "persist": value.Persist,
                      "type": value.Type, "flags": flags}
        return True

    def CredReadW(self, target, kind, flags, out_pointer):
        if self.fail_read:
            return False
        self.blob = (ctypes.c_ubyte * len(self.saved["blob"])).from_buffer_copy(self.saved["blob"])
        self.result = credentials.CREDENTIALW()
        self.result.Type = kind
        self.result.UserName = self.saved["username"]
        self.result.CredentialBlobSize = self.saved["size"]
        self.result.CredentialBlob = ctypes.cast(self.blob, ctypes.POINTER(ctypes.c_ubyte))
        ctypes.cast(out_pointer, ctypes.POINTER(ctypes.POINTER(credentials.CREDENTIALW)))[0] = ctypes.pointer(self.result)
        return True

    def CredFree(self, pointer):
        self.freed = True


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeCredentialAPI()
        self.patcher = patch.object(credentials, "_advapi", return_value=self.api)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_unicode_roundtrip_and_native_sizes_with_mock_only(self):
        credentials.save_credential(TARGET, ACCOUNT, SECRET)
        self.assertEqual(self.api.saved["blob"], SECRET.encode("utf-16-le"))
        self.assertEqual(self.api.saved["size"], len(SECRET.encode("utf-16-le")))
        self.assertEqual(self.api.saved["persist"], credentials.CRED_PERSIST_LOCAL_MACHINE)
        self.assertEqual(self.api.saved["type"], credentials.CRED_TYPE_GENERIC)
        self.assertEqual(credentials.read_credential(TARGET), (ACCOUNT, SECRET))
        self.assertTrue(self.api.freed)

    def test_missing_target_has_fixed_friendly_error(self):
        self.api.fail_read = True
        with patch.object(ctypes, "get_last_error", return_value=1168, create=True):
            with self.assertRaisesRegex(credentials.CredentialNotFound, "^imap_credential_not_saved$"):
                credentials.read_credential(TARGET)
        self.assertFalse(self.api.freed)

    def test_write_failure_does_not_report_supplied_secret(self):
        self.api.fail_write = True
        with self.assertRaises(credentials.CredentialError) as raised:
            credentials.save_credential(TARGET, ACCOUNT, SECRET)
        self.assertEqual(str(raised.exception), "credential_save_failed")
        self.assertNotIn(SECRET, str(raised.exception))

    def test_read_failure_has_fixed_error(self):
        self.api.fail_read = True
        with patch.object(ctypes, "get_last_error", return_value=5, create=True):
            with self.assertRaisesRegex(credentials.CredentialError, "^credential_read_failed$"):
                credentials.read_credential(TARGET)

    def test_other_credential_targets_are_rejected(self):
        with self.assertRaisesRegex(credentials.CredentialError, "^invalid_credential_target$"):
            credentials.read_credential("AnotherApp/credential")

    def test_invalid_native_blob_is_freed(self):
        credentials.save_credential(TARGET, ACCOUNT, SECRET)
        self.api.saved["size"] = 3
        with self.assertRaisesRegex(credentials.CredentialError, "^invalid_stored_credential$"):
            credentials.read_credential(TARGET)
        self.assertTrue(self.api.freed)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"account": ACCOUNT, "imap": {"host": "mail.example.edu", "port": 993,
                       "ssl": True, "credential_target": TARGET}}

    def load_config(self):
        (self.root / "config.json").write_text(json.dumps(self.config), encoding="utf-8")
        return setup.load_setup_config(self.root)

    def test_load_safe_config(self):
        config = self.load_config()
        self.assertEqual(config["credential_target"], TARGET)
        self.assertEqual(config["root"], self.root.resolve())

    def test_rejects_unsafe_protocol_or_unrelated_target(self):
        for name, value in [("port", 143), ("port", "993"), ("ssl", False),
                            ("verify_tls", False), ("host", "https://mail.example.edu"),
                            ("host", "127.0.0.1"), ("host", "-mail.example.edu"),
                            ("credential_target", credentials.TARGET_PREFIX + "another/account")]:
            with self.subTest(name=name, value=value):
                saved = self.config["imap"].copy()
                self.config["imap"][name] = value
                with self.assertRaisesRegex(setup.SetupError, "^invalid_config$"):
                    self.load_config()
                self.config["imap"] = saved

    def test_readonly_check_never_fetches_or_mutates_messages(self):
        config = self.load_config()
        client = Mock()
        client.login.return_value = ("OK", [b"secret-server-marker"])
        client.select.return_value = ("OK", [b"42"])
        factory = Mock(return_value=client)
        self.assertEqual(setup.verify_connection(config, SECRET, factory), {"folder_count": 1})
        client.select.assert_called_once_with("INBOX", readonly=True)
        client.login.assert_called_once_with(ACCOUNT, SECRET)
        for name in ["fetch", "store", "append", "expunge", "close", "delete", "logout"]:
            getattr(client, name).assert_not_called()
        client.shutdown.assert_called_once()
        tls = factory.call_args.kwargs["ssl_context"]
        self.assertTrue(tls.check_hostname)
        self.assertEqual(tls.verify_mode, ssl.CERT_REQUIRED)
        self.assertLessEqual(factory.call_args.kwargs["timeout"], 20)

    def test_server_auth_error_cannot_leak(self):
        config = self.load_config()
        client = Mock()
        client.login.side_effect = imaplib.IMAP4.error(SECRET)
        with self.assertRaises(setup.SetupError) as raised:
            setup.verify_connection(config, SECRET, Mock(return_value=client))
        self.assertEqual(str(raised.exception), "authentication_failed")
        client.shutdown.assert_called_once()

    def test_certificate_errors_have_fixed_classification(self):
        with self.assertRaisesRegex(setup.SetupError, "^tls_failed$"):
            setup.verify_connection(self.load_config(), SECRET,
                                    Mock(side_effect=ssl.SSLCertVerificationError(SECRET)))

    def test_success_state_has_only_whitelisted_metadata(self):
        config = self.load_config()
        setup.save_success(config, 1, False)
        result = json.loads((self.root / "state" / "imap_setup.json").read_text(encoding="utf-8"))
        self.assertEqual(set(result), {"status", "account", "host", "port", "saved_credential",
                                      "folder_count", "checked_at"})
        self.assertFalse(result["saved_credential"])
        self.assertNotIn(SECRET, json.dumps(result))


if __name__ == "__main__":
    unittest.main()
