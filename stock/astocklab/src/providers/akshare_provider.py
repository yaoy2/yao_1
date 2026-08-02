from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterator
from zoneinfo import ZoneInfo

import akshare as ak
import numpy as np
import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.providers.base import MarketDataProvider


STOCK_COLUMN_MAP = {
    "日期": "trade_date",
    "date": "trade_date",
    "股票代码": "code",
    "开盘": "open",
    "open": "open",
    "收盘": "close",
    "close": "close",
    "最高": "high",
    "high": "high",
    "最低": "low",
    "low": "low",
    "成交量": "volume",
    "volume": "volume",
    "成交额": "amount",
    "amount": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change_amount",
    "换手率": "turnover_rate",
    "turnover": "turnover_rate",
}
INDEX_COLUMN_MAP = {
    "日期": "trade_date",
    "date": "trade_date",
    "开盘": "open",
    "open": "open",
    "最高": "high",
    "high": "high",
    "最低": "low",
    "low": "low",
    "收盘": "close",
    "close": "close",
    "成交量": "volume",
    "volume": "volume",
    "成交额": "amount",
    "amount": "amount",
}
STOCK_NUMERIC = [
    "open", "high", "low", "close", "volume", "amount", "amplitude",
    "pct_change", "change_amount", "turnover_rate",
]
BENCHMARK_NUMERIC = ["open", "high", "low", "close", "volume", "amount"]
TICK_COLUMN_MAP = {
    "成交时间": "trade_time",
    "成交价格": "price",
    "价格变动": "price_change",
    "成交量": "volume_lots",
    "成交金额": "amount",
    "性质": "side",
}
TICK_SIDE_MAP = {"买盘": "buy", "卖盘": "sell", "中性盘": "neutral"}
MINUTE_COLUMN_MAP = {
    "day": "trade_datetime",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume_shares",
    "amount": "amount",
}
INDEX_MINUTE_COLUMN_MAP = {
    "时间": "trade_datetime",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume_shares",
    "成交额": "amount",
}
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DAILY_BAR_READY_TIME = time(15, 10)


def stock_market_symbol(code: str) -> str:
    """Return the Sina/Tencent market-prefixed symbol for an A-share code."""
    if code.startswith(("0", "3")):
        return f"sz{code}"
    if code.startswith(("4", "8", "9")):
        return f"bj{code}"
    return f"sh{code}"


@contextmanager
def direct_network() -> Iterator[None]:
    """Temporarily bypass a broken OS proxy without changing system settings."""
    old_upper = os.environ.get("NO_PROXY")
    old_lower = os.environ.get("no_proxy")
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    try:
        yield
    finally:
        if old_upper is None:
            os.environ.pop("NO_PROXY", None)
        else:
            os.environ["NO_PROXY"] = old_upper
        if old_lower is None:
            os.environ.pop("no_proxy", None)
        else:
            os.environ["no_proxy"] = old_lower


def _convert_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.replace([np.inf, -np.inf], np.nan)


def drop_incomplete_current_daily_bar(
    frame: pd.DataFrame,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Exclude today's still-forming daily bar before the post-close safety time."""
    if frame.empty or "trade_date" not in frame:
        return frame
    market_now = now or datetime.now(SHANGHAI_TZ)
    if market_now.tzinfo is None:
        market_now = market_now.replace(tzinfo=SHANGHAI_TZ)
    else:
        market_now = market_now.astimezone(SHANGHAI_TZ)
    if market_now.time() >= DAILY_BAR_READY_TIME:
        return frame
    current_date = market_now.date()
    incomplete_count = int((frame["trade_date"] == current_date).sum())
    if incomplete_count:
        logger.warning(
            "收盘前剔除未完成日线 trade_date={} rows={}",
            current_date,
            incomplete_count,
        )
        return frame.loc[frame["trade_date"] < current_date].reset_index(drop=True)
    return frame


def standardize_stock_daily(
    raw: pd.DataFrame,
    code: str,
    adjust: str,
    source: str = "akshare.stock_zh_a_hist",
) -> pd.DataFrame:
    """Normalize AKShare stock daily fields without filling invalid values."""
    if raw.empty:
        return pd.DataFrame()
    frame = raw.rename(columns=STOCK_COLUMN_MAP).copy()
    required = {"trade_date", "open", "high", "low", "close", "volume", "amount"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"股票数据缺少必要字段: {sorted(missing)}")
    for optional in ["amplitude", "pct_change", "change_amount", "turnover_rate"]:
        if optional not in frame:
            frame[optional] = np.nan
    frame["code"] = str(code)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
    frame["adjust_type"] = "raw" if adjust == "" else adjust
    frame = _convert_numeric(frame, STOCK_NUMERIC)
    if source in {"akshare.stock_zh_a_daily", "akshare.stock_zh_a_hist_tx"}:
        frame["volume"] = frame["volume"] / 100.0
        frame["turnover_rate"] = frame["turnover_rate"] * 100.0
    previous_close = frame["close"].shift(1)
    if frame["pct_change"].isna().all():
        frame["pct_change"] = safe_pct = (frame["close"] / previous_close.replace(0, np.nan) - 1) * 100
        frame["pct_change"] = safe_pct.replace([np.inf, -np.inf], np.nan)
    if frame["change_amount"].isna().all():
        frame["change_amount"] = frame["close"].diff()
    if frame["amplitude"].isna().all():
        frame["amplitude"] = ((frame["high"] - frame["low"]) / previous_close.replace(0, np.nan) * 100).replace(
            [np.inf, -np.inf], np.nan
        )
    frame["source"] = source
    frame["fetched_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    columns = [
        "code", "trade_date", "adjust_type", "open", "high", "low", "close",
        "volume", "amount", "amplitude", "pct_change", "change_amount",
        "turnover_rate", "source", "fetched_at",
    ]
    frame = frame[columns].dropna(subset=["trade_date"]).sort_values("trade_date")
    return frame.drop_duplicates(["code", "trade_date", "adjust_type"], keep="last").reset_index(drop=True)


def standardize_index_daily(raw: pd.DataFrame, code: str) -> pd.DataFrame:
    """Normalize an AKShare index DataFrame and preserve unavailable amount as null."""
    if raw.empty:
        return pd.DataFrame()
    frame = raw.rename(columns=INDEX_COLUMN_MAP).copy()
    required = {"trade_date", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"指数数据缺少必要字段: {sorted(missing)}")
    if "amount" not in frame:
        frame["amount"] = np.nan
    frame["code"] = str(code)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
    frame = _convert_numeric(frame, BENCHMARK_NUMERIC)
    frame["source"] = "akshare.stock_zh_index_daily"
    frame["fetched_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    columns = [
        "code", "trade_date", "open", "high", "low", "close",
        "volume", "amount", "source", "fetched_at",
    ]
    frame = frame[columns].dropna(subset=["trade_date"]).sort_values("trade_date")
    return frame.drop_duplicates(["code", "trade_date"], keep="last").reset_index(drop=True)


def standardize_tick_trades(raw: pd.DataFrame, code: str, trade_date: date) -> pd.DataFrame:
    """Normalize Tencent transaction details with deterministic sequence numbers."""
    if raw.empty:
        return pd.DataFrame()
    frame = raw.rename(columns=TICK_COLUMN_MAP).copy()
    required = {"trade_time", "price", "volume_lots", "amount", "side"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"逐笔成交缺少必要字段: {sorted(missing)}")
    if "price_change" not in frame:
        frame["price_change"] = np.nan
    for column in ["price", "price_change", "volume_lots", "amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["trade_date"] = trade_date
    combined = pd.to_datetime(
        trade_date.isoformat() + " " + frame["trade_time"].astype(str),
        errors="coerce",
    )
    frame["trade_datetime"] = combined
    frame["trade_time"] = combined.dt.time
    frame["side"] = frame["side"].map(TICK_SIDE_MAP).fillna("unknown")
    frame["code"] = str(code)
    frame["source"] = "akshare.stock_zh_a_tick_tx_js"
    frame["fetched_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    frame = frame.dropna(
        subset=["trade_datetime", "price", "volume_lots", "amount"]
    ).sort_values(["trade_datetime"], kind="stable").reset_index(drop=True)
    frame["sequence_no"] = np.arange(1, len(frame) + 1, dtype=int)
    columns = [
        "code", "trade_date", "sequence_no", "trade_time", "trade_datetime",
        "price", "price_change", "volume_lots", "amount", "side", "source", "fetched_at",
    ]
    return frame[columns]


def standardize_minute_bars(
    raw: pd.DataFrame,
    code: str,
    source: str = "akshare.stock_zh_a_minute",
) -> pd.DataFrame:
    """Normalize recent Sina-format one-minute bars returned by AKShare."""
    if raw.empty:
        return pd.DataFrame()
    frame = raw.rename(columns=MINUTE_COLUMN_MAP).copy()
    required = {
        "trade_datetime", "open", "high", "low", "close", "volume_shares", "amount"
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"分钟行情缺少必要字段: {sorted(missing)}")
    frame["trade_datetime"] = pd.to_datetime(frame["trade_datetime"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume_shares", "amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["code"] = str(code)
    frame["interval_minutes"] = 1
    frame["source"] = source
    frame["fetched_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    columns = [
        "code", "trade_datetime", "interval_minutes", "open", "high", "low", "close",
        "volume_shares", "amount", "source", "fetched_at",
    ]
    frame = frame[columns].dropna(subset=["trade_datetime"]).sort_values("trade_datetime")
    return frame.drop_duplicates(
        ["code", "trade_datetime", "interval_minutes"], keep="last"
    ).reset_index(drop=True)


def standardize_benchmark_minute_bars(
    raw: pd.DataFrame,
    code: str,
) -> pd.DataFrame:
    """Normalize Eastmoney one-minute index bars and preserve missing opens."""
    if raw.empty:
        return pd.DataFrame()
    frame = raw.rename(columns=INDEX_MINUTE_COLUMN_MAP).copy()
    required = {
        "trade_datetime", "open", "high", "low", "close",
        "volume_shares", "amount",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"指数分钟行情缺少必要字段: {sorted(missing)}")
    frame["trade_datetime"] = pd.to_datetime(
        frame["trade_datetime"], errors="coerce"
    )
    for column in ["open", "high", "low", "close", "volume_shares", "amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame.loc[frame["open"] <= 0, "open"] = np.nan
    frame["code"] = str(code)
    frame["interval_minutes"] = 1
    frame["source"] = "akshare.index_zh_a_hist_min_em"
    frame["fetched_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    columns = [
        "code", "trade_datetime", "interval_minutes", "open", "high", "low",
        "close", "volume_shares", "amount", "source", "fetched_at",
    ]
    frame = frame[columns].dropna(
        subset=["trade_datetime", "close"]
    ).sort_values("trade_datetime")
    return frame.drop_duplicates(
        ["code", "trade_datetime", "interval_minutes"], keep="last"
    ).reset_index(drop=True)


class AkshareProvider(MarketDataProvider):
    """AKShare implementation for A-share stock and Shenzhen index daily data."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_stock_daily(self, code: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        logger.info("请求股票日线 code={} adjust={} start={} end={}", code, adjust or "raw", start, end)
        source = "akshare.stock_zh_a_hist"
        try:
            with direct_network():
                raw = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust=adjust,
                )
        except Exception as exc:
            source = "akshare.stock_zh_a_daily"
            symbol = stock_market_symbol(code)
            logger.warning("主接口失败，切换新浪日线 code={} error={}", code, exc)
            with direct_network():
                raw = ak.stock_zh_a_daily(
                    symbol=symbol,
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust=adjust,
                )
        result = standardize_stock_daily(raw, code, adjust, source)
        result = drop_incomplete_current_daily_bar(result)
        logger.info("股票日线返回 code={} adjust={} rows={}", code, adjust or "raw", len(result))
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_benchmark_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        logger.info("请求指数日线 code={} start={} end={} interface=stock_zh_index_daily", code, start, end)
        symbol = f"sz{code}" if code.startswith("399") else f"sh{code}"
        with direct_network():
            raw = ak.stock_zh_index_daily(symbol=symbol)
        result = standardize_index_daily(raw, code)
        result = drop_incomplete_current_daily_bar(result)
        if not result.empty:
            mask = (result["trade_date"] >= start) & (result["trade_date"] <= end)
            result = result.loc[mask].reset_index(drop=True)
        logger.info("指数日线返回 code={} rows={}", code, len(result))
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_tick_trades(self, code: str, trade_date: date) -> pd.DataFrame:
        """Fetch the latest trading day's transaction details from Tencent."""
        symbol = stock_market_symbol(code)
        logger.info("请求逐笔成交 code={} expected_date={}", code, trade_date)
        with direct_network():
            raw = ak.stock_zh_a_tick_tx_js(symbol=symbol)
        result = standardize_tick_trades(raw, code, trade_date)
        logger.info("逐笔成交返回 code={} rows={}", code, len(result))
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_minute_bars(self, code: str) -> pd.DataFrame:
        """Fetch recent unadjusted one-minute bars."""
        symbol = stock_market_symbol(code)
        logger.info("请求分钟行情 code={} period=1", code)
        with direct_network():
            raw = ak.stock_zh_a_minute(symbol=symbol, period="1", adjust="")
        result = standardize_minute_bars(raw, code)
        logger.info("分钟行情返回 code={} rows={}", code, len(result))
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_benchmark_minute_bars(self, code: str) -> pd.DataFrame:
        """Fetch recent one-minute bars for an A-share benchmark index."""
        symbol = f"sz{code}" if code.startswith("399") else f"sh{code}"
        logger.info(
            "请求指数分钟行情 code={} interface=stock_zh_a_minute",
            code,
        )
        try:
            with direct_network():
                raw = ak.stock_zh_a_minute(
                    symbol=symbol,
                    period="1",
                    adjust="",
                )
            result = standardize_minute_bars(
                raw,
                code,
                "akshare.stock_zh_a_minute[index]",
            )
        except Exception as exc:
            market_now = datetime.now(SHANGHAI_TZ)
            start = market_now - timedelta(days=7)
            logger.warning(
                "新浪指数分钟失败，切换东方财富 code={} error={}",
                code,
                exc,
            )
            with direct_network():
                raw = ak.index_zh_a_hist_min_em(
                    symbol=code,
                    period="1",
                    start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
                    end_date=market_now.strftime("%Y-%m-%d %H:%M:%S"),
                )
            result = standardize_benchmark_minute_bars(raw, code)
        logger.info("指数分钟行情返回 code={} rows={}", code, len(result))
        return result
