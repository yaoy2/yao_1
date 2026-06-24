"""Persistent account labels for the LLM budget page."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_PATH = ROOT / "data" / "llm_budget_accounts.json"


def _clean_profile(value) -> dict[str, str]:
    if isinstance(value, dict):
        account = str(value.get("account", "")).strip()
        expiration_date = str(value.get("expiration_date", "")).strip()
    else:
        account = str(value).strip()
        expiration_date = ""
    profile = {}
    if account:
        profile["account"] = account
    if expiration_date:
        profile["expiration_date"] = expiration_date
    return profile


def load_accounts() -> dict[str, dict[str, str]]:
    if not ACCOUNTS_PATH.exists():
        return {}
    with ACCOUNTS_PATH.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return {}
    cleaned = {}
    for key, value in data.items():
        profile = _clean_profile(value)
        if profile:
            cleaned[str(key)] = profile
    return cleaned


def save_accounts(accounts: dict[str, dict[str, str]]) -> None:
    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {
        str(key): profile
        for key, value in accounts.items()
        if (profile := _clean_profile(value))
    }
    with ACCOUNTS_PATH.open("w", encoding="utf-8") as file:
        json.dump(cleaned, file, ensure_ascii=False, indent=2)


def get_login_account(provider_key: str) -> str:
    return load_accounts().get(provider_key, {}).get("account", "")


def get_expiration_date(provider_key: str) -> str:
    return load_accounts().get(provider_key, {}).get("expiration_date", "")


def save_login_account(provider_key: str, account: str) -> None:
    save_provider_profile(
        provider_key,
        account=account,
        expiration_date=get_expiration_date(provider_key),
    )


def save_provider_profile(provider_key: str, account: str, expiration_date: str) -> None:
    accounts = load_accounts()
    account = str(account).strip()
    expiration_date = str(expiration_date).strip()
    if account or expiration_date:
        accounts[provider_key] = {
            "account": account,
            "expiration_date": expiration_date,
        }
    else:
        accounts.pop(provider_key, None)
    save_accounts(accounts)
