from __future__ import annotations

from typing import Any

import plotly.graph_objects as go


A_SHARE_UP = "#d32f2f"
A_SHARE_DOWN = "#16865b"
NEUTRAL = "#5f6670"


def _path_values(
    artifact: dict[str, Any],
) -> tuple[list[str], list[float], list[float], list[float]]:
    forecast = artifact["forecast_path"]
    x_values = ["当前", *[f"T+{item['day']}" for item in forecast]]
    median = [0.0, *[
        float(item["median_return"]) * 100.0 for item in forecast
    ]]
    lower = [0.0, *[
        float(item["lower_return"]) * 100.0 for item in forecast
    ]]
    upper = [0.0, *[
        float(item["upper_return"]) * 100.0 for item in forecast
    ]]
    return x_values, median, lower, upper


def make_prediction_figure(
    artifact: dict[str, Any],
    history_count: int = 10,
) -> go.Figure:
    """Join real historical candles with five probabilistic forecast candles."""
    history = artifact["recent_history"][-history_count:]
    forecast = artifact.get("forecast_candles", [])
    if not history or not forecast:
        raise ValueError(
            "预测文件缺少K线字段，请重新运行 run_predictions.bat。"
        )
    required = {"open", "high", "low", "close"}
    if any(not required.issubset(item) for item in [*history, *forecast]):
        raise ValueError(
            "预测文件还是旧格式，请重新运行 run_predictions.bat。"
        )
    history_x = [item["trade_date"] for item in history]
    forecast_x = [
        str(item.get("label", f"T+{item['day']}"))
        for item in forecast
    ]
    figure = go.Figure()
    figure.add_trace(go.Candlestick(
        x=history_x,
        open=[item["open"] for item in history],
        high=[item["high"] for item in history],
        low=[item["low"] for item in history],
        close=[item["close"] for item in history],
        name="真实历史K线",
        increasing={
            "line": {"color": A_SHARE_UP},
            "fillcolor": A_SHARE_UP,
        },
        decreasing={
            "line": {"color": A_SHARE_DOWN},
            "fillcolor": A_SHARE_DOWN,
        },
    ))
    figure.add_trace(go.Candlestick(
        x=forecast_x,
        open=[item["open"] for item in forecast],
        high=[item["high"] for item in forecast],
        low=[item["low"] for item in forecast],
        close=[item["close"] for item in forecast],
        name="未来T+5概率合成K线",
        opacity=0.68,
        increasing={
            "line": {"color": A_SHARE_UP, "width": 2},
            "fillcolor": A_SHARE_UP,
        },
        decreasing={
            "line": {"color": A_SHARE_DOWN, "width": 2},
            "fillcolor": A_SHARE_DOWN,
        },
    ))
    category_order = [*history_x, *forecast_x]
    figure.add_vline(
        x=history_x[-1],
        line_color="#6b7280",
        line_width=1.5,
        line_dash="dash",
        annotation_text="左侧真实 / 右侧预测",
        annotation_position="top",
    )
    figure.update_layout(
        title=(
            f"前序{len(history)}根真实K线 + "
            f"未来{len(forecast)}根概率合成K线"
        ),
        height=560,
        hovermode="x unified",
        showlegend=False,
        xaxis={
            "type": "category",
            "categoryorder": "array",
            "categoryarray": category_order,
            "rangeslider": {"visible": False},
        },
        yaxis={
            "title": "前复权价格",
            "fixedrange": False,
        },
        margin={"l": 20, "r": 20, "t": 70, "b": 20},
    )
    return figure


def make_prediction_range_figure(
    artifact: dict[str, Any],
) -> go.Figure:
    """Show the calibrated uncertainty separately from the focused path."""
    x_values, median, lower, upper = _path_values(artifact)
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=x_values,
        y=upper,
        name="校准区间上界",
        mode="lines",
        line={"color": "rgba(84,110,122,0.35)", "width": 1},
        hovertemplate="%{x}<br>上界：%{y:+.2f}%<extra></extra>",
    ))
    figure.add_trace(go.Scatter(
        x=x_values,
        y=lower,
        name="校准不确定区间",
        mode="lines",
        line={"color": "rgba(84,110,122,0.35)", "width": 1},
        fill="tonexty",
        fillcolor="rgba(84,110,122,0.15)",
        hovertemplate="%{x}<br>下界：%{y:+.2f}%<extra></extra>",
    ))
    figure.add_trace(go.Scatter(
        x=x_values,
        y=median,
        name="中位预测",
        mode="lines+markers",
        line={"color": "#455a64", "width": 2, "dash": "dash"},
        hovertemplate="%{x}<br>中位：%{y:+.2f}%<extra></extra>",
    ))
    figure.add_hline(
        y=0.0,
        line_color="#8c939d",
        line_width=1,
        line_dash="dot",
    )
    figure.update_layout(
        title="校准不确定区间（宽幅风险视图）",
        height=400,
        hovermode="x unified",
        xaxis={"type": "category"},
        yaxis={
            "title": "较当前累计涨跌",
            "ticksuffix": "%",
            "zeroline": False,
        },
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        legend={"orientation": "h", "y": 1.12},
    )
    return figure
