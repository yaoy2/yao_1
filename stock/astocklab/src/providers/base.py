from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class MarketDataProvider(ABC):
    """Interface for replaceable market data sources."""

    @abstractmethod
    def fetch_stock_daily(self, code: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def fetch_benchmark_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def fetch_tick_trades(self, code: str, trade_date: date) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def fetch_minute_bars(self, code: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def fetch_benchmark_minute_bars(self, code: str) -> pd.DataFrame:
        raise NotImplementedError
