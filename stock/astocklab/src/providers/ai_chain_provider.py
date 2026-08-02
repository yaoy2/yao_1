from __future__ import annotations

import json
from datetime import date, datetime, timezone
from io import StringIO

import akshare as ak
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.providers.akshare_provider import (
    SHANGHAI_TZ,
    direct_network,
    stock_market_symbol,
)
from src.utils.config import AIChainNodeConfig


THS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/123.0 Safari/537.36"
    ),
    "Referer": "http://q.10jqka.com.cn",
}
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="


def standardize_sector_daily(
    raw: pd.DataFrame,
    node_id: str,
) -> pd.DataFrame:
    mapping = {
        "日期": "trade_date",
        "开盘价": "open",
        "最高价": "high",
        "最低价": "low",
        "收盘价": "close",
        "成交量": "volume",
        "成交额": "amount",
    }
    frame = raw.rename(columns=mapping).copy()
    required = set(mapping.values())
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"AI板块日线缺少字段: {sorted(missing)}")
    frame["node_id"] = node_id
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"], errors="coerce"
    ).dt.date
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame["source"] = "akshare.stock_board_concept_index_ths"
    frame["fetched_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    columns = [
        "node_id", "trade_date", "open", "high", "low", "close",
        "volume", "amount", "source", "fetched_at",
    ]
    frame = frame[columns].dropna(
        subset=["trade_date", "open", "high", "low", "close"]
    )
    return frame.drop_duplicates(
        ["node_id", "trade_date"], keep="last"
    ).sort_values("trade_date").reset_index(drop=True)


def standardize_constituents(
    raw: pd.DataFrame,
    node_id: str,
    snapshot_date: date,
) -> pd.DataFrame:
    mapping = {
        "序号": "rank",
        "代码": "stock_code",
        "名称": "stock_name",
        "现价": "current_price",
        "涨跌幅(%)": "pct_change",
        "换手(%)": "turnover_rate",
        "成交额": "amount_text",
    }
    frame = raw.rename(columns=mapping).copy()
    required = {"rank", "stock_code", "stock_name"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"AI板块成分股缺少字段: {sorted(missing)}")
    for optional in [
        "current_price", "today_high", "today_low", "pct_change",
        "amplitude", "volume", "volume_ratio", "total_market_cap",
        "float_market_cap", "turnover_rate", "amount_text",
    ]:
        if optional not in frame:
            frame[optional] = np.nan if optional != "amount_text" else None
    frame["stock_code"] = (
        frame["stock_code"]
        .astype(str)
        .str.extract(r"(\d+)", expand=False)
        .str.zfill(6)
    )
    frame["stock_name"] = frame["stock_name"].astype(str).str.strip()
    frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce")
    for column in [
        "current_price", "today_high", "today_low", "pct_change",
        "amplitude", "volume", "volume_ratio", "total_market_cap",
        "float_market_cap", "turnover_rate",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["node_id"] = node_id
    frame["snapshot_date"] = snapshot_date
    frame["source"] = "ths.concept_detail"
    frame["fetched_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    columns = [
        "node_id", "snapshot_date", "stock_code", "stock_name", "rank",
        "current_price", "today_high", "today_low", "pct_change",
        "amplitude", "volume", "volume_ratio", "total_market_cap",
        "float_market_cap", "turnover_rate", "amount_text", "source",
        "fetched_at",
    ]
    frame = frame[columns].dropna(
        subset=["stock_code", "stock_name", "rank"]
    )
    frame["rank"] = frame["rank"].astype(int)
    return frame.drop_duplicates(
        ["node_id", "snapshot_date", "stock_code"], keep="first"
    ).sort_values(["rank", "stock_code"]).reset_index(drop=True)


def standardize_stock_spot(
    raw: pd.DataFrame,
    snapshot_date: date,
) -> pd.DataFrame:
    """Normalize one full-market A-share spot snapshot for AI pool joins."""
    mapping = {
        "代码": "stock_code",
        "名称": "stock_name",
        "最新价": "current_price",
        "最高": "today_high",
        "最低": "today_low",
        "涨跌幅": "pct_change",
        "振幅": "amplitude",
        "成交量": "volume",
        "量比": "volume_ratio",
        "总市值": "total_market_cap",
        "流通市值": "float_market_cap",
        "换手率": "turnover_rate",
    }
    frame = raw.rename(columns=mapping).copy()
    required = set(mapping.values())
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"A股实时行情缺少字段: {sorted(missing)}")
    frame["stock_code"] = (
        frame["stock_code"]
        .astype(str)
        .str.extract(r"(\d+)", expand=False)
        .str.zfill(6)
    )
    frame["stock_name"] = frame["stock_name"].astype(str).str.strip()
    numeric_columns = [
        "current_price", "today_high", "today_low", "pct_change",
        "amplitude", "volume", "volume_ratio", "total_market_cap",
        "float_market_cap", "turnover_rate",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame["snapshot_date"] = snapshot_date
    for column in ["current_price", "today_high", "today_low"]:
        frame.loc[frame[column] <= 0, column] = np.nan
    frame["source"] = "tencent.stock_zh_a_spot_tx+qt.gtimg"
    frame["fetched_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    columns = [
        "snapshot_date", "stock_code", "stock_name", *numeric_columns,
        "source", "fetched_at",
    ]
    return (
        frame[columns]
        .dropna(subset=["stock_code", "stock_name"])
        .drop_duplicates("stock_code", keep="last")
        .sort_values("stock_code")
        .reset_index(drop=True)
    )


def enrich_constituents_with_spot(
    members: pd.DataFrame,
    spot: pd.DataFrame,
) -> pd.DataFrame:
    """Fill constituent quote fields from the matching full-market snapshot."""
    if members.empty or spot.empty:
        return members.copy()
    quote_columns = [
        "current_price", "today_high", "today_low", "pct_change",
        "amplitude", "volume", "volume_ratio", "total_market_cap",
        "float_market_cap", "turnover_rate",
    ]
    lookup = spot[["stock_code", *quote_columns]].copy()
    result = members.merge(
        lookup,
        on="stock_code",
        how="left",
        suffixes=("", "_spot"),
        validate="many_to_one",
    )
    for column in quote_columns:
        spot_column = f"{column}_spot"
        result[column] = result[spot_column].combine_first(result[column])
        result = result.drop(columns=spot_column)
    matched = result["stock_code"].isin(set(spot["stock_code"]))
    result.loc[matched, "source"] = (
        "ths.concept_detail+tencent.stock_zh_a_spot_tx+qt.gtimg"
    )
    return result[members.columns]


class ThsAIChainProvider:
    """THS-backed sector, constituent, intraday and company-profile provider."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_sector_daily(
        self,
        node: AIChainNodeConfig,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        logger.info(
            "请求AI板块日线 node={} source_name={} start={} end={}",
            node.node_id,
            node.source_name,
            start,
            end,
        )
        with direct_network():
            raw = ak.stock_board_concept_index_ths(
                symbol=node.source_name,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
        return standardize_sector_daily(raw, node.node_id)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _detail_html(self, source_code: str, page: int = 1) -> str:
        suffix = "" if page == 1 else f"page/{page}/"
        url = (
            f"http://q.10jqka.com.cn/gn/detail/code/{source_code}/"
            f"{suffix}"
        )
        with direct_network():
            response = requests.get(url, headers=THS_HEADERS, timeout=20)
        response.raise_for_status()
        if "<table" not in response.text:
            raise ValueError(f"同花顺板块页面未返回成分股表: {source_code}")
        return response.text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_constituents(
        self,
        node: AIChainNodeConfig,
        page_limit: int = 5,
    ) -> pd.DataFrame:
        first_html = self._detail_html(node.source_code)
        soup = BeautifulSoup(first_html, "lxml")
        page_info = soup.select_one(".page_info")
        page_count = 1
        if page_info and "/" in page_info.get_text(strip=True):
            page_count = int(page_info.get_text(strip=True).split("/")[-1])
        page_count = min(page_count, page_limit)
        tables = []
        for page in range(1, page_count + 1):
            html = first_html if page == 1 else self._detail_html(
                node.source_code, page
            )
            parsed = pd.read_html(
                StringIO(html),
                converters={"代码": str},
            )
            if not parsed:
                raise ValueError(
                    f"同花顺板块成分股表为空: {node.source_name} page={page}"
                )
            stock_table = next(
                (
                    table for table in parsed
                    if {"序号", "代码", "名称"}.issubset(table.columns)
                ),
                None,
            )
            if stock_table is None:
                raise ValueError(
                    f"同花顺板块页面没有可识别的股票表: "
                    f"{node.source_name} page={page}"
                )
            tables.append(stock_table)
        combined = pd.concat(tables, ignore_index=True)
        snapshot_date = datetime.now(SHANGHAI_TZ).date()
        result = standardize_constituents(
            combined, node.node_id, snapshot_date
        )
        logger.info(
            "AI板块成分股返回 node={} pages={} rows={}",
            node.node_id,
            page_count,
            len(result),
        )
        return result

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _fetch_tencent_high_low_batch(
        self,
        symbols: list[str],
    ) -> list[dict[str, object]]:
        with direct_network():
            response = requests.get(
                TENCENT_QUOTE_URL + ",".join(symbols),
                timeout=20,
            )
        response.raise_for_status()
        rows: list[dict[str, object]] = []
        for line in response.content.decode("gbk", errors="replace").splitlines():
            if '="' not in line:
                continue
            fields = line.split('="', 1)[1].rstrip('";').split("~")
            if len(fields) < 35:
                continue
            rows.append({
                "代码": fields[2],
                "最高": fields[33],
                "最低": fields[34],
            })
        if not rows:
            raise ValueError("腾讯AI股票池高低点行情为空。")
        return rows

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_stock_spot(self, stock_codes: list[str]) -> pd.DataFrame:
        """Fetch Tencent market snapshot plus batched intraday high and low."""
        codes = list(dict.fromkeys(str(code).zfill(6) for code in stock_codes))
        if not codes:
            raise ValueError("AI股票池代码为空，无法获取实时行情。")
        logger.info("请求AI股票池实时行情 stocks={}", len(codes))
        with direct_network():
            market = ak.stock_zh_a_spot_tx()
        market = market.copy()
        market["代码"] = market["code"].astype(str).str[-6:]
        market = market.loc[market["代码"].isin(codes)].copy()
        high_low_rows: list[dict[str, object]] = []
        symbols = [stock_market_symbol(code) for code in codes]
        for start in range(0, len(symbols), 60):
            high_low_rows.extend(
                self._fetch_tencent_high_low_batch(
                    symbols[start:start + 60]
                )
            )
        high_low = pd.DataFrame(high_low_rows).drop_duplicates(
            "代码", keep="last"
        )
        raw = market.rename(columns={
            "name": "名称",
            "zxj": "最新价",
            "zdf": "涨跌幅",
            "zf": "振幅",
            "volume": "成交量",
            "lb": "量比",
            "hsl": "换手率",
            "zsz": "总市值",
            "ltsz": "流通市值",
        }).merge(high_low, on="代码", how="left", validate="one_to_one")
        raw["总市值"] = pd.to_numeric(
            raw["总市值"], errors="coerce"
        ) * 100_000_000.0
        raw["流通市值"] = pd.to_numeric(
            raw["流通市值"], errors="coerce"
        ) * 100_000_000.0
        result = standardize_stock_spot(
            raw, datetime.now(SHANGHAI_TZ).date()
        )
        missing = sorted(set(codes).difference(result["stock_code"]))
        logger.info(
            "AI股票池实时行情返回 rows={} missing={}",
            len(result),
            len(missing),
        )
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_sector_minute(
        self,
        node: AIChainNodeConfig,
    ) -> pd.DataFrame:
        detail_html = self._detail_html(node.source_code)
        soup = BeautifulSoup(detail_html, "lxml")
        clid = soup.select_one("#clid")
        if clid is None or not clid.get("value"):
            raise ValueError(f"无法解析同花顺板块内部代码: {node.source_name}")
        inner_code = str(clid["value"])
        url = (
            "https://d.10jqka.com.cn/v6/time/"
            f"bk_{inner_code}/last.js"
        )
        with direct_network():
            response = requests.get(url, headers=THS_HEADERS, timeout=20)
        response.raise_for_status()
        text = response.text
        payload = json.loads(text[text.find("(") + 1:text.rfind(")")])
        data = payload[f"bk_{inner_code}"]
        trade_date = str(data["date"])
        previous_close = float(data["pre"])
        rows = []
        for item in str(data["data"]).split(";"):
            fields = item.split(",")
            if len(fields) < 2:
                continue
            timestamp = pd.to_datetime(
                trade_date + fields[0],
                format="%Y%m%d%H%M",
                errors="coerce",
            )
            close = pd.to_numeric(fields[1], errors="coerce")
            if pd.isna(timestamp) or pd.isna(close):
                continue
            rows.append({
                "node_id": node.node_id,
                "trade_datetime": timestamp,
                "close": float(close),
                "pct_change": float(close / previous_close - 1.0),
                "previous_close": previous_close,
                "source": "ths.d.10jqka.concept_minute",
                "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None),
            })
        result = pd.DataFrame(rows)
        if result.empty:
            raise ValueError(f"同花顺板块分钟数据为空: {node.source_name}")
        return result.drop_duplicates(
            ["node_id", "trade_datetime"], keep="last"
        ).sort_values("trade_datetime").reset_index(drop=True)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_business_profile(
        self,
        stock_code: str,
        stock_name: str,
    ) -> pd.DataFrame:
        with direct_network():
            raw = ak.stock_zyjs_ths(symbol=stock_code)
        if raw.empty:
            raise ValueError(f"主营介绍为空: {stock_code}")
        row = raw.iloc[0]
        result = pd.DataFrame([{
            "stock_code": stock_code,
            "stock_name": stock_name,
            "main_business": row.get("主营业务"),
            "product_type": row.get("产品类型"),
            "product_name": row.get("产品名称"),
            "business_scope": row.get("经营范围"),
            "source": "akshare.stock_zyjs_ths",
            "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }])
        return result.replace({np.nan: None})
