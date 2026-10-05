"""Windows task planning checks; never register or start a real task.

The fixture CLI deliberately raises if executed. Preview/preflight tests must
only inspect the selected Python and imports, and leave the fixture untouched.
"""

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "integrations" / "newspaper" / "windows"
NAMESPACE = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else None


def ps_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def ps_run(code):
    prefix = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); "
    encoded = base64.b64encode((prefix + code).encode("utf-16le")).decode("ascii")
    return subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)


class WindowsTaskSourceTest(unittest.TestCase):
    def test_scripts_do_not_bypass_policy_or_modify_system_power_and_credentials(self):
        for path in WINDOWS.glob("*.ps1"):
            text = path.read_text(encoding="utf-8-sig")
            with self.subTest(path=path.name):
                for forbidden in ("ExecutionPolicy Bypass", "Set-ExecutionPolicy", "Stop-Process",
                                  "taskkill", "powercfg", "cmdkey", "-Password", "-RunLevel Highest"):
                    self.assertNotIn(forbidden.lower(), text.lower())

    def test_runner_uses_fixed_cli_modes_and_local_computer_l_receipt(self):
        text = (WINDOWS / "run-daily.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("scripts\\newspaper_daily.py", text)
        self.assertIn("$mode = '--publish'", text)
        self.assertIn("$mode = '--dry-run'", text)
        self.assertIn("$receipt.MachineRole -ne 'L'", text)
        self.assertIn("$receipt.ComputerName -ine $actualComputer", text)
        self.assertIn("$receipt.RepositoryRoot -ine $repositoryRoot", text)
        self.assertIn("[System.IO.FileShare]::None", text)
        self.assertIn("exit $exitCode", text)
        self.assertIn("WindowsApps", text)


@unittest.skipUnless(POWERSHELL, "Windows PowerShell 5.1 is required for these read-only checks")
class WindowsTaskPlanningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="newspaper-task-test-")
        cls.repo = Path(cls.temp.name) / "日报 测试 & O'Neil"
        cls.scripts = cls.repo / "integrations" / "newspaper" / "windows"
        cls.scripts.mkdir(parents=True)
        (cls.repo / "scripts").mkdir()
        (cls.repo / "scripts" / "newspaper_daily.py").write_text(
            "raise RuntimeError('THE_DAILY_CLI_MUST_NOT_RUN_DURING_WINDOWS_TESTS')\n", encoding="utf-8")
        for name in ("install-task.ps1", "run-daily.ps1"):
            (cls.scripts / name).write_text((WINDOWS / name).read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
        cls.installer = cls.scripts / "install-task.ps1"
        cls.runner = cls.scripts / "run-daily.ps1"
        result = ps_run("& " + ps_string(cls.installer)
                        + " -ComputerName ([Environment]::MachineName) -Preview -PythonPath " + ps_string(sys.executable))
        if result.returncode != 0:
            cls.temp.cleanup()
            raise AssertionError("Read-only preview failed: " + result.stderr)
        cls.plan = json.loads(result.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_both_scripts_parse_without_powershell_syntax_errors(self):
        for path in (self.installer, self.runner):
            code = "$tokens=$null; $errors=$null; [void][System.Management.Automation.Language.Parser]::ParseFile(" \
                   + ps_string(path) + ", [ref]$tokens, [ref]$errors); if ($errors.Count) { throw ($errors | Out-String) }; 'parsed'"
            result = ps_run(code)
            with self.subTest(path=path.name):
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("parsed", result.stdout)

    def test_preview_preserves_unicode_space_and_ampersand_paths_without_writing(self):
        self.assertEqual("Preview", self.plan["Mode"])
        self.assertEqual(str(self.repo), self.plan["RepositoryRoot"])
        self.assertEqual(str(self.runner), self.plan["RunnerPath"])
        self.assertFalse((self.repo / ".local").exists())
        xml = ET.fromstring(self.plan["TaskXml"])
        self.assertEqual(str(self.repo), xml.findtext("t:Actions/t:Exec/t:WorkingDirectory", namespaces=NAMESPACE))
        arguments = xml.findtext("t:Actions/t:Exec/t:Arguments", namespaces=NAMESPACE)
        self.assertIn('-File "' + str(self.runner) + '"', arguments)
        self.assertIn('-PythonPath "' + self.plan["PythonPath"] + '"', arguments)
        self.assertNotIn("Bypass", arguments)

    def test_beijing_daily_schedule_and_reliability_settings_are_explicit(self):
        xml = ET.fromstring(self.plan["TaskXml"])
        paths = {
            "t:Triggers/t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval": "1",
            "t:Principals/t:Principal/t:LogonType": "InteractiveToken",
            "t:Principals/t:Principal/t:RunLevel": "LeastPrivilege",
            "t:Settings/t:MultipleInstancesPolicy": "IgnoreNew",
            "t:Settings/t:StartWhenAvailable": "true",
            "t:Settings/t:RunOnlyIfNetworkAvailable": "true",
            "t:Settings/t:RestartOnFailure/t:Interval": "PT10M",
            "t:Settings/t:RestartOnFailure/t:Count": "3",
            "t:Settings/t:ExecutionTimeLimit": "PT15M",
            "t:Settings/t:Hidden": "true",
            "t:Settings/t:WakeToRun": "false",
            "t:Settings/t:AllowHardTerminate": "false",
        }
        for xpath, expected in paths.items():
            with self.subTest(xpath=xpath):
                self.assertEqual(expected, xml.findtext(xpath, namespaces=NAMESPACE))
        start = xml.findtext("t:Triggers/t:CalendarTrigger/t:StartBoundary", namespaces=NAMESPACE)
        self.assertRegex(start, r"^\d{4}-\d{2}-\d{2}T09:00:00\+08:00$")
        self.assertGreater(datetime.fromisoformat(start), datetime.now(timezone.utc))
        self.assertEqual(1, len(xml.find("t:Triggers", NAMESPACE)))
        self.assertIn("signed in", self.plan["Limitations"])
        self.assertIn("sign-out", self.plan["Limitations"])

    def test_wrong_computer_or_missing_role_confirmation_fails_before_registration(self):
        cases = (("-ComputerName '__NOT_THIS_COMPUTER__' -Preview", "Computer mismatch"),
                 ("-ComputerName ([Environment]::MachineName)", "requires -ConfirmComputerL"))
        for options, message in cases:
            code = "function Register-ScheduledTask { throw 'REAL_REGISTRATION_MUST_NOT_RUN' }; & " \
                   + ps_string(self.installer) + " " + options
            result = ps_run(code)
            with self.subTest(options=options):
                self.assertNotEqual(0, result.returncode)
                self.assertIn(message, result.stderr)
                self.assertNotIn("REAL_REGISTRATION_MUST_NOT_RUN", result.stderr)
        self.assertFalse((self.repo / ".local").exists())

    def test_preflight_only_imports_dependencies_and_publishing_requires_local_receipt(self):
        code = "& " + ps_string(self.runner) + " -Preflight -PythonPath " + ps_string(sys.executable) + " | ConvertTo-Json"
        result = ps_run(code)
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(["requests", "beautifulsoup4"], report["Dependencies"])
        self.assertFalse((self.repo / ".local").exists())
        result = ps_run("& " + ps_string(self.runner) + " -PythonPath " + ps_string(sys.executable))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("requires the local Computer L installation receipt", result.stderr)
        self.assertNotIn("THE_DAILY_CLI_MUST_NOT_RUN", result.stderr)
        self.assertFalse((self.repo / ".local").exists())

    def test_python_can_be_discovered_without_an_explicit_interpreter(self):
        code = "$env:PATH=" + ps_string(str(Path(sys.executable).parent) + os.pathsep) + "+$env:PATH; & " \
               + ps_string(self.runner) + " -Preflight | ConvertTo-Json"
        result = ps_run(code)
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertNotIn("Microsoft\\WindowsApps", report["PythonPath"])
        self.assertGreaterEqual(tuple(map(int, report["PythonVersion"].split("."))), (3, 10))
        self.assertFalse((self.repo / ".local").exists())

    def test_task_ownership_and_configuration_checks_reject_foreign_actions(self):
        # Extract only locally defined validation functions. The installer's
        # top-level execution, ScheduledTasks module and registration are absent.
        encoded_xml = base64.b64encode(self.plan["TaskXml"].encode("utf-8")).decode("ascii")
        code = "$tokens=$null; $errors=$null; $ast=[System.Management.Automation.Language.Parser]::ParseFile(" \
               + ps_string(self.installer) + ", [ref]$tokens, [ref]$errors); " \
               + "$functions=$ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst]}, $true); " \
               + ". ([scriptblock]::Create(($functions | ForEach-Object {$_.Extent.Text}) -join \"`n\")); " \
               + "$xmlText=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded_xml + "')); [xml]$planned=$xmlText; " \
               + "$ownerArgs=@{RunnerPath=" + ps_string(self.runner) + "; RepositoryRoot=" + ps_string(self.repo) \
               + "; PowerShellPath=$planned.Task.Actions.Exec.Command; AccountSid=$planned.Task.Principals.Principal.UserId; " \
               + "AccountName=" + ps_string(self.plan["RunAs"]) + "; ComputerName=[Environment]::MachineName}; " \
               + "Assert-NewspaperTaskOwner -Document $planned @ownerArgs; Assert-NewspaperTaskDefinition -Actual $planned -Planned $planned; " \
               + "[xml]$foreign=$xmlText; $foreign.Task.Actions.Exec.Command='cmd.exe'; $ownerRejected=$false; " \
               + "try {Assert-NewspaperTaskOwner -Document $foreign @ownerArgs} catch {$ownerRejected=$true}; " \
               + "[xml]$changed=$xmlText; $changed.Task.Principals.Principal.RunLevel='HighestAvailable'; $changedRejected=$false; " \
               + "try {Assert-NewspaperTaskDefinition -Actual $changed -Planned $planned} catch {$changedRejected=$true}; " \
               + "@{OwnerRejected=$ownerRejected; ChangedRejected=$changedRejected} | ConvertTo-Json"
        result = ps_run(code)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual({"OwnerRejected": True, "ChangedRejected": True}, json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
