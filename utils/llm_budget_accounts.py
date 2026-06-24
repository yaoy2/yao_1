"""Persistent login-account labels for the LLM budget page."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_PATH = ROOT / "data" / "llm_budget_accounts.json"


def load_accounts() -> dict[str, str]:
    if not ACCOUNTS_PATH.exists():
        return {}
    with ACCOUNTS_PATH.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if str(value).strip()}


def save_accounts(accounts: dict[str, str]) -> None:
    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {
        str(key): str(value).strip()
        for key, value in accounts.items()
        if str(value).strip()
    }
    with ACCOUNTS_PATH.open("w", encoding="utf-8") as file:
        json.dump(cleaned, file, ensure_ascii=False, indent=2)


def get_login_account(provider_key: str) -> str:
    return load_accounts().get(provider_key, "")


def save_login_account(provider_key: str, account: str) -> None:
    accounts = load_accounts()
    account = str(account).strip()
    if account:
        accounts[provider_key] = account
    else:
        accounts.pop(provider_key, None)
    save_accounts(accounts)
