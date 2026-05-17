from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WechatArchiverScriptsTest(unittest.TestCase):
    def test_start_scripts_use_dedicated_port_8502(self):
        script = (ROOT / "启动微信归档窗口.bat").read_text(encoding="utf-8")

        self.assertIn("wechat_app.py", script)
        self.assertIn("--server.port 8502", script)
        self.assertIn("--server.address localhost", script)
        self.assertFalse((ROOT / "start_wechat_archiver.bat").exists())
        self.assertFalse((ROOT / "start_wechat_archiver.bat.bat").exists())


if __name__ == "__main__":
    unittest.main()
