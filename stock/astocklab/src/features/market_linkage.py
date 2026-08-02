from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = numerator / denominator.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def calculate_market_linkage(
    stock: pd.DataFrame,
    benchmark: pd.DataFrame,
    benchmark_code: str,
    settings: dict[str, Any],
) -> pd.DataFrame:
    """Calculate backward-looking linkage statistics for one stock-index pair."""
    if stock.empty or benchmark.empty:
        return pd.DataFrame()
    periods = settings["features"]["market_linkage"]["return_periods"]
    windows = settings["features"]["market_linkage"]["correlation_windows"]
    threshold = settings["features"]["market_linkage"]["strong_excess_20d"]
    left = stock[["code", "trade_date", "close"]].copy().sort_values("trade_date")
    right = benchmark[["trade_date", "close"]].copy().sort_values("trade_date")
    left["trade_date"] = pd.to_datetime(left["trade_date"]).dt.date
    right["trade_date"] = pd.to_datetime(right["trade_date"]).dt.date
    left = left.drop_duplicates("trade_date", keep="last")
    right = right.drop_duplicates("trade_date", keep="last")
    for period in periods:
        left[f"stock_ret_{period}d"] = left["close"].pct_change(period, fill_method=None)
        right[f"benchmark_ret_{period}d"] = right["close"].pct_change(period, fill_method=None)
    right = right.drop(columns=["close"])
    frame = left.merge(right, on="trade_date", how="left", validate="one_to_one")
    for period in periods:
        frame[f"excess_ret_{period}d"] = (
            frame[f"stock_ret_{period}d"] - frame[f"benchmark_ret_{period}d"]
        )
    for window in windows:
        stock_ret = frame["stock_ret_1d"]
        benchmark_ret = frame["benchmark_ret_1d"]
        frame[f"correlation_{window}d"] = stock_ret.rolling(
            window, min_periods=window
        ).corr(benchmark_ret)
        covariance = stock_ret.rolling(window, min_periods=window).cov(benchmark_ret)
        variance = benchmark_ret.rolling(window, min_periods=window).var()
        frame[f"beta_{window}d"] = _safe_divide(covariance, variance)
    direction_ready = frame[["stock_ret_1d", "benchmark_ret_1d"]].notna().all(axis=1)
    frame["same_direction"] = (
        np.sign(frame["stock_ret_1d"]) == np.sign(frame["benchmark_ret_1d"])
    ).where(direction_ready, pd.NA).astype("boolean")
    frame["relationship_state"] = "insufficient_data"
    ready = frame[["excess_ret_20d", "correlation_60d"]].notna().all(axis=1)
    frame.loc[ready, "relationship_state"] = "neutral"
    frame.loc[ready & (frame["excess_ret_20d"] >= threshold), "relationship_state"] = "outperforming"
    frame.loc[ready & (frame["excess_ret_20d"] <= -threshold), "relationship_state"] = "underperforming"
    frame.loc[
        ready & (frame["correlation_60d"] >= 0.6) &
        (frame["excess_ret_20d"].abs() < threshold),
        "relationship_state",
    ] = "coupled"
    frame.loc[
        ready & (frame["correlation_60d"] < 0.2) &
        (frame["excess_ret_20d"].abs() < threshold),
        "relationship_state",
    ] = "decoupled"
    frame["benchmark_code"] = benchmark_code
    frame["calculated_at"] = datetime.now()
    frame = frame.replace([np.inf, -np.inf], np.nan)
    columns = [
        "code", "trade_date", "benchmark_code",
        "stock_ret_1d", "stock_ret_5d", "stock_ret_20d", "stock_ret_60d",
        "benchmark_ret_1d", "benchmark_ret_5d", "benchmark_ret_20d", "benchmark_ret_60d",
        "excess_ret_1d", "excess_ret_5d", "excess_ret_20d", "excess_ret_60d",
        "correlation_20d", "correlation_60d", "beta_20d", "beta_60d",
        "same_direction", "relationship_state", "calculated_at",
    ]
    return frame[columns].reset_index(drop=True)
