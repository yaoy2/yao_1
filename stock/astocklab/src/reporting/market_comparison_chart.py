from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go


RETURN_MODE = "累计收益率（%）"
TREND_MODE = "归一化走势（首日=100）"
COMPARISON_MODES = [RETURN_MODE, TREND_MODE]


def calculate_comparison_values(close: pd.Series, mode: str) -> pd.Series:
    """Convert closing prices into one transparent comparison scale."""
    values = pd.to_numeric(close, errors="coerce")
    valid = values.dropna()
    result = pd.Series(index=values.index, dtype="float64")
    if valid.empty or float(valid.iloc[0]) <= 0:
        return result

    first_close = float(valid.iloc[0])
    if mode == RETURN_MODE:
        return (values / first_close - 1.0) * 100.0
    if mode == TREND_MODE:
        return values / first_close * 100.0
    raise ValueError(f"不支持的市场对比口径: {mode}")


def make_market_comparison_figure(
    series: Iterable[tuple[str, pd.DataFrame, float]],
    mode: str,
    *,
    trading_days: int = 120,
) -> go.Figure:
    """Overlay stock and benchmark series using the selected scale."""
    figure = go.Figure()
    suffix = "%" if mode == RETURN_MODE else ""
    for name, frame, width in series:
        if frame.empty or not {"trade_date", "close"}.issubset(frame.columns):
            continue
        cleaned = frame[["trade_date", "close"]].copy()
        cleaned["trade_date"] = pd.to_datetime(cleaned["trade_date"], errors="coerce")
        cleaned["close"] = pd.to_numeric(cleaned["close"], errors="coerce")
        cleaned = (
            cleaned.dropna(subset=["trade_date", "close"])
            .sort_values("trade_date")
            .drop_duplicates("trade_date", keep="last")
            .tail(trading_days)
        )
        if cleaned.empty:
            continue
        cleaned["comparison_value"] = calculate_comparison_values(
            cleaned["close"], mode
        )
        figure.add_trace(go.Scatter(
            x=cleaned["trade_date"],
            y=cleaned["comparison_value"],
            name=name,
            mode="lines",
            line={"width": width},
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>%{y:.2f}" + suffix
                + "<extra>%{fullData.name}</extra>"
            ),
        ))

    if mode == RETURN_MODE:
        title = f"最近{trading_days}个交易日累计收益率对比"
        yaxis_title = "区间累计收益率（%）"
        baseline = 0
    elif mode == TREND_MODE:
        title = f"最近{trading_days}个交易日归一化走势"
        yaxis_title = "相对指数（首日=100）"
        baseline = 100
    else:
        raise ValueError(f"不支持的市场对比口径: {mode}")

    figure.add_hline(
        y=baseline,
        line_width=1,
        line_dash="dot",
        line_color="#8A94A6",
    )
    figure.update_layout(
        title=title,
        height=480,
        hovermode="x unified",
        yaxis_title=yaxis_title,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    return figure
