from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ResearchPoolConfig:
    """Rules for the current, quality-first research universe."""

    minimum_listing_history_days: int
    minimum_ranking_history_days: int
    minimum_backtest_history_days: int
    recent_amount_window: int
    minimum_recent_amount_days: int
    minimum_average_amount: float
    minimum_valid_ohlc_ratio: float
    max_stale_trading_days: int
    target_pool_size: int
    excluded_name_tokens: tuple[str, ...]

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "ResearchPoolConfig":
        values = settings["prediction"]["research_pool"]
        return cls(
            minimum_listing_history_days=int(
                values["minimum_listing_history_days"]
            ),
            minimum_ranking_history_days=int(
                values["minimum_ranking_history_days"]
            ),
            minimum_backtest_history_days=int(
                values["minimum_backtest_history_days"]
            ),
            recent_amount_window=int(values["recent_amount_window"]),
            minimum_recent_amount_days=int(
                values["minimum_recent_amount_days"]
            ),
            minimum_average_amount=float(values["minimum_average_amount"]),
            minimum_valid_ohlc_ratio=float(
                values["minimum_valid_ohlc_ratio"]
            ),
            max_stale_trading_days=int(
                values["max_stale_trading_days"]
            ),
            target_pool_size=int(values["target_pool_size"]),
            excluded_name_tokens=tuple(
                str(value).upper()
                for value in values["excluded_name_tokens"]
            ),
        )

    def validate(self) -> None:
        if self.minimum_listing_history_days < 60:
            raise ValueError("研究池最低上市历史不能少于60个交易日。")
        if (
            self.minimum_ranking_history_days
            < self.minimum_listing_history_days
        ):
            raise ValueError("排名历史要求不能低于上市历史要求。")
        if (
            self.minimum_backtest_history_days
            < self.minimum_ranking_history_days
        ):
            raise ValueError("回测历史要求不能低于排名历史要求。")
        if self.recent_amount_window < 5:
            raise ValueError("成交额观察窗口至少为5个交易日。")
        if not 0 < self.minimum_valid_ohlc_ratio <= 1:
            raise ValueError("OHLC有效率阈值必须位于0到1之间。")
        if self.target_pool_size < 10:
            raise ValueError("研究池目标规模不能少于10只。")


def _normalize_memberships(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "node_id", "snapshot_date", "stock_code", "stock_name", "rank"
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"AI成分快照缺少字段: {sorted(missing)}")
    result = frame[list(required)].copy()
    result["stock_code"] = (
        result["stock_code"].astype(str).str.zfill(6)
    )
    result["stock_name"] = result["stock_name"].astype(str).str.strip()
    result["node_id"] = result["node_id"].astype(str)
    result["snapshot_date"] = pd.to_datetime(
        result["snapshot_date"], errors="coerce"
    ).dt.normalize()
    result["rank"] = pd.to_numeric(result["rank"], errors="coerce")
    return result.dropna(
        subset=["node_id", "snapshot_date", "stock_code", "stock_name"]
    )


def _normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "code", "trade_date", "adjust_type",
        "open", "high", "low", "close", "amount",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"研究池日线缺少字段: {sorted(missing)}")
    result = frame.copy()
    result = result.loc[result["adjust_type"].astype(str) == "qfq"]
    result["code"] = result["code"].astype(str).str.zfill(6)
    result["trade_date"] = pd.to_datetime(
        result["trade_date"], errors="coerce"
    ).dt.normalize()
    for column in ["open", "high", "low", "close", "amount"]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = (
        result.dropna(subset=["code", "trade_date"])
        .drop_duplicates(["code", "trade_date"], keep="last")
        .sort_values(["code", "trade_date"])
        .reset_index(drop=True)
    )
    return result


def _valid_ohlc(frame: pd.DataFrame) -> pd.Series:
    prices = frame[["open", "high", "low", "close"]]
    finite = pd.Series(
        np.isfinite(prices.to_numpy(dtype=float)).all(axis=1),
        index=frame.index,
    )
    positive = (prices > 0).all(axis=1)
    coherent = (
        (frame["high"] >= frame[["open", "close"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close"]].min(axis=1))
        & (frame["high"] >= frame["low"])
    )
    return finite & positive & coherent


def _name_is_excluded(
    name: str,
    tokens: tuple[str, ...],
) -> bool:
    normalized = str(name).upper().replace(" ", "")
    return any(token in normalized for token in tokens)


def _rejection_reasons(row: pd.Series) -> list[str]:
    reasons = []
    if bool(row["name_excluded"]):
        reasons.append("名称含ST或退市标记")
    if not bool(row["listing_history_ok"]):
        reasons.append("上市历史不足")
    if not bool(row["ranking_history_ok"]):
        reasons.append("排名历史不足")
    if not bool(row["freshness_ok"]):
        reasons.append("行情未更新到共同交易日")
    if not bool(row["data_quality_ok"]):
        reasons.append("OHLC数据质量不足")
    if not bool(row["liquidity_ok"]):
        reasons.append("近期成交额不足或缺失")
    return reasons


def build_research_pool_audit(
    memberships: pd.DataFrame,
    daily_bars: pd.DataFrame,
    config: ResearchPoolConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Audit the latest AI memberships without using future outcomes."""
    config.validate()
    members = _normalize_memberships(memberships)
    bars = _normalize_bars(daily_bars)
    if members.empty:
        raise ValueError("AI产业链当前没有可审计的成分股。")

    grouped_members = (
        members.groupby("stock_code", as_index=False)
        .agg(
            stock_name=("stock_name", "last"),
            snapshot_date=("snapshot_date", "max"),
            node_count=("node_id", "nunique"),
            node_ids=(
                "node_id",
                lambda values: ",".join(sorted(set(values))),
            ),
            best_source_rank=("rank", "min"),
        )
    )
    member_codes = set(grouped_members["stock_code"])
    bars = bars.loc[bars["code"].isin(member_codes)].copy()
    available_dates = sorted(bars["trade_date"].dropna().unique())
    reference_date = (
        pd.Timestamp(available_dates[-1])
        if available_dates
        else pd.NaT
    )

    bar_rows: list[dict[str, Any]] = []
    for code, stock_bars in bars.groupby("code", sort=False):
        stock_bars = stock_bars.sort_values("trade_date")
        recent = stock_bars.tail(config.recent_amount_window)
        valid_amount = recent["amount"].where(recent["amount"] >= 0).dropna()
        last_date = pd.Timestamp(stock_bars["trade_date"].max())
        trading_day_lag = (
            sum(pd.Timestamp(value) > last_date for value in available_dates)
            if available_dates
            else None
        )
        bar_rows.append({
            "stock_code": code,
            "history_rows": int(len(stock_bars)),
            "first_trade_date": pd.Timestamp(
                stock_bars["trade_date"].min()
            ),
            "last_trade_date": last_date,
            "trading_day_lag": trading_day_lag,
            "valid_ohlc_ratio": float(_valid_ohlc(stock_bars).mean()),
            "recent_amount_days": int(len(valid_amount)),
            "average_amount_recent": (
                float(valid_amount.mean()) if not valid_amount.empty else np.nan
            ),
        })
    bar_summary = pd.DataFrame(bar_rows)
    result = grouped_members.merge(
        bar_summary,
        on="stock_code",
        how="left",
        validate="one_to_one",
    )
    result["history_rows"] = result["history_rows"].fillna(0).astype(int)
    result["recent_amount_days"] = (
        result["recent_amount_days"].fillna(0).astype(int)
    )
    result["name_excluded"] = result["stock_name"].map(
        lambda value: _name_is_excluded(
            value, config.excluded_name_tokens
        )
    )
    result["listing_history_ok"] = (
        result["history_rows"] >= config.minimum_listing_history_days
    )
    result["ranking_history_ok"] = (
        result["history_rows"] >= config.minimum_ranking_history_days
    )
    result["backtest_history_ok"] = (
        result["history_rows"] >= config.minimum_backtest_history_days
    )
    result["freshness_ok"] = (
        result["trading_day_lag"].notna()
        & (
            result["trading_day_lag"]
            <= config.max_stale_trading_days
        )
    )
    result["data_quality_ok"] = (
        result["valid_ohlc_ratio"].notna()
        & (
            result["valid_ohlc_ratio"]
            >= config.minimum_valid_ohlc_ratio
        )
    )
    result["liquidity_ok"] = (
        result["recent_amount_days"]
        >= config.minimum_recent_amount_days
    ) & (
        result["average_amount_recent"]
        >= config.minimum_average_amount
    )
    result["ranking_ready"] = (
        ~result["name_excluded"]
        & result["listing_history_ok"]
        & result["ranking_history_ok"]
        & result["freshness_ok"]
        & result["data_quality_ok"]
        & result["liquidity_ok"]
    )
    result["backtest_ready"] = (
        result["ranking_ready"] & result["backtest_history_ok"]
    )
    reason_lists = result.apply(_rejection_reasons, axis=1)
    result["rejection_reasons"] = reason_lists.map("；".join)

    eligible = result.loc[result["ranking_ready"]].sort_values(
        [
            "backtest_ready", "node_count", "average_amount_recent",
            "history_rows", "stock_code",
        ],
        ascending=[False, False, False, False, True],
        kind="stable",
    )
    selected_codes = set(
        eligible.head(config.target_pool_size)["stock_code"]
    )
    pilot_ranks = {
        code: index + 1
        for index, code in enumerate(
            eligible.head(config.target_pool_size)["stock_code"]
        )
    }
    result["selected_for_pilot"] = result["stock_code"].isin(
        selected_codes
    )
    result["pilot_rank"] = result["stock_code"].map(pilot_ranks).astype(
        "Int64"
    )
    result = result.sort_values(
        ["selected_for_pilot", "pilot_rank", "stock_code"],
        ascending=[False, True, True],
        kind="stable",
    ).reset_index(drop=True)

    reason_counts = Counter(
        reason
        for reasons in reason_lists
        for reason in reasons
    )
    summary = {
        "reference_trade_date": (
            reference_date.date().isoformat()
            if pd.notna(reference_date)
            else None
        ),
        "latest_snapshot_date": (
            members["snapshot_date"].max().date().isoformat()
        ),
        "membership_rows": int(len(members)),
        "distinct_stock_count": int(len(result)),
        "stocks_with_qfq_bars": int((result["history_rows"] > 0).sum()),
        "ranking_ready_count": int(result["ranking_ready"].sum()),
        "backtest_ready_count": int(result["backtest_ready"].sum()),
        "selected_for_pilot_count": int(
            result["selected_for_pilot"].sum()
        ),
        "target_pool_size": config.target_pool_size,
        "minimum_average_amount": config.minimum_average_amount,
        "minimum_ranking_history_days": (
            config.minimum_ranking_history_days
        ),
        "minimum_backtest_history_days": (
            config.minimum_backtest_history_days
        ),
        "rejection_reason_counts": dict(reason_counts),
    }
    return result, summary
