from __future__ import annotations

import re
from typing import Any

import pandas as pd
import streamlit as st

from src.reporting.ai_chain_chart import make_kline_figure
from src.reporting.intraday_chart import (
    add_a_share_session_minute,
    make_intraday_figure,
    prepare_intraday_comparison,
    symmetric_pct_range,
)


STAGE_LABELS = {
    "upstream": "AI上游",
    "midstream": "AI中游",
    "downstream": "AI下游",
    "application": "AI应用",
}
PATH_COLUMNS = [
    ("stage", "大类"),
    ("industry", "中类"),
    ("subindustry", "细分行业"),
    ("field", "细分领域"),
    ("direction", "细分方向"),
]
PAGE_POOL = "第一页 · AI股票池"
PAGE_COMPANY = "第二页 · 企业与板块"
PAGE_DIRECTION = "第三页 · 方向涨幅榜"
PAGE_OPTIONS = [PAGE_POOL, PAGE_COMPANY, PAGE_DIRECTION]

AI_PROFILE_KEYWORDS = (
    "人工智能", "智能体", "大模型", "算力", "智算", "芯片", "半导体",
    "数据中心", "云计算", "大数据", "数据要素", "机器人", "自动驾驶",
    "智能驾驶", "工业互联网", "光模块", "cpo", "液冷", "语料",
    "多模态", "机器学习", "计算机视觉", "算法",
)
PROFILE_FIELDS = [
    ("主营业务", "main_business"),
    ("产品类型", "product_type"),
    ("产品名称", "product_name"),
    ("经营范围", "business_scope"),
]


def ai_node_catalog(config: Any) -> pd.DataFrame:
    """Build the UI taxonomy from validated config, independent of DB refresh."""
    rows = [{
        "node_id": node.node_id,
        "stage": node.stage,
        "industry": node.industry,
        "subindustry": node.subindustry,
        "field": node.field,
        "direction": node.direction,
        "order_index": node.order,
        "name": node.name,
        "description": node.description,
    } for node in config.nodes if node.enabled]
    stage_order = {name: index for index, name in enumerate(STAGE_LABELS)}
    frame = pd.DataFrame(rows)
    frame["stage_order"] = frame["stage"].map(stage_order)
    return frame.sort_values(
        ["stage_order", "order_index", "node_id"]
    ).reset_index(drop=True)


def prepare_ai_member_table(members: pd.DataFrame) -> pd.DataFrame:
    """Prepare the first-page quote table with explicit display units."""
    if members.empty:
        return pd.DataFrame()
    frame = members.copy()
    frame["stock_code"] = frame["stock_code"].astype(str).str.zfill(6)
    for column in [
        "current_price", "today_high", "today_low", "pct_change",
        "amplitude", "volume", "volume_ratio", "total_market_cap",
        "float_market_cap",
    ]:
        if column not in frame:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return pd.DataFrame({
        "代码": frame["stock_code"],
        "名称": frame["stock_name"],
        "现价": frame["current_price"],
        "今日高点": frame["today_high"],
        "今日低点": frame["today_low"],
        "涨幅": frame["pct_change"],
        "振幅": frame["amplitude"],
        "成交量（万手）": frame["volume"] / 10_000.0,
        "量比": frame["volume_ratio"],
        "总市值（亿元）": frame["total_market_cap"] / 100_000_000.0,
        "流通市值（亿元）": frame["float_market_cap"] / 100_000_000.0,
    })


def sort_ai_members_by_pct(members: pd.DataFrame) -> pd.DataFrame:
    """Sort one direction's stocks by daily gain, then source rank."""
    if members.empty:
        return members.copy()
    frame = members.copy()
    frame["pct_change"] = pd.to_numeric(
        frame["pct_change"], errors="coerce"
    )
    if "rank" not in frame:
        frame["rank"] = pd.NA
    return frame.sort_values(
        ["pct_change", "rank"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)


def prioritize_chart_ready_codes(
    codes: list[str],
    ready_codes: list[str],
) -> list[str]:
    """Keep the legacy chart-readiness ordering helper for compatibility."""
    normalized = list(dict.fromkeys(str(code).zfill(6) for code in codes))
    ready = set(str(code).zfill(6) for code in ready_codes)
    return (
        [code for code in normalized if code in ready]
        + [code for code in normalized if code not in ready]
    )


def prepare_direction_ranking(
    nodes: pd.DataFrame,
    daily_by_node: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Calculate each direction's latest close-to-close percentage change."""
    rows: list[dict[str, Any]] = []
    for _, node in nodes.iterrows():
        node_id = str(node["node_id"])
        daily = daily_by_node.get(node_id, pd.DataFrame()).copy()
        pct_change = float("nan")
        trade_date = pd.NaT
        if not daily.empty and "close" in daily:
            daily["trade_date"] = pd.to_datetime(daily["trade_date"])
            daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
            daily = daily.dropna(subset=["trade_date", "close"]).sort_values(
                "trade_date"
            )
            if not daily.empty:
                trade_date = daily.iloc[-1]["trade_date"]
            if len(daily) >= 2 and daily.iloc[-2]["close"] != 0:
                pct_change = (
                    daily.iloc[-1]["close"] / daily.iloc[-2]["close"] - 1
                ) * 100.0
        rows.append({
            "node_id": node_id,
            "细分方向": node["direction"],
            "涨幅": pct_change,
            "细分领域": node["field"],
            "细分行业": node["subindustry"],
            "中类": node["industry"],
            "大类": STAGE_LABELS.get(str(node["stage"]), node["stage"]),
            "行情日期": trade_date,
        })
    return pd.DataFrame(rows).sort_values(
        ["涨幅", "细分方向"], ascending=[False, True], na_position="last"
    ).reset_index(drop=True)


def extract_ai_business_evidence(profile_row: pd.Series) -> list[tuple[str, str]]:
    """Return only profile fields that contain explicit AI-adjacent terms."""
    evidence: list[tuple[str, str]] = []
    for label, column in PROFILE_FIELDS:
        value = profile_row.get(column)
        if pd.isna(value) or not str(value).strip():
            continue
        text = str(value).strip()
        clauses = [part.strip() for part in re.split(r"[。；;]", text)]
        matched = [part for part in clauses if _contains_ai_keyword(part)]
        if matched:
            evidence.append((label, "；".join(matched[:6])))
    return evidence


def _contains_ai_keyword(text: str) -> bool:
    lowered = text.lower()
    if any(keyword in lowered for keyword in AI_PROFILE_KEYWORDS):
        return True
    return re.search(r"(?<![a-z])ai(?![a-z])", lowered) is not None


def _ordered_values(frame: pd.DataFrame, column: str) -> list[str]:
    return frame[column].dropna().astype(str).drop_duplicates().tolist()


def _path_text(node: pd.Series) -> str:
    return " → ".join([
        STAGE_LABELS.get(str(node["stage"]), str(node["stage"])),
        str(node["industry"]),
        str(node["subindustry"]),
        str(node["field"]),
        str(node["direction"]),
    ])


def _select_node(nodes: pd.DataFrame) -> pd.Series:
    filtered = nodes.copy()
    columns = st.columns(len(PATH_COLUMNS), gap="small")
    for column_ui, (column, label) in zip(columns, PATH_COLUMNS, strict=True):
        options = _ordered_values(filtered, column)
        if not options:
            raise ValueError(f"AI分类配置缺少{label}。")
        with column_ui:
            selected = st.selectbox(
                label,
                options,
                format_func=(
                    (lambda value: STAGE_LABELS.get(value, value))
                    if column == "stage" else str
                ),
                key=f"ai_pool_{column}",
            )
        filtered = filtered.loc[filtered[column].astype(str) == selected]
    return filtered.iloc[0]


def _selection_rows(event: Any) -> list[int]:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection", {})
    rows = getattr(selection, "rows", None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows", [])
    if rows:
        return list(rows)
    cells = getattr(selection, "cells", None)
    if cells is None and isinstance(selection, dict):
        cells = selection.get("cells", [])
    return [int(cells[0][0])] if cells else []


def selected_member_row(event: Any) -> int | None:
    """Return the row only when the stock code or name cell was clicked."""
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection", {})
    cells = getattr(selection, "cells", None)
    if cells is None and isinstance(selection, dict):
        cells = selection.get("cells", [])
    if not cells:
        return None
    row_index, column_name = cells[0]
    if str(column_name) not in {"代码", "名称"}:
        return None
    return int(row_index)


def _profile_text(profile_row: pd.Series, column: str, fallback: str = "—") -> str:
    value = profile_row.get(column)
    if value is None or pd.isna(value) or not str(value).strip():
        return fallback
    return str(value).strip()


def _member_table_config() -> dict[str, Any]:
    return {
        "代码": st.column_config.TextColumn(
            "代码", width="small", help="单击代码进入第二页"
        ),
        "名称": st.column_config.TextColumn(
            "名称", width="small", help="单击名称进入第二页"
        ),
        "现价": st.column_config.NumberColumn("现价", format="%.2f"),
        "今日高点": st.column_config.NumberColumn("今日高点", format="%.2f"),
        "今日低点": st.column_config.NumberColumn("今日低点", format="%.2f"),
        "涨幅": st.column_config.NumberColumn("涨幅", format="%.2f%%"),
        "振幅": st.column_config.NumberColumn("振幅", format="%.2f%%"),
        "成交量（万手）": st.column_config.NumberColumn(
            "成交量（万手）", format="%.2f"
        ),
        "量比": st.column_config.NumberColumn("量比", format="%.2f"),
        "总市值（亿元）": st.column_config.NumberColumn(
            "总市值（亿元）", format="%.2f"
        ),
        "流通市值（亿元）": st.column_config.NumberColumn(
            "流通市值（亿元）", format="%.2f"
        ),
    }


def _render_pool_page(database: Any, nodes: pd.DataFrame) -> None:
    st.markdown("### AI产业链分类")
    selected_node = _select_node(nodes)
    st.info(f"{_path_text(selected_node)}｜{selected_node['description']}")

    members = database.get_latest_ai_memberships(str(selected_node["node_id"]))
    st.markdown("### A股标的")
    st.caption("单击股票代码或名称（无需双击），自动进入第二页查看板块和企业资料。")
    if members.empty:
        st.warning("该方向尚无股票池数据，请先运行 run_ai_chain.bat。")
        return
    members["snapshot_date"] = pd.to_datetime(members["snapshot_date"])
    members = sort_ai_members_by_pct(members)
    quote_columns = [
        "current_price", "today_high", "today_low", "pct_change",
        "amplitude", "volume", "volume_ratio", "total_market_cap",
        "float_market_cap",
    ]
    available_columns = [column for column in quote_columns if column in members]
    coverage = (
        members[available_columns].notna().all(axis=1).mean()
        if available_columns else 0.0
    )
    profile_codes = database.get_ai_profile_codes()
    profile_count = members["stock_code"].astype(str).isin(profile_codes).sum()
    summary_columns = st.columns(4)
    summary_columns[0].metric("股票数量", f"{len(members)} 只")
    summary_columns[1].metric(
        "行情日期", members["snapshot_date"].max().date().isoformat()
    )
    summary_columns[2].metric("完整行情覆盖", f"{coverage:.0%}")
    summary_columns[3].metric(
        "企业资料覆盖", f"{profile_count}/{len(members)}"
    )
    if coverage < 1.0:
        st.caption(
            "空白行情字段表示全市场实时快照尚未成功更新；已有成功数据不会被空值覆盖。"
        )

    display = prepare_ai_member_table(members)
    table_epoch = st.session_state.setdefault("ai_pool_table_epoch", 0)
    event = st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=min(620, 38 * len(display) + 40),
        column_config=_member_table_config(),
        on_select="rerun",
        selection_mode="single-cell",
        key=f"ai_pool_members_{selected_node['node_id']}_{table_epoch}",
    )
    selected_row = selected_member_row(event)
    if selected_row is not None:
        selected = members.iloc[selected_row]
        st.session_state["ai_selected_node_id"] = str(selected_node["node_id"])
        st.session_state["ai_selected_stock_code"] = str(
            selected["stock_code"]
        ).zfill(6)
        st.session_state["ai_requested_page"] = PAGE_COMPANY
        st.session_state["ai_nav_epoch"] += 1
        st.session_state["ai_pool_table_epoch"] += 1
        st.rerun()


def _render_sector_charts(database: Any, selected_node: pd.Series) -> None:
    node_id = str(selected_node["node_id"])
    name = str(selected_node["direction"])
    minute_column, daily_column = st.columns(2, gap="large")
    with minute_column:
        st.markdown("#### 板块分时图")
        minute = database.get_ai_sector_minute(node_id)
        if minute.empty:
            st.warning("该板块尚无可用分时数据。")
        else:
            minute["trade_datetime"] = pd.to_datetime(minute["trade_datetime"])
            latest_day = minute["trade_datetime"].dt.date.max()
            minute = minute.loc[
                minute["trade_datetime"].dt.date == latest_day
            ].copy()
            minute["intraday_pct"] = minute["pct_change"] * 100.0
            minute = add_a_share_session_minute(minute)
            st.plotly_chart(
                make_intraday_figure(
                    minute,
                    f"{name}（{latest_day}）",
                    symmetric_pct_range([minute]),
                ),
                width="stretch",
                config={"displayModeBar": False},
            )
    with daily_column:
        st.markdown("#### 板块K线图")
        daily = database.get_ai_sector_daily(node_id)
        if daily.empty:
            st.warning("该板块尚无日K数据。")
        else:
            daily["trade_date"] = pd.to_datetime(daily["trade_date"])
            st.plotly_chart(
                make_kline_figure(daily, f"{name} 日K", height=420),
                width="stretch",
                config={"displayModeBar": False},
            )


def _render_stock_charts(
    database: Any,
    stock_code: str,
    stock_name: str,
) -> None:
    """Render locally cached minute and daily charts for the selected stock."""
    minute_column, daily_column = st.columns(2, gap="large")
    with minute_column:
        st.markdown("#### 个股分时图")
        minute = database.get_minute_bars(stock_code)
        if minute.empty:
            st.warning(
                "本地尚无该股分时数据。请运行 run_ai_chain.bat 分批补齐个股行情后刷新。"
            )
        else:
            (
                latest_day,
                prepared,
                y_range,
                _missing_codes,
                _stale_codes,
            ) = prepare_intraday_comparison({stock_code: minute})
            if latest_day is None or stock_code not in prepared:
                st.warning("该股分钟数据缺少可绘制的共同交易日。")
            else:
                st.plotly_chart(
                    make_intraday_figure(
                        prepared[stock_code],
                        f"{stock_name}（{stock_code}，{latest_day}）",
                        y_range,
                    ),
                    width="stretch",
                    config={"displayModeBar": False},
                    key=f"ai_stock_intraday_{stock_code}",
                )
    with daily_column:
        st.markdown("#### 个股K线图")
        daily = database.get_stock_bars(stock_code, "qfq")
        if daily.empty:
            st.warning(
                "本地尚无该股日K数据。请运行 run_ai_chain.bat 分批补齐个股行情后刷新。"
            )
        else:
            daily["trade_date"] = pd.to_datetime(daily["trade_date"])
            st.plotly_chart(
                make_kline_figure(
                    daily,
                    f"{stock_name}（{stock_code}）前复权日K",
                    height=420,
                ),
                width="stretch",
                config={"displayModeBar": False},
                key=f"ai_stock_daily_{stock_code}",
            )


def _render_company_profile(
    database: Any,
    stock_code: str,
    member: pd.Series | None,
    member_count: int,
) -> None:
    stock_name = str(member.get("stock_name", stock_code)) if member is not None else stock_code
    st.markdown(f"### {stock_name}（{stock_code}）企业介绍")
    profile = database.get_company_business_profile(stock_code)
    if profile.empty:
        st.warning(
            "本地尚无该公司的主营资料。运行 run_ai_chain.bat，并等待窗口明确显示"
            "“AI产业链数据更新完成”后再刷新页面；"
            "当前板块归属不能单独证明公司主营属于 AI。"
        )
    else:
        row = profile.iloc[0]
        main_business = _profile_text(
            row, "main_business", "暂无主营业务说明"
        )
        st.markdown("#### 主营概况")
        st.write(main_business)
        st.markdown("#### AI 相关业务证据")
        evidence = extract_ai_business_evidence(row)
        if evidence:
            for label, text in evidence:
                st.markdown(f"- **{label}：** {text}")
        else:
            st.warning(
                "现有公开主营资料未直接提到 AI 相关业务；这里只能确认其被纳入该概念板块，"
                "不能据此认定 AI 是其主营或核心优势。"
            )
        with st.expander("查看完整主营资料"):
            for label, column in PROFILE_FIELDS:
                st.write(f"**{label}：**", _profile_text(row, column))
            st.caption(
                f"来源：{_profile_text(row, 'source')}　"
                f"采集时间：{_profile_text(row, 'fetched_at')}"
            )

    st.markdown("#### 优势线索（可核验）")
    if member is None:
        st.info("该股票已不在当前最新成员快照中，暂不展示实时优势线索。")
        return
    rank = pd.to_numeric(member.get("rank"), errors="coerce")
    total_cap = pd.to_numeric(member.get("total_market_cap"), errors="coerce")
    volume_ratio = pd.to_numeric(member.get("volume_ratio"), errors="coerce")
    pct_change = pd.to_numeric(member.get("pct_change"), errors="coerce")
    metrics = st.columns(4)
    metrics[0].metric(
        "板块成分位次",
        f"{int(rank)}/{member_count}" if pd.notna(rank) else "—",
    )
    metrics[1].metric(
        "总市值",
        f"{total_cap / 100_000_000:.2f} 亿元" if pd.notna(total_cap) else "—",
    )
    metrics[2].metric(
        "今日涨幅",
        f"{pct_change:.2f}%" if pd.notna(pct_change) else "—",
    )
    metrics[3].metric(
        "量比",
        f"{volume_ratio:.2f}" if pd.notna(volume_ratio) else "—",
    )
    st.caption(
        "以上是板块位次、规模和交易活跃度等可核验线索，不等同于技术壁垒、"
        "持续竞争优势或投资结论。"
    )


def _render_company_page(database: Any, nodes: pd.DataFrame) -> None:
    node_id = st.session_state.get("ai_selected_node_id")
    stock_code = st.session_state.get("ai_selected_stock_code")
    if not node_id or not stock_code:
        st.info("请先到第一页点击一只股票，再查看它所属板块和企业资料。")
        return
    node_matches = nodes.loc[nodes["node_id"].astype(str) == str(node_id)]
    if node_matches.empty:
        st.warning("原选择对应的细分方向已不在当前配置中，请回到第一页重新选择。")
        return
    selected_node = node_matches.iloc[0]
    members = database.get_latest_ai_memberships(str(node_id))
    member_matches = members.loc[
        members["stock_code"].astype(str).str.zfill(6) == str(stock_code).zfill(6)
    ] if not members.empty else pd.DataFrame()
    member = member_matches.iloc[0] if not member_matches.empty else None
    stock_name = str(member["stock_name"]) if member is not None else str(stock_code)
    st.caption(f"当前股票：{stock_name}（{stock_code}）｜所属方向：{_path_text(selected_node)}")
    st.markdown("### 所属板块行情")
    _render_sector_charts(database, selected_node)
    st.divider()
    st.markdown(f"### 所选个股行情：{stock_name}（{stock_code}）")
    _render_stock_charts(database, str(stock_code), stock_name)
    st.divider()
    _render_company_profile(database, str(stock_code), member, len(members))


def _render_direction_members(
    database: Any,
    selected_node: pd.Series,
) -> None:
    node_id = str(selected_node["node_id"])
    direction = str(selected_node["direction"])
    st.markdown(f"### {direction}个股（按涨幅从高到低）")
    st.caption("数据与第一页使用同一份最新板块成分快照；单击股票代码或名称可进入第二页。")
    members = database.get_latest_ai_memberships(node_id)
    if members.empty:
        st.warning("该方向尚无股票池数据，请先运行 run_ai_chain.bat。")
        return
    members["snapshot_date"] = pd.to_datetime(members["snapshot_date"])
    members = sort_ai_members_by_pct(members)
    metrics = st.columns(2)
    metrics[0].metric("股票数量", f"{len(members)} 只")
    metrics[1].metric(
        "行情日期", members["snapshot_date"].max().date().isoformat()
    )
    display = prepare_ai_member_table(members)
    table_epoch = st.session_state.setdefault(
        "ai_direction_members_table_epoch", 0
    )
    event = st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=min(620, 38 * len(display) + 40),
        column_config=_member_table_config(),
        on_select="rerun",
        selection_mode="single-cell",
        key=f"ai_direction_members_{node_id}_{table_epoch}",
    )
    selected_row = selected_member_row(event)
    if selected_row is not None:
        selected = members.iloc[selected_row]
        st.session_state["ai_selected_node_id"] = node_id
        st.session_state["ai_selected_stock_code"] = str(
            selected["stock_code"]
        ).zfill(6)
        st.session_state["ai_requested_page"] = PAGE_COMPANY
        st.session_state["ai_nav_epoch"] += 1
        st.session_state["ai_direction_members_table_epoch"] += 1
        st.rerun()


def _render_direction_page(database: Any, nodes: pd.DataFrame) -> None:
    daily_by_node = {
        str(row["node_id"]): database.get_ai_sector_daily(str(row["node_id"]))
        for _, row in nodes.iterrows()
    }
    ranking = prepare_direction_ranking(nodes, daily_by_node)
    st.markdown("### AI 细分方向涨幅榜")
    st.caption(
        "按每个板块最新两个交易日的收盘价计算涨幅，并从高到低排列。"
        "点击一行查看该方向的股票和图表。"
    )
    display_columns = ["细分方向", "涨幅", "细分领域", "细分行业", "中类", "大类"]
    event = st.dataframe(
        ranking[display_columns],
        width="stretch",
        hide_index=True,
        height=min(620, 38 * len(ranking) + 40),
        column_config={
            "涨幅": st.column_config.NumberColumn("涨幅", format="%.2f%%"),
        },
        on_select="rerun",
        selection_mode="single-cell",
        key="ai_direction_ranking",
    )
    selected_rows = _selection_rows(event)
    if selected_rows:
        st.session_state["ai_rank_selected_node_id"] = str(
            ranking.iloc[selected_rows[0]]["node_id"]
        )
    selected_id = st.session_state.get("ai_rank_selected_node_id")
    if not selected_id:
        st.info("点击上方任意细分方向后，这里将展开该方向股票、板块分时图和 K 线图。")
        return
    matches = nodes.loc[nodes["node_id"].astype(str) == str(selected_id)]
    if matches.empty:
        return
    selected_node = matches.iloc[0]
    st.divider()
    _render_direction_members(database, selected_node)
    st.divider()
    st.markdown(f"### {selected_node['direction']}板块行情")
    _render_sector_charts(database, selected_node)


def render_ai_chain_panel(database: Any, config: Any) -> None:
    """Render the three linked AI pool, company, and direction pages."""
    st.subheader("A股 AI 股票池")
    st.caption(
        "分类由本项目维护；概念板块成员只用于行情观察，不等于公司主营业务属于 AI。"
    )
    nodes = ai_node_catalog(config)
    if nodes.empty:
        st.warning("AI产业链配置为空。")
        return

    st.session_state.setdefault("ai_nav_epoch", 0)
    st.session_state.setdefault("ai_requested_page", PAGE_POOL)
    page = st.segmented_control(
        "页面",
        PAGE_OPTIONS,
        default=st.session_state["ai_requested_page"],
        key=f"ai_page_nav_{st.session_state['ai_nav_epoch']}",
        label_visibility="collapsed",
        width="stretch",
    )
    page = page or PAGE_POOL
    st.session_state["ai_requested_page"] = page
    if page == PAGE_POOL:
        _render_pool_page(database, nodes)
    elif page == PAGE_COMPANY:
        _render_company_page(database, nodes)
    else:
        _render_direction_page(database, nodes)
