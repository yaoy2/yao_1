"""DeepSeek 余额查询"""

import requests
from .base import BaseProvider, BalanceResult


class DeepSeekProvider(BaseProvider):
    name = "deepseek"
    display_name = "DeepSeek"
    console_url = "https://platform.deepseek.com/usage"
    supports_auto = True

    def query(self, api_key: str) -> BalanceResult:
        try:
            resp = requests.get(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("balance_infos"):
                return BalanceResult(provider=self.name, available=0, error="无余额信息")

            info = data["balance_infos"][0]
            return BalanceResult(
                provider=self.name,
                available=float(info["total_balance"]),
                currency=info.get("currency", "CNY"),
                total=float(info["total_balance"]),
                granted=float(info.get("granted_balance", 0)),
                topped_up=float(info.get("topped_up_balance", 0)),
            )
        except Exception as e:
            return BalanceResult(provider=self.name, available=0, error=str(e))
