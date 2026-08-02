from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def make_kline_figure(
    frame: pd.DataFrame,
    title: str,
    count: int = 120,
    height: int = 590,
) -> go.Figure:
    chart = frame.sort_values("trade_date").tail(count).copy()
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.76, 0.24],
    )
    figure.add_trace(go.Candlestick(
        x=chart["trade_date"],
        open=chart["open"],
        high=chart["high"],
        low=chart["low"],
        close=chart["close"],
        name=title,
        increasing={
            "line": {"color": "#d32f2f"},
            "fillcolor": "#d32f2f",
        },
        decreasing={
            "line": {"color": "#16865b"},
            "fillcolor": "#16865b",
        },
    ), row=1, col=1)
    if "volume" in chart:
        colors = [
            "#ef5350" if close >= open_ else "#26a69a"
            for close, open_ in zip(
                chart["close"], chart["open"], strict=True
            )
        ]
        figure.add_trace(go.Bar(
            x=chart["trade_date"],
            y=chart["volume"],
            name="成交量",
            marker_color=colors,
        ), row=2, col=1)
    figure.update_layout(
        title=title,
        height=height,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        showlegend=False,
    )
    return figure


def make_sector_comparison(
    frames: dict[str, pd.DataFrame],
    count: int = 120,
) -> go.Figure:
    figure = go.Figure()
    for name, source in frames.items():
        frame = source.sort_values("trade_date").tail(count).copy()
        if frame.empty:
            continue
        frame["normalized"] = (
            frame["close"] / frame["close"].iloc[0] * 100.0
        )
        figure.add_trace(go.Scatter(
            x=frame["trade_date"],
            y=frame["normalized"],
            name=name,
            mode="lines",
            line={"width": 2},
        ))
    figure.update_layout(
        title=f"最近{count}个交易日板块走势对比（起点=100）",
        height=460,
        hovermode="x unified",
        yaxis_title="归一化点位",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        legend={"orientation": "h", "y": 1.12},
    )
    return figure
