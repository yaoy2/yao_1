from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
import threading
import time
from typing import Any, Iterator
from uuid import uuid4

import duckdb
import pandas as pd

from src.utils.config import load_settings


_CONNECTION_LOCKS_GUARD = threading.Lock()
_CONNECTION_LOCKS: dict[str, Any] = {}


def _connection_lock(path: Path) -> Any:
    """Return one re-entrant connection lock per database file in this process."""
    key = str(path.resolve()).casefold()
    with _CONNECTION_LOCKS_GUARD:
        return _CONNECTION_LOCKS.setdefault(key, threading.RLock())


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS instruments (
    code VARCHAR PRIMARY KEY,
    exchange VARCHAR,
    full_code VARCHAR,
    name VARCHAR,
    instrument_type VARCHAR,
    benchmark_code VARCHAR,
    enabled BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_bars (
    code VARCHAR,
    trade_date DATE,
    adjust_type VARCHAR,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE,
    amplitude DOUBLE,
    pct_change DOUBLE,
    change_amount DOUBLE,
    turnover_rate DOUBLE,
    source VARCHAR,
    fetched_at TIMESTAMP,
    PRIMARY KEY (code, trade_date, adjust_type)
);

CREATE TABLE IF NOT EXISTS benchmark_daily_bars (
    code VARCHAR,
    trade_date DATE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE,
    source VARCHAR,
    fetched_at TIMESTAMP,
    PRIMARY KEY (code, trade_date)
);

CREATE TABLE IF NOT EXISTS daily_features (
    code VARCHAR,
    trade_date DATE,
    close DOUBLE,
    ret_1d DOUBLE,
    ret_3d DOUBLE,
    ret_5d DOUBLE,
    ret_10d DOUBLE,
    ret_20d DOUBLE,
    ma5 DOUBLE,
    ma10 DOUBLE,
    ma20 DOUBLE,
    ma60 DOUBLE,
    dist_ma5 DOUBLE,
    dist_ma10 DOUBLE,
    dist_ma20 DOUBLE,
    dist_ma60 DOUBLE,
    volume_ma5 DOUBLE,
    volume_ma20 DOUBLE,
    volume_ratio_5 DOUBLE,
    volume_ratio_20 DOUBLE,
    amount_ma5 DOUBLE,
    amount_ma20 DOUBLE,
    atr14 DOUBLE,
    atr14_pct DOUBLE,
    range_position_20 DOUBLE,
    range_position_60 DOUBLE,
    drawdown_20 DOUBLE,
    drawdown_60 DOUBLE,
    gap_pct DOUBLE,
    body_pct DOUBLE,
    upper_wick_pct DOUBLE,
    lower_wick_pct DOUBLE,
    close_location_value DOUBLE,
    new_high_20 BOOLEAN,
    new_low_20 BOOLEAN,
    rs_5 DOUBLE,
    rs_10 DOUBLE,
    rs_20 DOUBLE,
    up_streak INTEGER,
    down_streak INTEGER,
    volume_percentile_120 DOUBLE,
    volatility_percentile_120 DOUBLE,
    trend_state VARCHAR,
    volume_state VARCHAR,
    location_state VARCHAR,
    relative_strength_state VARCHAR,
    calculated_at TIMESTAMP,
    PRIMARY KEY (code, trade_date)
);

CREATE TABLE IF NOT EXISTS benchmark_linkage_features (
    code VARCHAR,
    trade_date DATE,
    benchmark_code VARCHAR,
    stock_ret_1d DOUBLE,
    stock_ret_5d DOUBLE,
    stock_ret_20d DOUBLE,
    stock_ret_60d DOUBLE,
    benchmark_ret_1d DOUBLE,
    benchmark_ret_5d DOUBLE,
    benchmark_ret_20d DOUBLE,
    benchmark_ret_60d DOUBLE,
    excess_ret_1d DOUBLE,
    excess_ret_5d DOUBLE,
    excess_ret_20d DOUBLE,
    excess_ret_60d DOUBLE,
    correlation_20d DOUBLE,
    correlation_60d DOUBLE,
    beta_20d DOUBLE,
    beta_60d DOUBLE,
    same_direction BOOLEAN,
    relationship_state VARCHAR,
    calculated_at TIMESTAMP,
    PRIMARY KEY (code, trade_date, benchmark_code)
);

CREATE TABLE IF NOT EXISTS tick_trades (
    code VARCHAR,
    trade_date DATE,
    sequence_no INTEGER,
    trade_time TIME,
    trade_datetime TIMESTAMP,
    price DOUBLE,
    price_change DOUBLE,
    volume_lots DOUBLE,
    amount DOUBLE,
    side VARCHAR,
    source VARCHAR,
    fetched_at TIMESTAMP,
    PRIMARY KEY (code, trade_date, sequence_no)
);

CREATE TABLE IF NOT EXISTS minute_bars (
    code VARCHAR,
    trade_datetime TIMESTAMP,
    interval_minutes INTEGER,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume_shares DOUBLE,
    amount DOUBLE,
    source VARCHAR,
    fetched_at TIMESTAMP,
    PRIMARY KEY (code, trade_datetime, interval_minutes)
);

CREATE TABLE IF NOT EXISTS daily_money_flow (
    code VARCHAR,
    trade_date DATE,
    tick_count INTEGER,
    total_amount DOUBLE,
    buy_amount DOUBLE,
    sell_amount DOUBLE,
    neutral_amount DOUBLE,
    net_active_amount DOUBLE,
    net_active_ratio DOUBLE,
    buy_sell_ratio DOUBLE,
    large_trade_threshold DOUBLE,
    large_trade_count INTEGER,
    large_buy_amount DOUBLE,
    large_sell_amount DOUBLE,
    large_net_amount DOUBLE,
    large_net_ratio DOUBLE,
    vwap DOUBLE,
    close_vs_vwap DOUBLE,
    tail_net_amount DOUBLE,
    amount_coverage DOUBLE,
    volume_coverage DOUBLE,
    flow_state VARCHAR,
    confidence VARCHAR,
    evidence VARCHAR,
    calculated_at TIMESTAMP,
    PRIMARY KEY (code, trade_date)
);

CREATE TABLE IF NOT EXISTS ai_chain_nodes (
    node_id VARCHAR PRIMARY KEY,
    stage VARCHAR,
    industry VARCHAR,
    subindustry VARCHAR,
    field VARCHAR,
    direction VARCHAR,
    order_index INTEGER,
    name VARCHAR,
    description VARCHAR,
    source_provider VARCHAR,
    source_name VARCHAR,
    source_code VARCHAR,
    enabled BOOLEAN,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_sector_daily_bars (
    node_id VARCHAR,
    trade_date DATE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE,
    source VARCHAR,
    fetched_at TIMESTAMP,
    PRIMARY KEY (node_id, trade_date)
);

CREATE TABLE IF NOT EXISTS ai_sector_minute_bars (
    node_id VARCHAR,
    trade_datetime TIMESTAMP,
    close DOUBLE,
    pct_change DOUBLE,
    previous_close DOUBLE,
    source VARCHAR,
    fetched_at TIMESTAMP,
    PRIMARY KEY (node_id, trade_datetime)
);

CREATE TABLE IF NOT EXISTS ai_sector_membership_snapshots (
    node_id VARCHAR,
    snapshot_date DATE,
    stock_code VARCHAR,
    stock_name VARCHAR,
    rank INTEGER,
    current_price DOUBLE,
    today_high DOUBLE,
    today_low DOUBLE,
    pct_change DOUBLE,
    amplitude DOUBLE,
    volume DOUBLE,
    volume_ratio DOUBLE,
    total_market_cap DOUBLE,
    float_market_cap DOUBLE,
    turnover_rate DOUBLE,
    amount_text VARCHAR,
    source VARCHAR,
    fetched_at TIMESTAMP,
    PRIMARY KEY (node_id, snapshot_date, stock_code)
);

CREATE TABLE IF NOT EXISTS company_business_profiles (
    stock_code VARCHAR PRIMARY KEY,
    stock_name VARCHAR,
    main_business VARCHAR,
    product_type VARCHAR,
    product_name VARCHAR,
    business_scope VARCHAR,
    source VARCHAR,
    fetched_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id VARCHAR PRIMARY KEY,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    job_name VARCHAR,
    source VARCHAR,
    status VARCHAR,
    rows_fetched BIGINT,
    rows_inserted BIGINT,
    rows_updated BIGINT,
    error_message VARCHAR
);
"""

MIGRATION_SQL = """
ALTER TABLE daily_money_flow ADD COLUMN IF NOT EXISTS large_net_ratio DOUBLE;
ALTER TABLE ai_chain_nodes ADD COLUMN IF NOT EXISTS industry VARCHAR;
ALTER TABLE ai_chain_nodes ADD COLUMN IF NOT EXISTS subindustry VARCHAR;
ALTER TABLE ai_chain_nodes ADD COLUMN IF NOT EXISTS field VARCHAR;
ALTER TABLE ai_chain_nodes ADD COLUMN IF NOT EXISTS direction VARCHAR;
ALTER TABLE ai_sector_membership_snapshots ADD COLUMN IF NOT EXISTS today_high DOUBLE;
ALTER TABLE ai_sector_membership_snapshots ADD COLUMN IF NOT EXISTS today_low DOUBLE;
ALTER TABLE ai_sector_membership_snapshots ADD COLUMN IF NOT EXISTS amplitude DOUBLE;
ALTER TABLE ai_sector_membership_snapshots ADD COLUMN IF NOT EXISTS volume DOUBLE;
ALTER TABLE ai_sector_membership_snapshots ADD COLUMN IF NOT EXISTS volume_ratio DOUBLE;
ALTER TABLE ai_sector_membership_snapshots ADD COLUMN IF NOT EXISTS total_market_cap DOUBLE;
ALTER TABLE ai_sector_membership_snapshots ADD COLUMN IF NOT EXISTS float_market_cap DOUBLE;
"""

TABLE_KEYS = {
    "instruments": ["code"],
    "daily_bars": ["code", "trade_date", "adjust_type"],
    "benchmark_daily_bars": ["code", "trade_date"],
    "daily_features": ["code", "trade_date"],
    "benchmark_linkage_features": ["code", "trade_date", "benchmark_code"],
    "tick_trades": ["code", "trade_date", "sequence_no"],
    "minute_bars": ["code", "trade_datetime", "interval_minutes"],
    "daily_money_flow": ["code", "trade_date"],
    "ai_chain_nodes": ["node_id"],
    "ai_sector_daily_bars": ["node_id", "trade_date"],
    "ai_sector_minute_bars": ["node_id", "trade_datetime"],
    "ai_sector_membership_snapshots": [
        "node_id", "snapshot_date", "stock_code"
    ],
    "company_business_profiles": ["stock_code"],
    "ingestion_runs": ["run_id"],
}


class Database:
    """Centralized DuckDB access with idempotent DataFrame upserts."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or load_settings()["resolved_paths"]["database"]
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
        with _connection_lock(self.path):
            connection = None
            for attempt in range(6):
                try:
                    connection = duckdb.connect(
                        str(self.path), read_only=read_only
                    )
                    break
                except (duckdb.IOException, duckdb.ConnectionException):
                    if attempt == 5:
                        raise
                    time.sleep(0.25 * (attempt + 1))
            if connection is None:
                raise RuntimeError(f"无法连接数据库: {self.path}")
            try:
                yield connection
            finally:
                connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(SCHEMA_SQL)
            connection.execute(MIGRATION_SQL)

    def table_columns(self, table: str) -> list[str]:
        if table not in TABLE_KEYS:
            raise ValueError(f"不允许的表名: {table}")
        with self.connect(read_only=True) as connection:
            return connection.execute(f"SELECT * FROM {table} LIMIT 0").df().columns.tolist()

    def upsert_dataframe(self, table: str, frame: pd.DataFrame) -> tuple[int, int]:
        """Insert or replace rows transactionally and return inserted/updated counts."""
        if table not in TABLE_KEYS:
            raise ValueError(f"不允许的表名: {table}")
        if frame.empty:
            return 0, 0
        keys = TABLE_KEYS[table]
        missing_keys = set(keys).difference(frame.columns)
        if missing_keys:
            raise ValueError(f"{table} 缺少主键列: {sorted(missing_keys)}")
        with self.connect() as connection:
            table_columns = connection.execute(f"SELECT * FROM {table} LIMIT 0").df().columns.tolist()
            missing_columns = set(table_columns).difference(frame.columns)
            if missing_columns:
                raise ValueError(f"{table} 缺少字段: {sorted(missing_columns)}")
            incoming = frame[table_columns].copy()
            connection.register("_incoming", incoming)
            join = " AND ".join([f"t.{key} = i.{key}" for key in keys])
            updated = int(connection.execute(
                f"SELECT COUNT(*) FROM {table} t JOIN _incoming i ON {join}"
            ).fetchone()[0])
            key_tuple = ", ".join(keys)
            select_keys = ", ".join([f"i.{key}" for key in keys])
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.execute(
                    f"DELETE FROM {table} WHERE ({key_tuple}) IN (SELECT {select_keys} FROM _incoming i)"
                )
                columns = ", ".join(table_columns)
                connection.execute(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM _incoming")
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            finally:
                connection.unregister("_incoming")
        return len(frame) - updated, updated

    def upsert_instruments(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        now = datetime.now()
        existing = self.read_table("instruments") if self.path.exists() else pd.DataFrame()
        created = {str(row.code): row.created_at for row in existing.itertuples()} if not existing.empty else {}
        frame = pd.DataFrame([
            {**row, "created_at": created.get(row["code"], now), "updated_at": now}
            for row in rows
        ])
        return self.upsert_dataframe("instruments", frame)

    def read_table(
        self,
        table: str,
        where: str = "",
        params: list[Any] | None = None,
        order_by: str = "",
    ) -> pd.DataFrame:
        if table not in TABLE_KEYS:
            raise ValueError(f"不允许的表名: {table}")
        query = f"SELECT * FROM {table}"
        if where:
            query += f" WHERE {where}"
        if order_by:
            query += f" ORDER BY {order_by}"
        with self.connect(read_only=True) as connection:
            return connection.execute(query, params or []).df()

    def get_stock_bars(self, code: str, adjust_type: str = "qfq") -> pd.DataFrame:
        return self.read_table(
            "daily_bars", "code = ? AND adjust_type = ?", [code, adjust_type], "trade_date"
        )

    def get_benchmark_bars(self, code: str) -> pd.DataFrame:
        return self.read_table("benchmark_daily_bars", "code = ?", [code], "trade_date")

    def get_features(self, code: str) -> pd.DataFrame:
        return self.read_table("daily_features", "code = ?", [code], "trade_date")

    def get_linkage_features(self, code: str, benchmark_code: str | None = None) -> pd.DataFrame:
        if benchmark_code is None:
            return self.read_table(
                "benchmark_linkage_features", "code = ?", [code], "trade_date, benchmark_code"
            )
        return self.read_table(
            "benchmark_linkage_features",
            "code = ? AND benchmark_code = ?",
            [code, benchmark_code],
            "trade_date",
        )

    def get_tick_trades(self, code: str, trade_date: date | None = None) -> pd.DataFrame:
        if trade_date is None:
            return self.read_table("tick_trades", "code = ?", [code], "trade_date, sequence_no")
        return self.read_table(
            "tick_trades", "code = ? AND trade_date = ?", [code, trade_date], "sequence_no"
        )

    def get_minute_bars(self, code: str) -> pd.DataFrame:
        return self.read_table("minute_bars", "code = ?", [code], "trade_datetime")

    def get_money_flow(self, code: str) -> pd.DataFrame:
        return self.read_table("daily_money_flow", "code = ?", [code], "trade_date")

    def get_ai_chain_nodes(self) -> pd.DataFrame:
        return self.read_table(
            "ai_chain_nodes", "enabled = TRUE", order_by="stage, order_index"
        )

    def get_ai_sector_daily(self, node_id: str) -> pd.DataFrame:
        return self.read_table(
            "ai_sector_daily_bars",
            "node_id = ?",
            [node_id],
            "trade_date",
        )

    def get_ai_sector_minute(self, node_id: str) -> pd.DataFrame:
        return self.read_table(
            "ai_sector_minute_bars",
            "node_id = ?",
            [node_id],
            "trade_datetime",
        )

    def get_latest_ai_memberships(self, node_id: str) -> pd.DataFrame:
        with self.connect(read_only=True) as connection:
            return connection.execute(
                """
                SELECT *
                FROM ai_sector_membership_snapshots
                WHERE node_id = ?
                  AND snapshot_date = (
                    SELECT MAX(snapshot_date)
                    FROM ai_sector_membership_snapshots
                    WHERE node_id = ?
                  )
                ORDER BY rank, stock_code
                """,
                [node_id, node_id],
            ).df()

    def upsert_ai_memberships(
        self,
        frame: pd.DataFrame,
    ) -> tuple[int, int]:
        """Upsert AI members without replacing successful quote fields with nulls."""
        if frame.empty:
            return 0, 0
        table = "ai_sector_membership_snapshots"
        columns = self.table_columns(table)
        missing = set(columns).difference(frame.columns)
        if missing:
            raise ValueError(f"{table} 缺少字段: {sorted(missing)}")
        incoming = frame[columns].copy()
        existing = self.read_table(table)
        keys = TABLE_KEYS[table]
        if existing.empty:
            aligned = pd.DataFrame(index=incoming.index, columns=columns)
        else:
            incoming_index = pd.MultiIndex.from_frame(incoming[keys])
            existing_indexed = existing.set_index(keys)
            aligned = existing_indexed.reindex(incoming_index).reset_index(
                drop=True
            )
        preserved_rows = pd.Series(False, index=incoming.index, dtype=bool)
        protected_columns = [
            "current_price", "today_high", "today_low", "pct_change",
            "amplitude", "volume", "volume_ratio", "total_market_cap",
            "float_market_cap", "turnover_rate",
        ]
        for column in protected_columns:
            previous = aligned[column].reset_index(drop=True)
            preserve = incoming[column].isna() & previous.notna()
            incoming.loc[preserve, column] = previous.loc[preserve]
            preserved_rows |= preserve
        if preserved_rows.any():
            for column in ["source", "fetched_at"]:
                previous = aligned[column].reset_index(drop=True)
                incoming.loc[preserved_rows, column] = previous.loc[
                    preserved_rows
                ]
        scopes = incoming[["node_id", "snapshot_date"]].drop_duplicates()
        with self.connect() as connection:
            connection.register("_incoming_ai_members", incoming)
            connection.register("_incoming_ai_scopes", scopes)
            updated = int(connection.execute(
                """
                SELECT COUNT(*)
                FROM ai_sector_membership_snapshots existing
                JOIN _incoming_ai_members incoming
                  ON existing.node_id = incoming.node_id
                 AND existing.snapshot_date = incoming.snapshot_date
                 AND existing.stock_code = incoming.stock_code
                """
            ).fetchone()[0])
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.execute(
                    """
                    DELETE FROM ai_sector_membership_snapshots existing
                    WHERE EXISTS (
                        SELECT 1
                        FROM _incoming_ai_scopes incoming
                        WHERE existing.node_id = incoming.node_id
                          AND existing.snapshot_date = incoming.snapshot_date
                    )
                    """
                )
                column_list = ", ".join(columns)
                connection.execute(
                    f"""
                    INSERT INTO ai_sector_membership_snapshots ({column_list})
                    SELECT {column_list} FROM _incoming_ai_members
                    """
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            finally:
                connection.unregister("_incoming_ai_members")
                connection.unregister("_incoming_ai_scopes")
        return len(incoming) - updated, updated

    def get_all_latest_ai_memberships(self) -> pd.DataFrame:
        with self.connect(read_only=True) as connection:
            return connection.execute(
                """
                SELECT *
                FROM ai_sector_membership_snapshots
                QUALIFY snapshot_date = MAX(snapshot_date)
                    OVER (PARTITION BY node_id)
                ORDER BY node_id, rank, stock_code
                """
            ).df()

    def get_ai_chart_ready_codes(self, node_id: str) -> list[str]:
        """Return current node members that have both qfq daily and minute bars."""
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                WITH latest_members AS (
                    SELECT stock_code, rank
                    FROM ai_sector_membership_snapshots
                    WHERE node_id = ?
                      AND snapshot_date = (
                          SELECT MAX(snapshot_date)
                          FROM ai_sector_membership_snapshots
                          WHERE node_id = ?
                      )
                )
                SELECT member.stock_code
                FROM latest_members member
                WHERE EXISTS (
                    SELECT 1 FROM daily_bars daily
                    WHERE daily.code = member.stock_code
                      AND daily.adjust_type = 'qfq'
                )
                  AND EXISTS (
                    SELECT 1 FROM minute_bars minute
                    WHERE minute.code = member.stock_code
                )
                ORDER BY member.rank, member.stock_code
                """,
                [node_id, node_id],
            ).fetchall()
        return [str(row[0]).zfill(6) for row in rows]

    def get_company_business_profile(self, stock_code: str) -> pd.DataFrame:
        return self.read_table(
            "company_business_profiles",
            "stock_code = ?",
            [stock_code],
        )

    def get_ai_profile_codes(self) -> set[str]:
        frame = self.read_table("company_business_profiles")
        if frame.empty:
            return set()
        return set(frame["stock_code"].astype(str))

    def latest_date(self, table: str, code: str, adjust_type: str | None = None) -> date | None:
        if table not in {
            "daily_bars", "benchmark_daily_bars", "daily_features",
            "benchmark_linkage_features", "tick_trades", "daily_money_flow",
        }:
            raise ValueError(f"不支持查询最新日期的表: {table}")
        where = "code = ?"
        params: list[Any] = [code]
        if adjust_type is not None:
            where += " AND adjust_type = ?"
            params.append(adjust_type)
        with self.connect(read_only=True) as connection:
            value = connection.execute(
                f"SELECT MAX(trade_date) FROM {table} WHERE {where}", params
            ).fetchone()[0]
        return value

    def start_ingestion(self, job_name: str, source: str) -> str:
        run_id = str(uuid4())
        frame = pd.DataFrame([{
            "run_id": run_id,
            "started_at": datetime.now(),
            "finished_at": pd.NaT,
            "job_name": job_name,
            "source": source,
            "status": "running",
            "rows_fetched": 0,
            "rows_inserted": 0,
            "rows_updated": 0,
            "error_message": None,
        }])
        self.upsert_dataframe("ingestion_runs", frame)
        return run_id

    def finish_ingestion(
        self,
        run_id: str,
        status: str,
        rows_fetched: int,
        rows_inserted: int,
        rows_updated: int,
        error_message: str | None = None,
    ) -> None:
        current = self.read_table("ingestion_runs", "run_id = ?", [run_id])
        if current.empty:
            raise ValueError(f"找不到 ingestion run: {run_id}")
        row = current.iloc[0].to_dict()
        row.update({
            "finished_at": datetime.now(),
            "status": status,
            "rows_fetched": rows_fetched,
            "rows_inserted": rows_inserted,
            "rows_updated": rows_updated,
            "error_message": error_message,
        })
        self.upsert_dataframe("ingestion_runs", pd.DataFrame([row]))

    def latest_ingestion(self) -> pd.DataFrame:
        with self.connect(read_only=True) as connection:
            return connection.execute(
                "SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT 1"
            ).df()

    def counts_and_ranges(self, code: str, benchmark_code: str) -> dict[str, Any]:
        with self.connect(read_only=True) as connection:
            raw = connection.execute(
                "SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM daily_bars "
                "WHERE code = ? AND adjust_type = 'raw'", [code]
            ).fetchone()
            qfq = connection.execute(
                "SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM daily_bars "
                "WHERE code = ? AND adjust_type = 'qfq'", [code]
            ).fetchone()
            benchmark = connection.execute(
                "SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM benchmark_daily_bars "
                "WHERE code = ?", [benchmark_code]
            ).fetchone()
        return {
            "raw_count": raw[0], "raw_start": raw[1], "raw_end": raw[2],
            "qfq_count": qfq[0], "qfq_start": qfq[1], "qfq_end": qfq[2],
            "benchmark_count": benchmark[0],
            "benchmark_start": benchmark[1], "benchmark_end": benchmark[2],
        }
