from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.storage.database import Database
from src.utils.config import StockConfig, load_settings


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _percent(value: Any) -> str:
    return "缺失" if pd.isna(value) else f"{float(value):.2%}"


def _number(value: Any, digits: int = 2) -> str:
    return "缺失" if pd.isna(value) else f"{float(value):,.{digits}f}"


def build_context_pack(
    database: Database,
    stock_config: StockConfig,
    validation: dict[str, Any] | None = None,
    as_of: date | None = None,
) -> tuple[Path, Path, Path]:
    """Build JSON, Markdown, and daily-summary reports from local database data."""
    settings = load_settings()
    raw = database.get_stock_bars(stock_config.code, "raw")
    features = database.get_features(stock_config.code)
    if raw.empty or features.empty:
        raise ValueError("行情或特征数据为空，无法生成 context pack")
    raw["trade_date"] = pd.to_datetime(raw["trade_date"]).dt.date
    features["trade_date"] = pd.to_datetime(features["trade_date"]).dt.date
    latest_date = min(raw["trade_date"].max(), features["trade_date"].max())
    raw_latest = raw.loc[raw["trade_date"] == latest_date].iloc[-1]
    feature_latest = features.loc[features["trade_date"] == latest_date].iloc[-1]
    tick_trades = database.get_tick_trades(stock_config.code, latest_date)
    minute_bars = database.get_minute_bars(stock_config.code)
    money_flow = database.get_money_flow(stock_config.code)
    linkage = database.get_linkage_features(stock_config.code)
    instruments = database.read_table("instruments")
    instrument_names = (
        instruments.set_index("code")["name"].to_dict()
        if not instruments.empty else {}
    )
    money_latest = None
    if not money_flow.empty:
        money_flow["trade_date"] = pd.to_datetime(money_flow["trade_date"]).dt.date
        matching_money = money_flow.loc[money_flow["trade_date"] == latest_date]
        if not matching_money.empty:
            money_latest = matching_money.iloc[-1]
    linkage_latest = pd.DataFrame()
    if not linkage.empty:
        linkage["trade_date"] = pd.to_datetime(linkage["trade_date"]).dt.date
        linkage_latest = linkage.loc[linkage["trade_date"] == latest_date].copy()
    recent = raw.merge(
        features[["trade_date", "ma20", "volume_ratio_20", "rs_20", "trend_state"]],
        on="trade_date", how="left",
    ).tail(20)
    missing = {
        column: int(features[column].isna().sum())
        for column in ["ret_20d", "ma60", "atr14", "range_position_60", "rs_20", "volume_percentile_120"]
    }
    generated_at = datetime.now()
    report_date = as_of or generated_at.date()
    validation = validation or {"status": "not_run", "warnings": [], "errors": []}
    data_sources = [str(raw_latest["source"]), "akshare.stock_zh_index_daily"]
    if not tick_trades.empty:
        data_sources.append(str(tick_trades.iloc[-1]["source"]))
    if not minute_bars.empty:
        data_sources.append(str(minute_bars.iloc[-1]["source"]))
    data_sources = list(dict.fromkeys(data_sources))

    payload = {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "data_as_of": latest_date.isoformat(),
        "data_sources": data_sources,
        "validation": validation,
        "instrument": stock_config.model_dump(),
        "facts": {
            "latest_raw_price": {
                key: _json_value(raw_latest[key])
                for key in ["trade_date", "open", "high", "low", "close", "volume", "amount", "pct_change", "turnover_rate"]
            },
            "returns": {f"ret_{period}d": _json_value(feature_latest[f"ret_{period}d"]) for period in [5, 10, 20]},
            "moving_averages": {f"ma{period}": _json_value(feature_latest[f"ma{period}"]) for period in [5, 10, 20, 60]},
            "ma20_distance": _json_value(feature_latest["dist_ma20"]),
            "range_position_20": _json_value(feature_latest["range_position_20"]),
            "range_position_60": _json_value(feature_latest["range_position_60"]),
            "relative_strength": {f"rs_{period}": _json_value(feature_latest[f"rs_{period}"]) for period in [5, 10, 20]},
            "money_flow": (
                {
                    key: _json_value(money_latest[key])
                    for key in [
                        "tick_count", "total_amount", "net_active_amount",
                        "net_active_ratio", "large_trade_threshold", "large_net_amount",
                        "large_net_ratio",
                        "vwap", "close_vs_vwap", "tail_net_amount",
                        "amount_coverage", "volume_coverage",
                    ]
                }
                if money_latest is not None else None
            ),
            "market_linkage": [
                {
                    "benchmark_code": row["benchmark_code"],
                    "benchmark_name": instrument_names.get(
                        row["benchmark_code"], row["benchmark_code"]
                    ),
                    "excess_ret_20d": _json_value(row["excess_ret_20d"]),
                    "correlation_60d": _json_value(row["correlation_60d"]),
                    "beta_60d": _json_value(row["beta_60d"]),
                    "relationship_state": row["relationship_state"],
                }
                for row in linkage_latest.to_dict(orient="records")
            ],
        },
        "rule_labels": {
            "trend_state": feature_latest["trend_state"],
            "volume_state": feature_latest["volume_state"],
            "location_state": feature_latest["location_state"],
            "relative_strength_state": feature_latest["relative_strength_state"],
            "money_flow_state": (
                money_latest["flow_state"] if money_latest is not None else "missing"
            ),
            "money_flow_confidence": (
                money_latest["confidence"] if money_latest is not None else "missing"
            ),
        },
        "recent_20_trading_days": [
            {key: _json_value(value) for key, value in row.items()}
            for row in recent.to_dict(orient="records")
        ],
        "missing_values_in_full_feature_history": missing,
        "limitations": [
            "状态标签由 settings.yaml 中的透明规则计算，不是人工判断。",
            "数据为公开接口日线，可能存在延迟、停牌缺口或事后修订。",
            "指数接口不提供成交额，因此基准 amount 保留为空。",
            "逐笔买卖方向来自第三方行情分类，只代表成交行为推断，不能识别投资者身份。",
            "市场联动是统计相关关系，不代表因果关系。",
            "本报告不构成买入、卖出或收益承诺。",
        ],
        "manual_review": [
            "结合公司公告、行业信息和风险承受能力复核事实。",
            "检查最新交易日是否已覆盖当前应有的收盘数据。",
            "程序标签只用于整理信息，最终判断由使用者独立完成。",
        ],
    }

    md_lines = [
        f"# {stock_config.name}（{stock_config.full_code}）每日分析包",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 数据截止：{payload['data_as_of']}",
        f"- 数据来源：{', '.join(payload['data_sources'])}",
        f"- 数据校验：{validation.get('status', 'not_run')}",
        "",
        "## 一、事实数据",
        "",
        f"- 最新未复权收盘价：{_number(raw_latest['close'])} 元",
        f"- 当日涨跌幅：{_number(raw_latest['pct_change'])}%",
        f"- 5日 / 10日 / 20日收益：{_percent(feature_latest['ret_5d'])} / {_percent(feature_latest['ret_10d'])} / {_percent(feature_latest['ret_20d'])}",
        f"- MA5 / MA10 / MA20 / MA60：{_number(feature_latest['ma5'])} / {_number(feature_latest['ma10'])} / {_number(feature_latest['ma20'])} / {_number(feature_latest['ma60'])}",
        f"- 相对 MA20：{_percent(feature_latest['dist_ma20'])}",
        f"- 20日 / 60日区间位置：{_percent(feature_latest['range_position_20'])} / {_percent(feature_latest['range_position_60'])}",
        f"- 相对创业板指 5日 / 10日 / 20日强弱：{_percent(feature_latest['rs_5'])} / {_percent(feature_latest['rs_10'])} / {_percent(feature_latest['rs_20'])}",
        "",
        "## 二、逐笔资金行为事实",
        "",
    ]
    if money_latest is None:
        md_lines.append("- 当日逐笔资金行为数据缺失。")
    else:
        md_lines.extend([
            f"- 逐笔记录：{int(money_latest['tick_count']):,} 条",
            f"- 逐笔成交额：{_number(money_latest['total_amount'], 0)} 元",
            f"- 主动买卖净额：{_number(money_latest['net_active_amount'], 0)} 元，占比 {_percent(money_latest['net_active_ratio'])}",
            f"- 大额成交阈值：{_number(money_latest['large_trade_threshold'], 0)} 元",
            f"- 大额买卖净额：{_number(money_latest['large_net_amount'], 0)} 元",
            f"- 大额买卖净额占全天成交额：{_percent(money_latest['large_net_ratio'])}",
            f"- VWAP：{_number(money_latest['vwap'], 3)} 元，收盘相对VWAP {_percent(money_latest['close_vs_vwap'])}",
            f"- 尾盘主动净额：{_number(money_latest['tail_net_amount'], 0)} 元",
            f"- 日线成交额 / 成交量覆盖率：{_percent(money_latest['amount_coverage'])} / {_percent(money_latest['volume_coverage'])}",
        ])
    md_lines.extend([
        "",
        "## 三、市场联动",
        "",
        "| 指数 | 20日超额收益 | 60日相关性 | 60日Beta | 关系标签 |",
        "|---|---:|---:|---:|---|",
    ])
    for row in linkage_latest.itertuples():
        md_lines.append(
            f"| {instrument_names.get(row.benchmark_code, row.benchmark_code)} | "
            f"{_percent(row.excess_ret_20d)} | {_number(row.correlation_60d)} | "
            f"{_number(row.beta_60d)} | {row.relationship_state} |"
        )
    md_lines.extend([
        "",
        "## 四、程序规则标签",
        "",
        "> 以下标签由固定阈值自动计算，不是投资建议。",
        "",
        f"- 趋势：`{feature_latest['trend_state']}`",
        f"- 量能：`{feature_latest['volume_state']}`",
        f"- 位置：`{feature_latest['location_state']}`",
        f"- 相对强弱：`{feature_latest['relative_strength_state']}`",
        f"- 逐笔资金行为：`{money_latest['flow_state'] if money_latest is not None else 'missing'}`",
        f"- 资金结论置信度：`{money_latest['confidence'] if money_latest is not None else 'missing'}`",
        "",
        "## 五、最近20个交易日简表",
        "",
        "| 日期 | 收盘 | 涨跌幅(%) | MA20 | 20日量比 | 20日相对强弱 | 趋势标签 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in recent.itertuples():
        md_lines.append(
            f"| {row.trade_date} | {_number(row.close)} | {_number(row.pct_change)} | "
            f"{_number(row.ma20)} | {_number(row.volume_ratio_20)} | {_percent(row.rs_20)} | {row.trend_state or '缺失'} |"
        )
    md_lines.extend([
        "",
        "## 六、数据缺失情况",
        "",
        *[f"- {key}：{value} 行为空（历史窗口不足属于正常情况）" for key, value in missing.items()],
        "",
        "## 七、后续人工判断",
        "",
        *[f"- {item}" for item in payload["manual_review"]],
        "",
        "## 八、模型和数据限制",
        "",
        *[f"- {item}" for item in payload["limitations"]],
        "",
    ])
    markdown = "\n".join(md_lines)
    context_dir: Path = settings["resolved_paths"]["context_pack"]
    daily_dir: Path = settings["resolved_paths"]["reports_daily"]
    context_dir.mkdir(parents=True, exist_ok=True)
    daily_dir.mkdir(parents=True, exist_ok=True)
    report_prefix = f"{report_date.isoformat()}_{stock_config.code}"
    markdown_path = context_dir / f"{report_prefix}_context_pack.md"
    json_path = context_dir / f"{report_prefix}_context_pack.json"
    daily_path = daily_dir / f"{report_prefix}_daily_summary.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    daily_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return markdown_path, json_path, daily_path
