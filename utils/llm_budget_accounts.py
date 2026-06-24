"""Persistent account labels for the LLM budget page."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_PATH = ROOT / "data" / "llm_budget_accounts.json"


def _clean_account_profile(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    expiration_date = str(value.get("expiration_date", "")).strip()
    return {"expiration_date": expiration_date} if expiration_date else {}


def _clean_provider_profile(value) -> dict:
    if isinstance(value, dict) and "accounts" in value:
        accounts = {
            str(account).strip(): _clean_account_profile(profile)
            for account, profile in value.get("accounts", {}).items()
            if str(account).strip()
        }
        active_account = str(value.get("active_account", "")).strip()
        if active_account not in accounts:
            active_account = next(iter(accounts), "")
        return {"active_account": active_account, "accounts": accounts} if accounts else {}

    if isinstance(value, dict):
        account = str(value.get("account", "")).strip()
        expiration_date = str(value.get("expiration_date", "")).strip()
    else:
        account = str(value).strip()
        expiration_date = ""
    if not account:
        return {}
    profile = {"expiration_date": expiration_date} if expiration_date else {}
    return {"active_account": account, "accounts": {account: profile}}


def load_accounts() -> dict[str, dict]:
    if not ACCOUNTS_PATH.exists():
        return {}
    with ACCOUNTS_PATH.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return {}
    cleaned = {}
    for key, value in data.items():
        profile = _clean_provider_profile(value)
        if profile:
            cleaned[str(key)] = profile
    return cleaned


def save_accounts(accounts: dict[str, dict]) -> None:
    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {
        str(key): profile
        for key, value in accounts.items()
        if (profile := _clean_provider_profile(value))
    }
    with ACCOUNTS_PATH.open("w", encoding="utf-8") as file:
        json.dump(cleaned, file, ensure_ascii=False, indent=2)


def get_login_account(provider_key: str) -> str:
    return load_accounts().get(provider_key, {}).get("active_account", "")


def get_expiration_date(provider_key: str, account: str | None = None) -> str:
    provider = load_accounts().get(provider_key, {})
    account = str(account if account is not None else provider.get("active_account", "")).strip()
    return provider.get("accounts", {}).get(account, {}).get("expiration_date", "")


def list_login_accounts(provider_key: str) -> list[str]:
    return list(load_accounts().get(provider_key, {}).get("accounts", {}).keys())


def set_active_login_account(provider_key: str, account: str) -> None:
    accounts = load_accounts()
    provider = accounts.get(provider_key, {})
    account = str(account).strip()
    if account and account in provider.get("accounts", {}):
        provider["active_account"] = account
        accounts[provider_key] = provider
        save_accounts(accounts)


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
        provider = accounts.get(provider_key, {"active_account": "", "accounts": {}})
        provider_accounts = provider.setdefault("accounts", {})
        provider_accounts[account] = {"expiration_date": expiration_date} if expiration_date else {}
        provider["active_account"] = account
        accounts[provider_key] = provider
    else:
        accounts.pop(provider_key, None)
    save_accounts(accounts)
