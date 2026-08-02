from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def add_a_share_session_minute(
    frame: pd.DataFrame,
    datetime_column: str = "trade_datetime",
) -> pd.DataFrame:
    """Map A-share morning and afternoon sessions to one continuous x-axis."""
    output = frame.copy()
    timestamps = pd.to_datetime(output[datetime_column], errors="coerce")
    minute_of_day = timestamps.dt.hour * 60 + timestamps.dt.minute
    in_session = (
        ((minute_of_day >= 9 * 60 + 30) & (minute_of_day <= 11 * 60 + 30))
        | ((minute_of_day >= 13 * 60) & (minute_of_day <= 15 * 60))
    )
    output = output.loc[in_session].copy()
    minute_of_day = minute_of_day.loc[in_session]
    output["session_minute"] = np.where(
        minute_of_day <= 11 * 60 + 30,
        minute_of_day - (9 * 60 + 30),
        120 + minute_of_day - 13 * 60,
    )
    return output


def symmetric_pct_range(
    frames: list[pd.DataFrame],
    minimum_bound: float = 1.0,
) -> tuple[float, float]:
    """Return a zero-centered percent range covering all supplied frames."""
    values: list[float] = []
    for frame in frames:
        if frame.empty or "intraday_pct" not in frame:
            continue
        numeric = pd.to_numeric(frame["intraday_pct"], errors="coerce")
        values.extend(numeric.replace([np.inf, -np.inf], np.nan).dropna())
    max_abs = max((abs(value) for value in values), default=0.0)
    bound = float(np.ceil(max(max_abs * 1.08, minimum_bound)))
    return -bound, bound


def _a_share_tick_text(value: float, text: str) -> str:
    color = (
        "#d32f2f"
        if value > 1e-9
        else "#16865b" if value < -1e-9 else "#5f6670"
    )
    return f"<span style='color:{color}'>{text}</span>"


def prepare_intraday_comparison(
    frames: dict[str, pd.DataFrame],
) -> tuple[
    date | None,
    dict[str, pd.DataFrame],
    tuple[float, float],
    list[str],
    list[str],
]:
    """Align minute bars to the latest date shared by every requested instrument."""
    missing = [code for code, frame in frames.items() if frame.empty]
    if missing:
        return None, {}, (-1.0, 1.0), missing, []

    date_sets: list[set[date]] = []
    converted: dict[str, pd.DataFrame] = {}
    for code, source in frames.items():
        frame = source.copy()
        frame["trade_datetime"] = pd.to_datetime(
            frame["trade_datetime"], errors="coerce"
        )
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame.dropna(subset=["trade_datetime", "close"])
        frame = frame.loc[frame["close"] > 0].sort_values("trade_datetime")
        converted[code] = frame
        dates = set(frame["trade_datetime"].dt.date)
        if not dates:
            missing.append(code)
        date_sets.append(dates)
    if missing or not date_sets:
        return None, {}, (-1.0, 1.0), sorted(set(missing)), []

    common_dates = set.intersection(*date_sets)
    if not common_dates:
        return None, {}, (-1.0, 1.0), [], []
    comparison_date = max(common_dates)

    prepared: dict[str, pd.DataFrame] = {}
    for code, frame in converted.items():
        day = frame.loc[
            frame["trade_datetime"].dt.date == comparison_date
        ].copy()
        previous = frame.loc[
            frame["trade_datetime"].dt.date < comparison_date
        ]
        baseline = (
            float(previous.iloc[-1]["close"])
            if not previous.empty
            else float(day.iloc[0]["close"])
        )
        day["previous_close"] = baseline
        day["intraday_pct"] = (
            day["close"] / baseline - 1.0
        ) * 100.0
        day["intraday_pct"] = day["intraday_pct"].replace(
            [np.inf, -np.inf], np.nan
        )
        day = add_a_share_session_minute(day)
        day = day.dropna(subset=["intraday_pct"])
        prepared[code] = day

    latest_times = {
        code: frame["trade_datetime"].max()
        for code, frame in prepared.items()
    }
    if not latest_times:
        return None, {}, (-1.0, 1.0), sorted(frames), []
    freshest = max(latest_times.values())
    stale = sorted(
        code
        for code, timestamp in latest_times.items()
        if freshest - timestamp > pd.Timedelta(minutes=2)
    )

    y_range = symmetric_pct_range(list(prepared.values()))
    return (
        comparison_date,
        prepared,
        y_range,
        [],
        stale,
    )


def make_intraday_figure(
    frame: pd.DataFrame,
    name: str,
    y_range: tuple[float, float],
    compact: bool = False,
) -> go.Figure:
    """Create a compact minute chart with raw price in hover details."""
    latest = frame.iloc[-1]
    latest_pct = float(latest["intraday_pct"])
    color = (
        "#d32f2f"
        if latest_pct > 0
        else "#16865b" if latest_pct < 0 else "#5f6670"
    )
    plot_frame = frame.copy().sort_values("trade_datetime")
    previous_close = float(plot_frame.iloc[0]["previous_close"])
    hover_times = plot_frame["trade_datetime"].map(
        lambda value: value.strftime("%H:%M")
    )
    pct_ticks = np.linspace(y_range[0], y_range[1], 5)
    price_range = [
        previous_close * (1.0 + y_range[0] / 100.0),
        previous_close * (1.0 + y_range[1] / 100.0),
    ]
    price_ticks = previous_close * (1.0 + pct_ticks / 100.0)

    figure = go.Figure(go.Scatter(
        x=plot_frame["session_minute"],
        y=plot_frame["close"],
        customdata=np.column_stack([
            plot_frame["intraday_pct"].to_numpy(),
            hover_times.to_numpy(),
        ]),
        mode="lines",
        line={"color": color, "width": 2},
        connectgaps=True,
        hovertemplate=(
            "%{customdata[1]}<br>价格：%{y:.2f}"
            "<br>较昨收：%{customdata[0]:+.2f}%<extra></extra>"
        ),
    ))
    figure.add_trace(go.Scatter(
        x=plot_frame["session_minute"],
        y=plot_frame["intraday_pct"],
        yaxis="y2",
        mode="lines",
        line={"width": 0},
        opacity=0,
        hoverinfo="skip",
        showlegend=False,
    ))
    figure.add_hline(
        y=previous_close,
        line_color="#8c939d",
        line_width=1.2,
    )
    figure.update_layout(
        title={
            "text": (
                f"{name}<br><sup><span style='color:{color}'>"
                f"{float(latest['close']):,.2f} "
                f"({latest_pct:+.2f}%)</span></sup>"
            ),
            "font": {"size": 15},
        },
        height=270,
        showlegend=False,
        hovermode="x",
        margin={"l": 54, "r": 54, "t": 58, "b": 35},
        xaxis={
            "range": [0, 240],
            "tickmode": "array",
            "tickvals": (
                [0, 120, 240]
                if compact else [0, 60, 120, 180, 240]
            ),
            "ticktext": (
                ["09:30", "11:30", "15:00"]
                if compact
                else ["09:30", "10:30", "11:30", "14:00", "15:00"]
            ),
            "tickfont": {"size": 9 if compact else 11},
            "fixedrange": True,
            "showgrid": False,
        },
        yaxis={
            "title": {"text": "价格", "font": {"size": 10}},
            "range": price_range,
            "tickmode": "array",
            "tickvals": price_ticks.tolist(),
            "ticktext": [
                _a_share_tick_text(pct, f"{price:,.2f}")
                for pct, price in zip(pct_ticks, price_ticks, strict=True)
            ],
            "tickfont": {"size": 9 if compact else 10},
            "showticklabels": True,
            "fixedrange": True,
            "zeroline": False,
            "gridcolor": "#eeeeee",
        },
        yaxis2={
            "title": {"text": "涨跌幅", "font": {"size": 10}},
            "overlaying": "y",
            "side": "right",
            "range": list(y_range),
            "tickmode": "array",
            "tickvals": pct_ticks.tolist(),
            "ticktext": [
                _a_share_tick_text(pct, f"{pct:+.2f}%")
                for pct in pct_ticks
            ],
            "tickfont": {"size": 9 if compact else 10},
            "showticklabels": True,
            "fixedrange": True,
            "zeroline": False,
            "showgrid": False,
        },
    )
    return figure


def make_money_flow_intraday_figure(
    frame: pd.DataFrame,
    previous_close: float,
    vwap: float,
    title: str,
) -> go.Figure:
    """Create a continuous-session price and amount chart for money-flow review."""
    plot_frame = add_a_share_session_minute(frame).sort_values(
        "trade_datetime"
    )
    plot_frame["intraday_pct"] = (
        plot_frame["close"] / previous_close - 1.0
    ) * 100.0
    pct_range = symmetric_pct_range([plot_frame])
    pct_ticks = np.linspace(pct_range[0], pct_range[1], 5)
    price_range = [
        previous_close * (1.0 + pct_range[0] / 100.0),
        previous_close * (1.0 + pct_range[1] / 100.0),
    ]
    price_ticks = previous_close * (1.0 + pct_ticks / 100.0)
    latest_pct = float(plot_frame.iloc[-1]["intraday_pct"])
    line_color = (
        "#d32f2f"
        if latest_pct > 0
        else "#16865b" if latest_pct < 0 else "#5f6670"
    )
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.05,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )
    figure.add_trace(
        go.Scatter(
            x=plot_frame["session_minute"],
            y=plot_frame["close"],
            customdata=plot_frame["trade_datetime"].dt.strftime(
                "%H:%M"
            ).to_numpy(),
            name="1分钟收盘价",
            line={"width": 1.5, "color": line_color},
            hovertemplate=(
                "%{customdata}<br>价格：%{y:.2f}<extra></extra>"
            ),
            connectgaps=True,
        ),
        row=1,
        col=1,
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=plot_frame["session_minute"],
            y=plot_frame["intraday_pct"],
            mode="lines",
            line={"width": 0},
            opacity=0,
            hoverinfo="skip",
            showlegend=False,
        ),
        row=1,
        col=1,
        secondary_y=True,
    )
    figure.add_hline(
        y=float(vwap),
        line_dash="dash",
        line_color="#f4b400",
        annotation_text="当日VWAP",
        row=1,
        col=1,
        secondary_y=False,
    )
    figure.add_trace(
        go.Bar(
            x=plot_frame["session_minute"],
            y=plot_frame["amount"],
            customdata=plot_frame["trade_datetime"].dt.strftime(
                "%H:%M"
            ).to_numpy(),
            name="分钟成交额",
            marker_color="#90a4ae",
            hovertemplate=(
                "%{customdata}<br>成交额：%{y:,.0f}<extra></extra>"
            ),
        ),
        row=2,
        col=1,
    )
    figure.update_xaxes(
        range=[0, 240],
        tickmode="array",
        tickvals=[0, 60, 120, 180, 240],
        ticktext=["09:30", "10:30", "11:30", "14:00", "15:00"],
        fixedrange=True,
        row=2,
        col=1,
    )
    figure.update_yaxes(
        title_text="价格",
        range=price_range,
        tickmode="array",
        tickvals=price_ticks.tolist(),
        ticktext=[
            _a_share_tick_text(pct, f"{price:,.2f}")
            for pct, price in zip(pct_ticks, price_ticks, strict=True)
        ],
        fixedrange=True,
        row=1,
        col=1,
        secondary_y=False,
    )
    figure.update_yaxes(
        title_text="涨跌幅",
        range=list(pct_range),
        tickmode="array",
        tickvals=pct_ticks.tolist(),
        ticktext=[
            _a_share_tick_text(pct, f"{pct:+.2f}%")
            for pct in pct_ticks
        ],
        fixedrange=True,
        row=1,
        col=1,
        secondary_y=True,
    )
    figure.update_xaxes(
        range=[0, 240],
        showticklabels=False,
        fixedrange=True,
        row=1,
        col=1,
    )
    figure.update_layout(
        title=title,
        height=600,
        hovermode="x unified",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    return figure
