import py_compile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CompileTest(unittest.TestCase):
    def test_app_modules_compile(self):
        files = list((ROOT / "app").glob("*.py"))
        self.assertGreater(len(files), 5)
        for path in files:
            with self.subTest(path.name):
                py_compile.compile(str(path), doraise=True)


if __name__ == "__main__":
    unittest.main()
