from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide two series, returning null for zero denominators and non-finite results."""
    result = numerator / denominator.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).apply(
        lambda values: float(pd.Series(values).rank(pct=True).iloc[-1]),
        raw=False,
    )


def _streaks(change: pd.Series) -> tuple[pd.Series, pd.Series]:
    up_values: list[int] = []
    down_values: list[int] = []
    up = down = 0
    for value in change:
        if pd.isna(value):
            up = down = 0
        elif value > 0:
            up += 1
            down = 0
        elif value < 0:
            down += 1
            up = 0
        else:
            up = down = 0
        up_values.append(up)
        down_values.append(down)
    return (
        pd.Series(up_values, index=change.index, dtype="int64"),
        pd.Series(down_values, index=change.index, dtype="int64"),
    )


def _state_labels(frame: pd.DataFrame, thresholds: dict[str, Any]) -> pd.DataFrame:
    trend = thresholds["trend"]
    volume = thresholds["volume"]
    location = thresholds["location"]
    relative = thresholds["relative_strength"]

    frame["trend_state"] = "insufficient_data"
    ready = frame[["ma20", "ma60", "dist_ma20"]].notna().all(axis=1)
    frame.loc[ready, "trend_state"] = "range"
    frame.loc[ready & (frame["close"] > frame["ma20"]) & (frame["ma20"] >= frame["ma60"]) &
              (frame["dist_ma20"] >= trend["ma20_distance"]), "trend_state"] = "up"
    frame.loc[ready & (frame["close"] > frame["ma20"]) & (frame["ma20"] > frame["ma60"]) &
              (frame["dist_ma20"] >= trend["strong_ma20_distance"]), "trend_state"] = "strong_up"
    frame.loc[ready & (frame["close"] < frame["ma20"]) & (frame["ma20"] <= frame["ma60"]) &
              (frame["dist_ma20"] <= -trend["ma20_distance"]), "trend_state"] = "down"
    frame.loc[ready & (frame["close"] < frame["ma20"]) & (frame["ma20"] < frame["ma60"]) &
              (frame["dist_ma20"] <= -trend["strong_ma20_distance"]), "trend_state"] = "strong_down"

    frame["volume_state"] = "insufficient_data"
    volume_ready = frame["volume_ratio_20"].notna()
    frame.loc[volume_ready, "volume_state"] = "normal_volume"
    frame.loc[volume_ready & (frame["volume_ratio_20"] >= volume["high_ratio"]), "volume_state"] = "high_volume"
    frame.loc[volume_ready & (frame["volume_ratio_20"] <= volume["low_ratio"]), "volume_state"] = "low_volume"

    frame["location_state"] = "insufficient_data"
    location_ready = frame["range_position_20"].notna()
    frame.loc[location_ready, "location_state"] = "middle"
    frame.loc[location_ready & (frame["range_position_20"] >= location["near_high"]), "location_state"] = "near_high"
    frame.loc[location_ready & (frame["range_position_20"] <= location["near_low"]), "location_state"] = "near_low"
    frame.loc[location_ready & frame["new_high_20"], "location_state"] = "breakout"
    frame.loc[location_ready & frame["new_low_20"], "location_state"] = "breakdown"

    frame["relative_strength_state"] = "insufficient_data"
    rs_ready = frame["rs_20"].notna()
    frame.loc[rs_ready, "relative_strength_state"] = "neutral"
    frame.loc[rs_ready & (frame["rs_20"] >= relative["strong_20d"]), "relative_strength_state"] = "strong"
    frame.loc[rs_ready & (frame["rs_20"] <= relative["weak_20d"]), "relative_strength_state"] = "weak"
    return frame


def calculate_daily_features(
    stock: pd.DataFrame,
    benchmark: pd.DataFrame,
    settings: dict[str, Any],
) -> pd.DataFrame:
    """Calculate backward-looking daily features from qfq stock and aligned benchmark bars."""
    if stock.empty:
        return pd.DataFrame()
    frame = stock.copy().sort_values("trade_date").drop_duplicates("trade_date", keep="last").reset_index(drop=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    periods = settings["features"]["return_periods"]
    ma_periods = settings["features"]["ma_periods"]
    atr_period = int(settings["features"]["atr_period"])
    percentile_window = int(settings["features"]["percentile_window"])

    for period in periods:
        frame[f"ret_{period}d"] = frame["close"].pct_change(periods=period, fill_method=None)
    for period in ma_periods:
        frame[f"ma{period}"] = frame["close"].rolling(period, min_periods=period).mean()
        frame[f"dist_ma{period}"] = safe_divide(frame["close"] - frame[f"ma{period}"], frame[f"ma{period}"])

    for period in (5, 20):
        frame[f"volume_ma{period}"] = frame["volume"].rolling(period, min_periods=period).mean()
        frame[f"volume_ratio_{period}"] = safe_divide(frame["volume"], frame[f"volume_ma{period}"])
        frame[f"amount_ma{period}"] = frame["amount"].rolling(period, min_periods=period).mean()

    previous_close = frame["close"].shift(1)
    true_range = pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - previous_close).abs(),
        (frame["low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    frame["atr14"] = true_range.rolling(atr_period, min_periods=atr_period).mean()
    frame["atr14_pct"] = safe_divide(frame["atr14"], frame["close"])

    for period in (20, 60):
        rolling_high = frame["high"].rolling(period, min_periods=period).max()
        rolling_low = frame["low"].rolling(period, min_periods=period).min()
        frame[f"range_position_{period}"] = safe_divide(frame["close"] - rolling_low, rolling_high - rolling_low)
        frame[f"drawdown_{period}"] = safe_divide(frame["close"], rolling_high) - 1

    frame["gap_pct"] = safe_divide(frame["open"] - previous_close, previous_close)
    daily_range = frame["high"] - frame["low"]
    frame["body_pct"] = safe_divide((frame["close"] - frame["open"]).abs(), daily_range)
    frame["upper_wick_pct"] = safe_divide(frame["high"] - frame[["open", "close"]].max(axis=1), daily_range)
    frame["lower_wick_pct"] = safe_divide(frame[["open", "close"]].min(axis=1) - frame["low"], daily_range)
    frame["close_location_value"] = safe_divide(frame["close"] - frame["low"], daily_range)
    high20 = frame["high"].rolling(20, min_periods=20).max()
    low20 = frame["low"].rolling(20, min_periods=20).min()
    frame["new_high_20"] = (frame["high"] >= high20).where(high20.notna(), False)
    frame["new_low_20"] = (frame["low"] <= low20).where(low20.notna(), False)

    benchmark_returns = pd.DataFrame(columns=["trade_date"])
    if not benchmark.empty:
        benchmark_returns = benchmark.copy().sort_values("trade_date").drop_duplicates("trade_date", keep="last")
        benchmark_returns["trade_date"] = pd.to_datetime(benchmark_returns["trade_date"]).dt.date
        for period in (5, 10, 20):
            benchmark_returns[f"benchmark_ret_{period}d"] = benchmark_returns["close"].pct_change(
                periods=period, fill_method=None
            )
        benchmark_returns = benchmark_returns[["trade_date", "benchmark_ret_5d", "benchmark_ret_10d", "benchmark_ret_20d"]]
    frame = frame.merge(benchmark_returns, on="trade_date", how="left", validate="one_to_one")
    for period in (5, 10, 20):
        frame[f"rs_{period}"] = frame[f"ret_{period}d"] - frame[f"benchmark_ret_{period}d"]

    frame["up_streak"], frame["down_streak"] = _streaks(frame["close"].diff())
    frame["volume_percentile_120"] = _rolling_percentile(frame["volume"], percentile_window)
    rolling_volatility = frame["ret_1d"].rolling(20, min_periods=20).std()
    frame["volatility_percentile_120"] = _rolling_percentile(rolling_volatility, percentile_window)
    frame = _state_labels(frame, settings["features"]["thresholds"])
    frame["calculated_at"] = datetime.now()
    frame = frame.replace([np.inf, -np.inf], np.nan)

    columns = [
        "code", "trade_date", "close", "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
        "ma5", "ma10", "ma20", "ma60", "dist_ma5", "dist_ma10", "dist_ma20", "dist_ma60",
        "volume_ma5", "volume_ma20", "volume_ratio_5", "volume_ratio_20",
        "amount_ma5", "amount_ma20", "atr14", "atr14_pct",
        "range_position_20", "range_position_60", "drawdown_20", "drawdown_60",
        "gap_pct", "body_pct", "upper_wick_pct", "lower_wick_pct", "close_location_value",
        "new_high_20", "new_low_20", "rs_5", "rs_10", "rs_20", "up_streak", "down_streak",
        "volume_percentile_120", "volatility_percentile_120", "trend_state", "volume_state",
        "location_state", "relative_strength_state", "calculated_at",
    ]
    return frame[columns].reset_index(drop=True)
