import json
import os
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


@unittest.skipUnless(os.name == "nt", "The management entry is a Windows PowerShell script.")
class ManagementTests(unittest.TestCase):
    def plan(self, *args):
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(HERE / "manage.ps1"), "-DryRun", *args],
            cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )

    def test_default_lists_both_existing_runtime_locations(self):
        result = self.plan()
        self.assertEqual(result.returncode, 0, result.stderr)
        plans = json.loads(result.stdout)
        self.assertEqual({p["Instance"] for p in plans}, {"whale", "gpt"})
        expected = {"whale": "whale_companion", "gpt": "gpt_qq"}
        for plan in plans:
            self.assertEqual(plan["Action"], "status")
            self.assertEqual(Path(plan["RuntimeRoot"]), REPO / ".local" / expected[plan["Instance"]])
            self.assertTrue(Path(plan["Entry"]).is_relative_to(HERE))

    def test_targeted_start_only_resolves_the_selected_instance(self):
        result = self.plan("-Instance", "gpt", "-Action", "start-all")
        self.assertEqual(result.returncode, 0, result.stderr)
        plans = json.loads(result.stdout)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["Instance"], "gpt")
        self.assertEqual(Path(plans[0]["Entry"]), HERE / "gpt_qq/manage.ps1")

    def test_bulk_start_cannot_accidentally_resume_the_other_bot(self):
        result = self.plan("-Action", "start-all")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Bulk startup is not supported", result.stderr)

    def test_unsupported_operation_fails_before_dispatch(self):
        result = self.plan("-Instance", "gpt", "-Action", "backup")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not supported", result.stderr)


if __name__ == "__main__":
    unittest.main()
