"""Kimi / Moonshot 余额查询"""

import requests
from .base import BaseProvider, BalanceResult


class KimiProvider(BaseProvider):
    name = "kimi"
    display_name = "Kimi (月之暗面)"
    console_url = "https://platform.moonshot.cn/console/account"
    supports_auto = True

    def query(self, api_key: str) -> BalanceResult:
        try:
            resp = requests.get(
                "https://api.moonshot.cn/v1/users/me/balance",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                return BalanceResult(
                    provider=self.name, available=0,
                    error=data.get("msg", "查询失败"),
                )
            balance = data["data"]
            return BalanceResult(
                provider=self.name,
                available=balance["available_balance"],
                currency="CNY",
                total=balance["available_balance"],
                granted=balance.get("voucher_balance"),
                topped_up=balance.get("cash_balance"),
            )
        except Exception as e:
            return BalanceResult(provider=self.name, available=0, error=str(e))
