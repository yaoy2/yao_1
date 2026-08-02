from __future__ import annotations

from datetime import datetime, time
from typing import Any

import numpy as np
import pandas as pd


def reconcile_tick_with_daily(
    ticks: pd.DataFrame,
    daily_row: pd.Series,
    tolerance: float = 0.02,
) -> dict[str, float]:
    """Compare transaction-detail totals with the corresponding daily bar."""
    if ticks.empty:
        raise ValueError("逐笔成交为空")
    tick_amount = float(ticks["amount"].sum())
    tick_volume = float(ticks["volume_lots"].sum())
    daily_amount = float(daily_row["amount"])
    daily_volume = float(daily_row["volume"])
    amount_coverage = tick_amount / daily_amount if daily_amount else np.nan
    volume_coverage = tick_volume / daily_volume if daily_volume else np.nan
    last_price = float(ticks.sort_values("sequence_no").iloc[-1]["price"])
    close = float(daily_row["close"])
    if not np.isclose(last_price, close, atol=0.011):
        raise ValueError(f"逐笔末价 {last_price} 与日线收盘价 {close} 不一致")
    for label, value in [("成交额", amount_coverage), ("成交量", volume_coverage)]:
        if pd.isna(value) or not 1 - tolerance <= value <= 1 + tolerance:
            raise ValueError(f"逐笔{label}覆盖率异常: {value}")
    return {
        "amount_coverage": amount_coverage,
        "volume_coverage": volume_coverage,
    }


def calculate_daily_money_flow(
    ticks: pd.DataFrame,
    daily_row: pd.Series,
    settings: dict[str, Any],
) -> pd.DataFrame:
    """Summarize transaction behavior without claiming investor identity."""
    coverage = reconcile_tick_with_daily(ticks, daily_row)
    rules = settings["features"]["money_flow"]
    frame = ticks.copy().sort_values("sequence_no")
    total_amount = float(frame["amount"].sum())
    buy_amount = float(frame.loc[frame["side"] == "buy", "amount"].sum())
    sell_amount = float(frame.loc[frame["side"] == "sell", "amount"].sum())
    neutral_amount = float(frame.loc[~frame["side"].isin(["buy", "sell"]), "amount"].sum())
    net_active = buy_amount - sell_amount
    net_ratio = net_active / total_amount if total_amount else np.nan
    buy_sell_ratio = buy_amount / sell_amount if sell_amount else np.nan
    threshold = float(frame["amount"].quantile(float(rules["large_trade_quantile"])))
    large = frame.loc[frame["amount"] >= threshold]
    large_buy = float(large.loc[large["side"] == "buy", "amount"].sum())
    large_sell = float(large.loc[large["side"] == "sell", "amount"].sum())
    large_net = large_buy - large_sell
    large_net_ratio = large_net / total_amount if total_amount else np.nan
    volume_shares = float(frame["volume_lots"].sum()) * 100.0
    vwap = total_amount / volume_shares if volume_shares else np.nan
    close = float(daily_row["close"])
    close_vs_vwap = close / vwap - 1 if vwap else np.nan
    tail_start = time.fromisoformat(str(rules["tail_start"]))
    tail = frame.loc[frame["trade_time"].map(lambda value: value >= tail_start)]
    tail_buy = float(tail.loc[tail["side"] == "buy", "amount"].sum())
    tail_sell = float(tail.loc[tail["side"] == "sell", "amount"].sum())
    tail_net = tail_buy - tail_sell

    strong = float(rules["strong_net_ratio"])
    normal = float(rules["net_ratio"])
    flow_state = "balanced"
    if large_net_ratio >= normal and close_vs_vwap <= -0.01:
        flow_state = "buying_without_price_response"
    elif large_net_ratio <= -normal and close_vs_vwap >= 0.01:
        flow_state = "selling_absorbed"
    elif net_ratio >= strong and close_vs_vwap > 0:
        flow_state = "strong_inflow"
    elif net_ratio <= -strong and close_vs_vwap < 0:
        flow_state = "strong_outflow"
    elif net_ratio >= normal:
        flow_state = "inflow"
    elif net_ratio <= -normal:
        flow_state = "outflow"

    minimum_coverage = min(coverage.values())
    if minimum_coverage >= float(rules["high_confidence_coverage"]):
        confidence = "high"
    elif minimum_coverage >= float(rules["medium_confidence_coverage"]):
        confidence = "medium"
    else:
        confidence = "low"
    evidence = (
        f"主动净额占比={net_ratio:.2%}; "
        f"大额成交阈值={threshold:,.0f}元; "
        f"大额买卖净额={large_net:,.0f}元({large_net_ratio:.2%}); "
        f"收盘相对VWAP={close_vs_vwap:.2%}; "
        f"尾盘主动净额={tail_net:,.0f}元"
    )
    result = pd.DataFrame([{
        "code": str(daily_row["code"]),
        "trade_date": pd.to_datetime(daily_row["trade_date"]).date(),
        "tick_count": len(frame),
        "total_amount": total_amount,
        "buy_amount": buy_amount,
        "sell_amount": sell_amount,
        "neutral_amount": neutral_amount,
        "net_active_amount": net_active,
        "net_active_ratio": net_ratio,
        "buy_sell_ratio": buy_sell_ratio,
        "large_trade_threshold": threshold,
        "large_trade_count": len(large),
        "large_buy_amount": large_buy,
        "large_sell_amount": large_sell,
        "large_net_amount": large_net,
        "large_net_ratio": large_net_ratio,
        "vwap": vwap,
        "close_vs_vwap": close_vs_vwap,
        "tail_net_amount": tail_net,
        "amount_coverage": coverage["amount_coverage"],
        "volume_coverage": coverage["volume_coverage"],
        "flow_state": flow_state,
        "confidence": confidence,
        "evidence": evidence,
        "calculated_at": datetime.now(),
    }])
    return result.replace([np.inf, -np.inf], np.nan)
