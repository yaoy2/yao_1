import importlib.util
import tomllib
from pathlib import Path

spec = importlib.util.spec_from_file_location("local_password_setup", Path(__file__).resolve().parents[1] / "scripts/local_password_setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_password_entry_preserves_other_settings_and_quoted_characters():
    original = '[github_backup]\nrepo = "yaoy2/yao_1-data"\nbranch = "main"\n'
    password = '测试 " quote \\ backslash'
    result = tomllib.loads(setup.configured_text(original, password))
    assert result.pop("budget_password") == password
    assert result == tomllib.loads(original)


def test_existing_blank_password_is_replaced_without_duplicate_key():
    result = tomllib.loads(setup.configured_text('budget_password = " "\n[budget]\nyear = 2026\n', "local-test"))
    assert result == {"budget_password": "local-test", "budget": {"year": 2026}}
