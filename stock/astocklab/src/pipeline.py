from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
from loguru import logger

from src.features.intraday_features import reconcile_tick_with_daily
from src.providers.akshare_provider import (
    AkshareProvider,
    drop_incomplete_current_daily_bar,
)
from src.storage.database import Database
from src.utils.config import BenchmarkConfig, StockConfig, load_settings


def _snapshot_path(base: Path, snapshot_date: date, filename: str) -> Path:
    path = base / snapshot_date.isoformat() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_snapshot(
    frame: pd.DataFrame,
    path: Path,
    key_columns: list[str] | None = None,
) -> None:
    """Merge and atomically write a readable non-empty Parquet snapshot."""
    if frame.empty:
        raise ValueError(f"拒绝写入空快照: {path}")
    output = frame.copy()
    if path.exists():
        existing = pd.read_parquet(path)
        if set(existing.columns) == set(output.columns):
            output = pd.concat([existing[output.columns], output], ignore_index=True)
            keys = key_columns or ["code", "trade_date"]
            if key_columns is None and "adjust_type" in output.columns:
                keys.append("adjust_type")
            output = output.drop_duplicates(keys, keep="last")
            sort_column = "trade_datetime" if "trade_datetime" in output else "trade_date"
            output = output.sort_values(sort_column).reset_index(drop=True)
    temporary = path.with_suffix(".parquet.tmp")
    output.to_parquet(temporary, index=False)
    pd.read_parquet(temporary)
    temporary.replace(path)


def replace_snapshot(frame: pd.DataFrame, path: Path) -> None:
    """Atomically replace a snapshot after removing known-invalid rows."""
    if frame.empty:
        raise ValueError(f"拒绝用空数据替换快照: {path}")
    temporary = path.with_suffix(".parquet.tmp")
    frame.to_parquet(temporary, index=False)
    pd.read_parquet(temporary)
    temporary.replace(path)


def _load_or_fetch_stock(
    provider: AkshareProvider,
    stock: StockConfig,
    start: date,
    end: date,
    adjust: str,
    force: bool,
) -> tuple[pd.DataFrame, Path]:
    settings = load_settings()
    label = "raw" if adjust == "" else adjust
    path = _snapshot_path(
        settings["resolved_paths"]["raw_daily"], date.today(), f"{stock.code}_{label}.parquet"
    )
    if path.exists() and not force:
        logger.info("使用今日已有快照 {}", path)
        existing = pd.read_parquet(path)
        frame = drop_incomplete_current_daily_bar(existing)
        if len(frame) != len(existing):
            replace_snapshot(frame, path)
        return frame, path
    frame = provider.fetch_stock_daily(stock.code, start, end, adjust)
    if frame.empty:
        raise ValueError(f"{stock.code} {label} 返回空数据，旧数据保持不变")
    if path.exists():
        existing = pd.read_parquet(path)
        cleaned = drop_incomplete_current_daily_bar(existing)
        if len(cleaned) != len(existing):
            replace_snapshot(cleaned, path)
    save_snapshot(frame, path)
    return frame, path


def _load_or_fetch_benchmark(
    provider: AkshareProvider,
    benchmark: BenchmarkConfig,
    start: date,
    end: date,
    force: bool,
) -> tuple[pd.DataFrame, Path]:
    settings = load_settings()
    path = _snapshot_path(
        settings["resolved_paths"]["raw_benchmark"], date.today(), f"{benchmark.code}.parquet"
    )
    if path.exists() and not force:
        logger.info("使用今日已有指数快照 {}", path)
        existing = pd.read_parquet(path)
        frame = drop_incomplete_current_daily_bar(existing)
        if len(frame) != len(existing):
            replace_snapshot(frame, path)
        return frame, path
    frame = provider.fetch_benchmark_daily(benchmark.code, start, end)
    if frame.empty:
        raise ValueError(f"{benchmark.code} 指数返回空数据，旧数据保持不变")
    if path.exists():
        existing = pd.read_parquet(path)
        cleaned = drop_incomplete_current_daily_bar(existing)
        if len(cleaned) != len(existing):
            replace_snapshot(cleaned, path)
    save_snapshot(frame, path)
    return frame, path


def ingest_market_data(
    database: Database,
    stocks: Iterable[StockConfig],
    start: date,
    end: date,
    job_name: str,
    force: bool = False,
    benchmarks: Iterable[BenchmarkConfig] | None = None,
    benchmark_start: date | None = None,
) -> dict[str, int]:
    """Fetch stock/raw/qfq and benchmarks, snapshot them, then upsert transactionally."""
    provider = AkshareProvider()
    run_id = database.start_ingestion(job_name, "akshare")
    fetched = inserted = updated = 0
    stock_list = list(stocks)
    if benchmarks is None:
        benchmark_list = []
        seen: set[str] = set()
        for stock in stock_list:
            if stock.benchmark_code not in seen:
                benchmark_list.append(BenchmarkConfig(
                    code=stock.benchmark_code,
                    exchange="SZ" if stock.benchmark_code.startswith("399") else "SH",
                    full_code=(
                        f"{stock.benchmark_code}.SZ"
                        if stock.benchmark_code.startswith("399")
                        else f"{stock.benchmark_code}.SH"
                    ),
                    name=stock.benchmark_name,
                    role="primary",
                    enabled=True,
                ))
                seen.add(stock.benchmark_code)
    else:
        benchmark_list = [item for item in benchmarks if item.enabled]
    try:
        for stock in stock_list:
            for adjust in ("", "qfq"):
                frame, path = _load_or_fetch_stock(provider, stock, start, end, adjust, force)
                new, changed = database.upsert_dataframe("daily_bars", frame)
                fetched += len(frame)
                inserted += new
                updated += changed
                logger.info(
                    "写入股票 {} {} fetched={} inserted={} updated={} snapshot={}",
                    stock.code, adjust or "raw", len(frame), new, changed, path,
                )
        for benchmark in benchmark_list:
            frame, path = _load_or_fetch_benchmark(
                provider, benchmark, benchmark_start or start, end, force
            )
            new, changed = database.upsert_dataframe("benchmark_daily_bars", frame)
            fetched += len(frame)
            inserted += new
            updated += changed
            logger.info(
                "写入指数 {} fetched={} inserted={} updated={} snapshot={}",
                benchmark.code, len(frame), new, changed, path,
            )
        database.finish_ingestion(run_id, "success", fetched, inserted, updated)
        return {"rows_fetched": fetched, "rows_inserted": inserted, "rows_updated": updated}
    except Exception as exc:
        database.finish_ingestion(run_id, "failed", fetched, inserted, updated, str(exc))
        logger.exception("数据抓取失败，已有数据保持不变: {}", exc)
        raise


def ingest_minute_comparison_data(
    database: Database,
    stocks: Iterable[StockConfig],
    benchmarks: Iterable[BenchmarkConfig],
    job_name: str = "update_minute_comparison",
) -> dict[str, int]:
    """Fetch recent one-minute bars for all enabled stocks and benchmark indexes."""
    provider = AkshareProvider()
    settings = load_settings()
    run_id = database.start_ingestion(job_name, "akshare")
    fetched = inserted = updated = 0
    try:
        targets = [
            (stock.code, stock.name, provider.fetch_minute_bars)
            for stock in stocks
        ]
        targets.extend(
            (
                benchmark.code,
                benchmark.name,
                provider.fetch_benchmark_minute_bars,
            )
            for benchmark in benchmarks
            if benchmark.enabled
        )
        collected: list[
            tuple[str, str, pd.DataFrame, date, Path]
        ] = []
        for code, name, fetcher in targets:
            minutes = fetcher(code)
            if minutes.empty:
                raise ValueError(
                    f"{name}（{code}）分钟行情为空，旧数据保持不变"
                )
            latest_minute_date = pd.to_datetime(
                minutes["trade_datetime"]
            ).dt.date.max()
            minute_path = _snapshot_path(
                settings["resolved_paths"]["raw_minute"],
                latest_minute_date,
                f"{code}_1m.parquet",
            )
            collected.append(
                (code, name, minutes, latest_minute_date, minute_path)
            )
            fetched += len(minutes)

        latest_dates = {item[3] for item in collected}
        if len(latest_dates) != 1:
            coverage = {
                code: latest_date.isoformat()
                for code, _, _, latest_date, _ in collected
            }
            raise ValueError(f"分钟行情交易日不同步，拒绝整批写入: {coverage}")
        latest_times = {
            code: pd.to_datetime(minutes["trade_datetime"]).max()
            for code, _, minutes, _, _ in collected
        }
        freshest = max(latest_times.values())
        stale = {
            code: timestamp.isoformat()
            for code, timestamp in latest_times.items()
            if freshest - timestamp > pd.Timedelta(minutes=2)
        }
        if stale:
            raise ValueError(
                f"分钟行情最新时间不同步，拒绝整批写入: {stale}; "
                f"freshest={freshest.isoformat()}"
            )

        for code, _, minutes, _, minute_path in collected:
            save_snapshot(
                minutes,
                minute_path,
                ["code", "trade_datetime", "interval_minutes"],
            )
            logger.info(
                "分钟快照就绪 {} rows={} latest={} snapshot={}",
                code,
                len(minutes),
                latest_times[code],
                minute_path,
            )
        combined = pd.concat(
            [item[2] for item in collected],
            ignore_index=True,
        )
        inserted, updated = database.upsert_dataframe(
            "minute_bars", combined
        )
        logger.info(
            "分钟行情整批写入完成 instruments={} rows={} inserted={} updated={}",
            len(collected),
            len(combined),
            inserted,
            updated,
        )
        database.finish_ingestion(
            run_id, "success", fetched, inserted, updated
        )
        return {
            "rows_fetched": fetched,
            "rows_inserted": inserted,
            "rows_updated": updated,
        }
    except Exception as exc:
        database.finish_ingestion(
            run_id, "failed", fetched, inserted, updated, str(exc)
        )
        logger.exception("分钟对比数据抓取失败，已有数据保持不变: {}", exc)
        raise


def ingest_intraday_data(
    database: Database,
    stocks: Iterable[StockConfig],
    job_name: str = "update_intraday",
) -> dict[str, int]:
    """Fetch transaction details and write only data reconciled with daily bars."""
    provider = AkshareProvider()
    settings = load_settings()
    run_id = database.start_ingestion(job_name, "akshare")
    fetched = inserted = updated = 0
    try:
        for stock in stocks:
            daily = database.get_stock_bars(stock.code, "raw")
            if daily.empty:
                raise ValueError(f"{stock.code} 日线为空，不能核验逐笔数据")
            daily_row = daily.iloc[-1]
            latest_date = pd.to_datetime(daily_row["trade_date"]).date()
            ticks = provider.fetch_tick_trades(stock.code, latest_date)
            if ticks.empty:
                raise ValueError(f"{stock.code} 逐笔成交为空，旧数据保持不变")
            reconciliation = reconcile_tick_with_daily(ticks, daily_row)
            tick_path = _snapshot_path(
                settings["resolved_paths"]["raw_tick"], latest_date, f"{stock.code}.parquet"
            )
            save_snapshot(
                ticks,
                tick_path,
                ["code", "trade_date", "sequence_no"],
            )
            new, changed = database.upsert_dataframe("tick_trades", ticks)
            fetched += len(ticks)
            inserted += new
            updated += changed
            logger.info(
                "写入逐笔 {} rows={} inserted={} updated={} amount_coverage={:.4f} "
                "volume_coverage={:.4f}",
                stock.code, len(ticks), new, changed,
                reconciliation["amount_coverage"], reconciliation["volume_coverage"],
            )

        database.finish_ingestion(run_id, "success", fetched, inserted, updated)
        return {"rows_fetched": fetched, "rows_inserted": inserted, "rows_updated": updated}
    except Exception as exc:
        database.finish_ingestion(run_id, "failed", fetched, inserted, updated, str(exc))
        logger.exception("逐笔抓取失败，已有数据保持不变: {}", exc)
        raise
