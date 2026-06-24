"""各厂商余额查询基类"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class BalanceResult:
    """余额查询结果"""
    provider: str
    available: float
    currency: str = "CNY"
    total: Optional[float] = None
    granted: Optional[float] = None
    topped_up: Optional[float] = None
    error: Optional[str] = None

    @property
    def is_ok(self) -> bool:
        return self.error is None


class BaseProvider:
    """厂商查询基类"""
    name: str = ""
    display_name: str = ""
    console_url: str = ""
    supports_auto: bool = False

    def query(self, api_key: str) -> BalanceResult:
        raise NotImplementedError
