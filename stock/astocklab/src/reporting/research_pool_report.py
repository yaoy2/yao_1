from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if value is pd.NA:
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def build_research_pool_markdown(
    audit: pd.DataFrame,
    summary: dict[str, Any],
) -> str:
    ready = audit.loc[audit["selected_for_pilot"]].copy()
    missing = (
        summary["distinct_stock_count"] - summary["stocks_with_qfq_bars"]
    )
    lines = [
        "# AI产业链研究池审计",
        "",
        f"- 共同交易日：{summary['reference_trade_date'] or '无'}",
        f"- 最新成分快照：{summary['latest_snapshot_date']}",
        f"- 成分记录：{summary['membership_rows']} 条",
        f"- 去重股票：{summary['distinct_stock_count']} 只",
        f"- 已有前复权日线：{summary['stocks_with_qfq_bars']} 只",
        f"- 缺少前复权日线：{missing} 只",
        f"- 可用于当期排名：{summary['ranking_ready_count']} 只",
        f"- 可用于较长回测：{summary['backtest_ready_count']} 只",
        f"- 第一批试验池：{summary['selected_for_pilot_count']} 只",
        "",
        "## 剔除原因",
        "",
        "| 原因 | 股票数 |",
        "| --- | ---: |",
    ]
    reason_counts = summary["rejection_reason_counts"]
    if reason_counts:
        for reason, count in sorted(
            reason_counts.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            lines.append(f"| {reason} | {count} |")
    else:
        lines.append("| 无 | 0 |")
    lines.extend([
        "",
        "## 第一批试验池",
        "",
        "| 排名 | 代码 | 名称 | 节点数 | 日线数 | 近期待均成交额 | 回测就绪 |",
        "| ---: | --- | --- | ---: | ---: | ---: | --- |",
    ])
    for row in ready.head(50).itertuples():
        average_amount = float(row.average_amount_recent) / 100_000_000
        lines.append(
            f"| {int(row.pilot_rank)} | {row.stock_code} | "
            f"{row.stock_name} | {int(row.node_count)} | "
            f"{int(row.history_rows)} | {average_amount:.2f}亿 | "
            f"{'是' if row.backtest_ready else '否'} |"
        )
    if len(ready) > 50:
        lines.extend([
            "",
            f"> 表格只展示前50只，完整{len(ready)}只见同名JSON文件。",
        ])
    lines.extend([
        "",
        "## 口径说明",
        "",
        "- 研究池只按数据完整性、更新时间、上市历史和流动性过滤。",
        "- 当前试验池排名不是收益预测排名，不构成选股结论。",
        "- 后续历史回测必须按当时的板块成分快照重建股票池。",
        "- 任何预测模型只有在样本外证明增加横向排名价值后才进入最终结果。",
        "",
    ])
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def write_research_pool_report(
    output_directory: Path,
    audit: pd.DataFrame,
    summary: dict[str, Any],
) -> tuple[Path, Path]:
    date_label = (
        summary["reference_trade_date"]
        or summary["latest_snapshot_date"]
    )
    stem = f"{date_label}_research_pool_audit"
    json_path = output_directory / f"{stem}.json"
    markdown_path = output_directory / f"{stem}.md"
    payload = {
        "schema_version": 1,
        "summary": summary,
        "stocks": _records(audit),
    }
    _atomic_write(
        json_path,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    _atomic_write(
        markdown_path,
        build_research_pool_markdown(audit, summary),
    )
    _atomic_write(
        output_directory / "latest.json",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    _atomic_write(
        output_directory / "latest.md",
        build_research_pool_markdown(audit, summary),
    )
    return json_path, markdown_path
