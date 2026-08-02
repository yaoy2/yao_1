from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from src.features.intraday_features import reconcile_tick_with_daily
from src.storage.database import Database
from src.utils.config import AIChainConfig, WatchlistConfig


def validate_ohlc_frame(frame: pd.DataFrame, label: str) -> tuple[list[str], list[str]]:
    """Return severe errors and warnings for one OHLC DataFrame."""
    errors: list[str] = []
    warnings: list[str] = []
    required = ["trade_date", "open", "high", "low", "close"]
    missing_columns = set(required).difference(frame.columns)
    if missing_columns:
        return [f"{label}: 缺少字段 {sorted(missing_columns)}"], warnings
    if frame.empty:
        return [f"{label}: 数据为空"], warnings
    if frame[required].isna().any().any():
        rows = int(frame[required].isna().any(axis=1).sum())
        errors.append(f"{label}: {rows} 行日期或 OHLC 为空")
    if (frame["high"] < frame["low"]).any():
        errors.append(f"{label}: 存在 high 小于 low")
    outside = (
        (frame["open"] > frame["high"]) | (frame["open"] < frame["low"]) |
        (frame["close"] > frame["high"]) | (frame["close"] < frame["low"])
    )
    if outside.any():
        errors.append(f"{label}: {int(outside.sum())} 行 open/close 超出 high/low")
    if "volume" in frame and (frame["volume"].dropna() < 0).any():
        errors.append(f"{label}: 成交量存在负数")
    if "amount" in frame and (frame["amount"].dropna() < 0).any():
        errors.append(f"{label}: 成交额存在负数")
    if frame.duplicated(["trade_date"]).any():
        errors.append(f"{label}: 日期重复 {int(frame.duplicated(['trade_date']).sum())} 行")
    dates = pd.to_datetime(frame["trade_date"], errors="coerce")
    if not dates.is_monotonic_increasing:
        warnings.append(f"{label}: 日期未按升序排列")
    return errors, warnings


def validate_database(
    database: Database,
    watchlist: WatchlistConfig,
    ai_chain: AIChainConfig | None = None,
) -> dict[str, Any]:
    """Run integrity, coverage, freshness, and ingestion checks."""
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}
    for stock in [item for item in watchlist.stocks if item.enabled]:
        raw = database.get_stock_bars(stock.code, "raw")
        qfq = database.get_stock_bars(stock.code, "qfq")
        features = database.get_features(stock.code)
        for label, frame in [
            (f"{stock.code}-raw", raw),
            (f"{stock.code}-qfq", qfq),
        ]:
            frame_errors, frame_warnings = validate_ohlc_frame(frame, label)
            errors.extend(frame_errors)
            warnings.extend(frame_warnings)
        metrics[stock.code] = {
            "raw_count": len(raw),
            "qfq_count": len(qfq),
            "feature_count": len(features),
        }
        difference = abs(len(raw) - len(qfq))
        tolerance = max(2, int(max(len(raw), len(qfq)) * 0.02))
        if difference > tolerance:
            warnings.append(f"{stock.code}: 未复权与前复权记录数相差 {difference}，超过容许值 {tolerance}")
        benchmark_metrics: dict[str, Any] = {}
        for benchmark_config in watchlist.enabled_benchmarks_for(stock):
            benchmark = database.get_benchmark_bars(benchmark_config.code)
            frame_errors, frame_warnings = validate_ohlc_frame(
                benchmark, f"{benchmark_config.code}-benchmark"
            )
            errors.extend(frame_errors)
            warnings.extend(frame_warnings)
            if not qfq.empty and not benchmark.empty:
                qfq_dates = set(pd.to_datetime(qfq["trade_date"]).dt.date)
                benchmark_dates = set(pd.to_datetime(benchmark["trade_date"]).dt.date)
                covered = len(qfq_dates & benchmark_dates) / len(qfq_dates)
                linkage = database.get_linkage_features(
                    stock.code, benchmark_config.code
                )
                benchmark_metrics[benchmark_config.code] = {
                    "count": len(benchmark),
                    "coverage": covered,
                    "linkage_count": len(linkage),
                }
                if covered < 0.8:
                    errors.append(
                        f"{stock.code}: 基准 {benchmark_config.code} 仅覆盖 "
                        f"{covered:.1%} 的股票交易日"
                    )
                elif covered < 0.95:
                    warnings.append(
                        f"{stock.code}: 基准 {benchmark_config.code} 仅覆盖 "
                        f"{covered:.1%} 的股票交易日"
                    )
        metrics[stock.code]["benchmarks"] = benchmark_metrics
        if not raw.empty:
            latest = pd.to_datetime(raw["trade_date"]).max().date()
            age = (date.today() - latest).days
            metrics[stock.code]["latest_trade_date"] = latest.isoformat()
            if age > 20:
                errors.append(f"{stock.code}: 最新交易日距今 {age} 天，明显过旧")
            elif age > 7:
                warnings.append(f"{stock.code}: 最新交易日距今 {age} 天，请确认是否停牌或更新失败")
        if features.empty:
            warnings.append(f"{stock.code}: 特征表为空")
        else:
            numeric = features.select_dtypes(include=[np.number])
            if np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any():
                errors.append(f"{stock.code}: 特征表存在 inf")
        ticks = database.get_tick_trades(stock.code)
        minutes = database.get_minute_bars(stock.code)
        money_flow = database.get_money_flow(stock.code)
        metrics[stock.code]["tick_count"] = len(ticks)
        metrics[stock.code]["minute_count"] = len(minutes)
        metrics[stock.code]["money_flow_days"] = len(money_flow)
        if ticks.empty:
            warnings.append(f"{stock.code}: 尚无逐笔成交数据")
        elif not raw.empty:
            latest_tick_date = pd.to_datetime(ticks["trade_date"]).max().date()
            daily_match = raw.loc[
                pd.to_datetime(raw["trade_date"]).dt.date == latest_tick_date
            ]
            if daily_match.empty:
                errors.append(f"{stock.code}: 逐笔成交缺少对应日线 {latest_tick_date}")
            else:
                try:
                    coverage = reconcile_tick_with_daily(
                        ticks.loc[
                            pd.to_datetime(ticks["trade_date"]).dt.date == latest_tick_date
                        ],
                        daily_match.iloc[-1],
                    )
                    metrics[stock.code]["tick_reconciliation"] = coverage
                except ValueError as exc:
                    errors.append(f"{stock.code}: {exc}")
        if not ticks.empty and money_flow.empty:
            warnings.append(f"{stock.code}: 已有逐笔数据但资金行为特征为空")

    if ai_chain is not None:
        ai_metrics: dict[str, Any] = {"nodes": {}}
        stored_nodes = database.get_ai_chain_nodes()
        expected_nodes = [node for node in ai_chain.nodes if node.enabled]
        if len(stored_nodes) != len(expected_nodes):
            errors.append(
                f"AI产业链节点入库 {len(stored_nodes)}/{len(expected_nodes)}"
            )
        classification_columns = [
            "industry", "subindustry", "field", "direction"
        ]
        if (
            not stored_nodes.empty
            and not stored_nodes[classification_columns].notna().all().all()
        ):
            errors.append("AI产业链存在未完成的分类层级")
        universe_codes: set[str] = set()
        quote_columns = [
            "current_price", "today_high", "today_low", "pct_change",
            "amplitude", "volume", "volume_ratio", "total_market_cap",
            "float_market_cap",
        ]
        for node in expected_nodes:
            daily = database.get_ai_sector_daily(node.node_id)
            minute = database.get_ai_sector_minute(node.node_id)
            members = database.get_latest_ai_memberships(node.node_id)
            frame_errors, frame_warnings = validate_ohlc_frame(
                daily, f"AI板块-{node.node_id}"
            )
            errors.extend(frame_errors)
            warnings.extend(frame_warnings)
            if members.empty:
                warnings.append(f"AI板块 {node.name}: 代表性成分为空")
                quote_complete = 0
            else:
                universe_codes.update(members["stock_code"].astype(str))
                quote_complete = int(
                    members[quote_columns].notna().all(axis=1).sum()
                )
                if quote_complete < len(members):
                    warnings.append(
                        f"AI板块 {node.name}: 完整实时行情 "
                        f"{quote_complete}/{len(members)}"
                    )
            latest_daily = (
                pd.to_datetime(daily["trade_date"]).max().date()
                if not daily.empty else None
            )
            latest_minute = (
                pd.to_datetime(minute["trade_datetime"]).max()
                if not minute.empty else None
            )
            ai_metrics["nodes"][node.node_id] = {
                "daily_count": len(daily),
                "minute_count": len(minute),
                "member_count": len(members),
                "quote_complete_count": quote_complete,
                "latest_daily": (
                    latest_daily.isoformat() if latest_daily else None
                ),
                "latest_minute": (
                    str(latest_minute) if latest_minute is not None else None
                ),
            }
            if latest_daily is not None and (date.today() - latest_daily).days > 7:
                warnings.append(
                    f"AI板块 {node.name}: 最新日线为 {latest_daily}"
                )
        profiles = database.get_ai_profile_codes()
        qfq_codes = set(
            database.read_table(
                "daily_bars", "adjust_type = 'qfq'"
            )["code"].astype(str)
        )
        minute_codes = set(
            database.read_table("minute_bars")["code"].astype(str)
        )
        universe_count = len(universe_codes)
        ai_metrics["coverage"] = {
            "unique_stocks": universe_count,
            "business_profiles": len(universe_codes & profiles),
            "daily_bars": len(universe_codes & qfq_codes),
            "minute_bars": len(universe_codes & minute_codes),
        }
        metrics["ai_chain"] = ai_metrics

    latest_run = database.latest_ingestion()
    if latest_run.empty:
        warnings.append("没有数据抓取运行记录")
    else:
        run = latest_run.iloc[0]
        metrics["latest_ingestion"] = {
            "job_name": run["job_name"],
            "status": run["status"],
            "started_at": str(run["started_at"]),
            "finished_at": str(run["finished_at"]),
        }
        if run["status"] == "failed":
            errors.append(f"最近一次抓取失败: {run['error_message']}")
    status = "error" if errors else ("warning" if warnings else "ok")
    return {"status": status, "errors": errors, "warnings": warnings, "metrics": metrics}
