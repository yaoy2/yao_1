from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dingtalk_daily.cli import execute_run, main
from dingtalk_daily.settings import CHINA, PROJECT_DIR, REPOSITORY_ROOT, output_path, safe_config_target, validate
from dingtalk_daily.storage import RunBusy, desktop_lock, run_lock, write_json, write_text


class LocalRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dingtalk-test-")
        self.root = Path(self.temp.name).resolve()
        self.config = {
            "version": 1, "priority_contact": "联系人甲", "self_group": "测试院务群",
            "self_names": ["测试本人"], "output_dir": str(self.root / "private"),
            "calibration_ok": True, "ui": {},
        }
        self.when = datetime(2026, 10, 2, 22, 0, tzinfo=CHINA)
        self.capture = {
            "date": "2026-10-02", "cutoff": self.when.isoformat(),
            "discovery_complete": True, "issues": [],
            "conversations": [
                {"id": "p", "title": "联系人甲", "kind": "direct", "complete": True,
                 "issues": [], "messages": []},
                {"id": "g", "title": "测试院务群", "kind": "group", "complete": True,
                 "issues": [], "messages": []},
            ],
        }

    def tearDown(self):
        self.temp.cleanup()

    def factory(self, config):
        capture = self.capture

        class Desktop:
            def doctor(self):
                return {"ready": True}

            def collect(self, when):
                return capture

        return Desktop()

    def test_complete_run_writes_verified_private_results(self):
        code, folder = execute_run(self.config, self.when, factory=self.factory)
        self.assertEqual(code, 0)
        report = json.loads((folder / "records.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["source_mode"], "desktop")
        self.assertTrue((folder / "整理.md").is_file())
        pointer = json.loads((folder.parent / "latest_success.json").read_text(encoding="utf-8"))
        self.assertEqual(pointer["run"], folder.name)
        self.assertFalse((folder / "capture.json").exists())

    def test_partial_does_not_replace_last_complete(self):
        _, first = execute_run(self.config, self.when, factory=self.factory)
        self.capture["discovery_complete"] = False
        code, second = execute_run(self.config, self.when, factory=self.factory)
        self.assertEqual(code, 2)
        self.assertNotEqual(first, second)
        pointer = json.loads((first.parent / "latest_success.json").read_text(encoding="utf-8"))
        self.assertEqual(pointer["run"], first.name)
        self.assertTrue((first / "整理.md").exists())

    def test_wrong_day_is_failed_and_does_not_write_records(self):
        self.capture["date"] = "2026-10-01"
        code, folder = execute_run(self.config, self.when, factory=self.factory)
        self.assertEqual(code, 1)
        self.assertFalse((folder / "records.json").exists())
        status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "failed")

    def test_adapter_cannot_extend_cutoff(self):
        self.capture["cutoff"] = "2026-10-02T23:00:00+08:00"
        code, folder = execute_run(self.config, self.when, factory=self.factory)
        self.assertEqual(code, 1)
        self.assertFalse((folder / "records.json").exists())

    def test_scheduled_rejects_late_catchup_without_touching_ui(self):
        def forbidden(config):
            self.fail("Must not touch the desktop outside the scheduled hour")
        code, _ = execute_run(self.config, self.when.replace(hour=0), scheduled=True, factory=forbidden)
        self.assertEqual(code, 1)

    def test_uncalibrated_machine_never_opens_ui(self):
        self.config["calibration_ok"] = False
        def forbidden(config):
            self.fail("Must not touch the desktop before calibration")
        code, _ = execute_run(self.config, self.when, factory=forbidden)
        self.assertEqual(code, 1)

    def test_replay_does_not_claim_live_success(self):
        code, folder = execute_run(self.config, self.when, replay=self.capture)
        self.assertEqual(code, 0)
        self.assertFalse((folder.parent / "latest_success.json").exists())
        status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "replay")

    def test_lock_blocks_simultaneous_manual_run(self):
        output = self.root / "private"
        with run_lock(output):
            with self.assertRaises(RunBusy):
                with run_lock(output):
                    self.fail("Lock allowed concurrent access")
        with run_lock(output):
            pass

    def test_desktop_lock_is_shared_across_output_directories(self):
        with desktop_lock():
            with self.assertRaises(RunBusy):
                execute_run(self.config, self.when, factory=self.factory)
        code, _ = execute_run(self.config, self.when, factory=self.factory)
        self.assertEqual(code, 0)

    def test_windows_message_line_endings_survive_verified_write(self):
        target = self.root / "newlines.md"
        text = "第一行\r\n第二行\n第三行\r末行"
        write_text(target, text)
        self.assertEqual(target.read_bytes(), text.encode("utf-8"))

    def test_repository_output_is_rejected(self):
        repo = self.root / "public-repo"
        with self.assertRaisesRegex(ValueError, "公开代码仓库"):
            output_path(str(repo / "private"), repository=repo)
        with self.assertRaises(ValueError):
            output_path("outputs")

    def test_private_config_cannot_escape_its_gitignore(self):
        with self.assertRaises(ValueError):
            safe_config_target(REPOSITORY_ROOT / "config" / "dingtalk.local.json")
        self.assertEqual(safe_config_target(PROJECT_DIR / "config.local.json"),
                         (PROJECT_DIR / "config.local.json").resolve())

    def test_doctor_failure_is_nonzero(self):
        config_file = self.root / "config.local.json"
        self.config["calibration_ok"] = False
        write_json(config_file, self.config)
        self.assertEqual(main(["--config", str(config_file), "doctor"]), 1)

    def test_calibration_failure_invalidates_previous_profile(self):
        config_file = self.root / "config.local.json"
        write_json(config_file, self.config)
        with patch("dingtalk_daily.cli.desktop_factory", side_effect=RuntimeError("adapter error")):
            self.assertEqual(main(["--config", str(config_file), "calibrate"]), 1)
        self.assertFalse(json.loads(config_file.read_text(encoding="utf-8"))["calibration_ok"])

    def test_failed_doctor_keeps_observed_profile_disabled_for_repair(self):
        config_file = self.root / "config.local.json"
        write_json(config_file, self.config)

        class Desktop:
            def calibrate(self):
                return {"observed": "synthetic control profile"}

            def doctor(self):
                raise ValueError("sample field unavailable")

        with patch("dingtalk_daily.cli.desktop_factory", return_value=Desktop()):
            self.assertEqual(main(["--config", str(config_file), "calibrate"]), 1)
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        self.assertFalse(saved["calibration_ok"])
        self.assertEqual(saved["ui"], {"observed": "synthetic control profile"})

    def test_alias_validation_rejects_empty_or_unknown_identity(self):
        for aliases in ([], [""], "本人"):
            self.config["self_names"] = aliases
            with self.assertRaises(ValueError):
                validate(self.config)


if __name__ == "__main__":
    unittest.main()
