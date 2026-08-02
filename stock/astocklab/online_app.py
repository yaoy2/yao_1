from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.reporting.ai_chain_panel import render_ai_chain_panel
from src.reporting.context_pack import build_context_pack
from src.reporting.intraday_chart import (
    make_intraday_figure,
    make_money_flow_intraday_figure,
    prepare_intraday_comparison,
    symmetric_pct_range,
)
from src.reporting.prediction_panel import render_prediction_panel
from src.storage.database import Database
from src.utils.config import load_ai_chain, load_settings, load_watchlist
from stock.runtime import materialize_astocklab_database, online_validation_path


st.title("AStockLab 个股跟踪系统")
st.caption("日线、分时、资金行为、概率研究与 AI 产业链只读展示，不构成投资建议")

settings = load_settings()
watchlist = load_watchlist()
ai_chain_config = load_ai_chain()


@st.cache_resource
def load_database() -> Database:
    """Materialize the verified online snapshot and reuse its DB gateway."""
    result = Database(path=materialize_astocklab_database())
    result.initialize()
    return result


database = load_database()
stocks = [stock for stock in watchlist.stocks if stock.enabled]
selected = st.sidebar.radio(
    "选择个股",
    stocks,
    format_func=lambda item: f"{item.name}（{item.code}）",
)
st.sidebar.caption("选择股票后页面读取同一份只读在线快照。")
prediction_settings = settings.get("prediction", {})
prediction_enabled = bool(prediction_settings.get("enabled", False))
show_prediction = False
if prediction_enabled:
    st.sidebar.divider()
    show_prediction = st.sidebar.toggle(
        "显示概率预测",
        value=bool(prediction_settings.get("show_in_ui_default", False)),
        help="只控制本次页面是否展示；不会触发模型运行或自动交易。",
    )
    st.sidebar.caption("默认隐藏。结果需先运行 run_predictions.bat 生成。")

raw = database.get_stock_bars(selected.code, "raw")
qfq = database.get_stock_bars(selected.code, "qfq")
features = database.get_features(selected.code)
linkage = database.get_linkage_features(selected.code)
money_flow = database.get_money_flow(selected.code)
minute_bars = database.get_minute_bars(selected.code)
tick_trades = database.get_tick_trades(selected.code)
for frame in (raw, qfq, features, linkage, money_flow, tick_trades):
    if not frame.empty:
        if "trade_date" in frame:
            frame["trade_date"] = pd.to_datetime(frame["trade_date"])
if not minute_bars.empty:
    minute_bars["trade_datetime"] = pd.to_datetime(minute_bars["trade_datetime"])

benchmark_order = ["000001", "399001", "399006", "000680"]
benchmark_lookup = {
    benchmark.code: benchmark
    for benchmark in watchlist.benchmarks
    if benchmark.enabled
}
comparison_benchmarks = [
    benchmark_lookup[code]
    for code in benchmark_order
    if code in benchmark_lookup
]
comparison_items = [*comparison_benchmarks, *stocks]
comparison_frames = {
    item.code: database.get_minute_bars(item.code)
    for item in comparison_items
}

(
    overview_tab,
    prediction_tab,
    intraday_compare_tab,
    stock_analysis_tab,
    market_linkage_tab,
    ai_chain_tab,
    money_flow_tab,
    data_table_tab,
    daily_report_tab,
    data_health_tab,
) = st.tabs([
    "自选股总览", "概率预测", "分时对比", "单股分析", "市场联动",
    "AI产业链", "资金行为", "数据表", "每日摘要", "数据健康",
])

with overview_tab:
    if raw.empty or features.empty:
        st.warning("本地行情或特征数据为空，请先运行 run_daily.bat 或历史回填脚本。")
    else:
        latest_raw = raw.iloc[-1]
        latest_feature = features.iloc[-1]
        st.subheader(f"{selected.name}（{selected.full_code}）")
        cols = st.columns(5)
        cols[0].metric("最新交易日", latest_raw["trade_date"].date().isoformat())
        cols[1].metric("收盘价", f"{latest_raw['close']:.2f}")
        cols[2].metric("当日涨跌幅", f"{latest_raw['pct_change']:.2f}%")
        cols[3].metric("5日收益", f"{latest_feature['ret_5d']:.2%}" if pd.notna(latest_feature["ret_5d"]) else "缺失")
        cols[4].metric("20日收益", f"{latest_feature['ret_20d']:.2%}" if pd.notna(latest_feature["ret_20d"]) else "缺失")
        st.dataframe(pd.DataFrame([{
            "10日收益": latest_feature["ret_10d"],
            "MA5": latest_feature["ma5"],
            "MA10": latest_feature["ma10"],
            "MA20": latest_feature["ma20"],
            "MA60": latest_feature["ma60"],
            "相对MA20": latest_feature["dist_ma20"],
            "量能状态": latest_feature["volume_state"],
            "趋势状态": latest_feature["trend_state"],
            "相对创业板指": latest_feature["relative_strength_state"],
            "数据更新时间": latest_feature["calculated_at"],
        }]), width="stretch", hide_index=True)
        st.info("趋势、量能、位置和相对强弱均为程序规则标签。")

with prediction_tab:
    render_prediction_panel(
        stock=selected,
        qfq=qfq,
        prediction_path=settings["resolved_paths"]["predictions"],
        show_prediction=show_prediction,
    )

with intraday_compare_tab:
    st.subheader("当日市场与个股分时对比")
    st.caption(
        "全部图表以各自昨收为0%，并使用上下对称的涨跌幅范围；"
        "左轴为价格、右轴为涨跌幅，按A股习惯红涨绿跌。"
        "这样比较的是走势强弱和节奏，不会被指数点位或股价绝对值误导。"
    )
    (
        comparison_date,
        prepared_frames,
        _shared_y_range,
        missing_codes,
        stale_codes,
    ) = prepare_intraday_comparison(comparison_frames)
    item_names = {item.code: item.name for item in comparison_items}
    if missing_codes:
        missing_names = [
            f"{item_names.get(code, code)}（{code}）"
            for code in missing_codes
        ]
        st.warning(
            "以下标的尚无分钟数据：" + "、".join(missing_names)
            + "。请运行 update_intraday.py --minute-only。"
        )
    elif stale_codes:
        stale_names = [
            f"{item_names.get(code, code)}（{code}）"
            for code in stale_codes
        ]
        st.error(
            "分钟数据没有同步到同一采集时点，本页拒绝混合展示。"
            "落后标的：" + "、".join(stale_names)
            + "。请重新运行 run_intraday.bat；若仍失败请查看日志。"
        )
    elif comparison_date is None:
        st.warning("当前分钟数据没有共同交易日，暂时不能进行同日对比。")
    else:
        latest_minute = max(
            pd.to_datetime(frame["trade_datetime"]).max()
            for frame in prepared_frames.values()
        )
        st.info(
            f"共同交易日：{comparison_date.isoformat()}　"
            f"最新分钟：{latest_minute:%H:%M}　"
            "盘中采集的数据会随采集时间逐步增加。"
        )
        benchmark_y_range = symmetric_pct_range([
            prepared_frames[item.code]
            for item in comparison_benchmarks
        ])
        stock_y_range = symmetric_pct_range([
            prepared_frames[item.code]
            for item in stocks
        ])
        st.markdown("#### 市场指数")
        benchmark_columns = st.columns(4, gap="small")
        for column, benchmark in zip(
            benchmark_columns, comparison_benchmarks
        ):
            with column:
                st.plotly_chart(
                    make_intraday_figure(
                        prepared_frames[benchmark.code],
                        benchmark.name,
                        benchmark_y_range,
                        compact=True,
                    ),
                    width="stretch",
                    config={"displayModeBar": False},
                    key=f"intraday_benchmark_{benchmark.code}",
                )
        st.markdown("#### 自选个股")
        stock_columns = st.columns(len(stocks), gap="medium")
        for column, stock in zip(stock_columns, stocks):
            with column:
                st.plotly_chart(
                    make_intraday_figure(
                        prepared_frames[stock.code],
                        f"{stock.name}（{stock.code}）",
                        stock_y_range,
                        compact=False,
                    ),
                    width="stretch",
                    config={"displayModeBar": False},
                    key=f"intraday_stock_{stock.code}",
                )

with stock_analysis_tab:
    if qfq.empty or features.empty:
        st.warning("没有可绘制的前复权行情或特征数据。")
    else:
        range_choice = st.selectbox("显示范围", [60, 120, 250, "全部"], index=1)
        count = len(qfq) if range_choice == "全部" else int(range_choice)
        chart = qfq.merge(
            features[["trade_date", "ma5", "ma10", "ma20", "ma60"]],
            on="trade_date", how="left",
        ).tail(count)
        figure = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
            row_heights=[0.75, 0.25],
        )
        figure.add_trace(go.Candlestick(
            x=chart["trade_date"], open=chart["open"], high=chart["high"],
            low=chart["low"], close=chart["close"], name="前复权日K",
            increasing={
                "line": {"color": "#d32f2f"},
                "fillcolor": "#d32f2f",
            },
            decreasing={
                "line": {"color": "#16865b"},
                "fillcolor": "#16865b",
            },
        ), row=1, col=1)
        for period, color in [(5, "#f4b400"), (10, "#0f9d58"), (20, "#4285f4"), (60, "#ab47bc")]:
            figure.add_trace(go.Scatter(
                x=chart["trade_date"], y=chart[f"ma{period}"], name=f"MA{period}",
                line={"width": 1.4, "color": color},
            ), row=1, col=1)
        colors = ["#ef5350" if close >= open_ else "#26a69a" for close, open_ in zip(chart["close"], chart["open"])]
        figure.add_trace(go.Bar(
            x=chart["trade_date"], y=chart["volume"], name="成交量",
            marker_color=colors,
        ), row=2, col=1)
        figure.update_layout(
            height=720, xaxis_rangeslider_visible=False, hovermode="x unified",
            margin={"l": 20, "r": 20, "t": 30, "b": 20},
        )
        st.plotly_chart(figure, width="stretch")
        latest = features.iloc[-1]
        label_maps = {
            "trend_state": {
                "strong_up": "强势上涨",
                "up": "上涨趋势",
                "range": "区间震荡",
                "down": "下跌趋势",
                "strong_down": "强势下跌",
                "insufficient_data": "数据不足",
            },
            "volume_state": {
                "high_volume": "明显放量",
                "normal_volume": "量能正常",
                "low_volume": "明显缩量",
                "insufficient_data": "数据不足",
            },
            "location_state": {
                "breakout": "创20日新高",
                "near_high": "接近20日高位",
                "middle": "20日区间中部",
                "near_low": "接近20日低位",
                "breakdown": "创20日新低",
                "insufficient_data": "数据不足",
            },
            "relative_strength_state": {
                "strong": "明显强于基准",
                "neutral": "与基准接近",
                "weak": "明显弱于基准",
                "insufficient_data": "数据不足",
            },
        }
        st.subheader("当前核心特征")
        feature_columns = st.columns(4)
        feature_columns[0].metric(
            "趋势",
            label_maps["trend_state"].get(
                latest["trend_state"], "未知"
            ),
        )
        feature_columns[1].metric(
            "量能",
            label_maps["volume_state"].get(
                latest["volume_state"], "未知"
            ),
        )
        feature_columns[2].metric(
            "20日位置",
            label_maps["location_state"].get(
                latest["location_state"], "未知"
            ),
        )
        feature_columns[3].metric(
            "相对基准强弱",
            label_maps["relative_strength_state"].get(
                latest["relative_strength_state"], "未知"
            ),
        )
        numeric_columns = st.columns(2)
        numeric_columns[0].metric(
            "ATR14占收盘价",
            (
                "数据不足"
                if pd.isna(latest["atr14_pct"])
                else f"{float(latest['atr14_pct']):.2%}"
            ),
            help="近14日真实波幅相对当前收盘价，数值越大表示近期波动越剧烈。",
        )
        numeric_columns[1].metric(
            "20日区间位置",
            (
                "数据不足"
                if pd.isna(latest["range_position_20"])
                else f"{float(latest['range_position_20']):.1%}"
            ),
            help="0%接近20日最低，100%接近20日最高。",
        )

with market_linkage_tab:
    st.subheader("个股与主要市场指数联动")
    st.caption("联动指标是统计关系，不代表指数变化导致个股变化。")
    if linkage.empty:
        st.warning("尚无市场联动特征，请运行日更流程。")
    else:
        benchmark_names = {
            item.code: item.name for item in watchlist.benchmarks
        }
        latest_linkage = (
            linkage.sort_values("trade_date")
            .groupby("benchmark_code", as_index=False)
            .tail(1)
            .copy()
        )
        latest_linkage["指数"] = latest_linkage["benchmark_code"].map(
            benchmark_names
        ).fillna(latest_linkage["benchmark_code"])
        state_names = {
            "outperforming": "个股明显跑赢",
            "underperforming": "个股明显跑输",
            "coupled": "高度联动",
            "decoupled": "低度联动",
            "neutral": "中性",
            "insufficient_data": "数据不足",
        }
        latest_linkage["关系"] = latest_linkage["relationship_state"].map(
            state_names
        ).fillna(latest_linkage["relationship_state"])
        market_display = latest_linkage[[
            "指数", "excess_ret_5d", "excess_ret_20d",
            "correlation_60d", "beta_60d", "关系",
        ]].rename(columns={
                "excess_ret_5d": "5日超额收益",
                "excess_ret_20d": "20日超额收益",
                "correlation_60d": "60日相关性",
                "beta_60d": "60日Beta",
            })
        for column in [
            "5日超额收益", "20日超额收益",
        ]:
            market_display[column] = market_display[column].map(
                lambda value: "—" if pd.isna(value) else f"{value:.2%}"
            )
        for column in ["60日相关性", "60日Beta"]:
            market_display[column] = market_display[column].map(
                lambda value: "—" if pd.isna(value) else f"{value:.2f}"
            )
        st.dataframe(
            market_display,
            width="stretch",
            hide_index=True,
        )
        normalized = go.Figure()
        stock_chart = qfq.tail(120).copy()
        if not stock_chart.empty:
            stock_chart["normalized"] = stock_chart["close"] / stock_chart["close"].iloc[0] * 100
            normalized.add_trace(go.Scatter(
                x=stock_chart["trade_date"], y=stock_chart["normalized"],
                name=selected.name, line={"width": 3},
            ))
            start_date = stock_chart["trade_date"].min()
            for benchmark in watchlist.enabled_benchmarks_for(selected):
                benchmark_bars = database.get_benchmark_bars(benchmark.code)
                if benchmark_bars.empty:
                    continue
                benchmark_bars["trade_date"] = pd.to_datetime(benchmark_bars["trade_date"])
                benchmark_bars = benchmark_bars.loc[
                    benchmark_bars["trade_date"] >= start_date
                ].tail(120)
                if benchmark_bars.empty:
                    continue
                benchmark_bars["normalized"] = (
                    benchmark_bars["close"] / benchmark_bars["close"].iloc[0] * 100
                )
                normalized.add_trace(go.Scatter(
                    x=benchmark_bars["trade_date"],
                    y=benchmark_bars["normalized"],
                    name=benchmark.name,
                    line={"width": 1.5},
                ))
        normalized.update_layout(
            title="最近120个交易日归一化走势（起点=100）",
            height=480,
            hovermode="x unified",
            margin={"l": 20, "r": 20, "t": 50, "b": 20},
        )
        st.plotly_chart(normalized, width="stretch")

with ai_chain_tab:
    render_ai_chain_panel(database, ai_chain_config)

with money_flow_tab:
    st.subheader("逐笔成交与资金行为观察")
    st.warning(
        "买盘、卖盘来自第三方行情分类，只表示成交行为推断，"
        "不能确认基金、游资或具体投资者身份。"
    )
    if money_flow.empty:
        st.info(
            "尚无通过日线核验的逐笔资金行为数据。"
            "请在收盘后运行 run_daily.bat；run_intraday.bat 只更新分钟线，"
            "不会生成资金行为。"
        )
    else:
        latest_money = money_flow.sort_values("trade_date").iloc[-1]
        flow_names = {
            "strong_inflow": "明显主动流入",
            "inflow": "主动流入偏多",
            "balanced": "买卖相对均衡",
            "outflow": "主动流出偏多",
            "strong_outflow": "明显主动流出",
            "buying_without_price_response": "买入较多但价格未响应",
            "selling_absorbed": "卖出较多但价格有承接",
        }
        cols = st.columns(5)
        cols[0].metric("资金行为", flow_names.get(
            latest_money["flow_state"], latest_money["flow_state"]
        ))
        cols[1].metric("置信度", str(latest_money["confidence"]).upper())
        cols[2].metric("主动买卖净额", f"{latest_money['net_active_amount'] / 10000:,.0f} 万元")
        cols[3].metric("大额买卖净额", f"{latest_money['large_net_amount'] / 10000:,.0f} 万元")
        cols[4].metric("收盘相对VWAP", f"{latest_money['close_vs_vwap']:.2%}")
        reconciliation_details = {
            "交易日期": latest_money["trade_date"].date().isoformat(),
            "逐笔记录数": int(latest_money["tick_count"]),
            "逐笔成交额": f"{latest_money['total_amount']:,.0f} 元",
            "主动净额占比": f"{latest_money['net_active_ratio']:.2%}",
            "大额成交阈值（当日前5%）": f"{latest_money['large_trade_threshold']:,.0f} 元",
            "大额净额占全天成交额": f"{latest_money['large_net_ratio']:.2%}",
            "VWAP": f"{latest_money['vwap']:.3f} 元",
            "尾盘主动净额": f"{latest_money['tail_net_amount']:,.0f} 元",
            "成交额覆盖率": f"{latest_money['amount_coverage']:.4%}",
            "成交量覆盖率": f"{latest_money['volume_coverage']:.4%}",
        }
        with st.expander("查看资金计算与日线核验明细"):
            st.dataframe(
                pd.DataFrame(
                    [(key, str(value)) for key, value in reconciliation_details.items()],
                    columns=["项目", "结果"],
                ),
                width="stretch",
                hide_index=True,
            )
        if not minute_bars.empty:
            latest_day = latest_money["trade_date"].date()
            minute_day = minute_bars.loc[
                minute_bars["trade_datetime"].dt.date == latest_day
            ].copy()
            previous_daily = raw.loc[
                raw["trade_date"].dt.date < latest_day
            ].sort_values("trade_date")
            if minute_day.empty:
                st.warning(
                    f"{latest_day} 的资金特征存在，但缺少同日分钟行情，"
                    "暂时不能绘制资金行为分时图。"
                )
            elif previous_daily.empty:
                st.warning("缺少前一交易日收盘价，暂时不能绘制资金行为分时图。")
            else:
                intraday = make_money_flow_intraday_figure(
                    minute_day,
                    float(previous_daily.iloc[-1]["close"]),
                    float(latest_money["vwap"]),
                    f"{latest_day} 分钟价格与成交额",
                )
                st.plotly_chart(intraday, width="stretch")
        if not tick_trades.empty:
            latest_tick_date = tick_trades["trade_date"].dt.date.max()
            tick_day = tick_trades.loc[
                tick_trades["trade_date"].dt.date == latest_tick_date
            ].copy()
            threshold = tick_day["amount"].quantile(0.95)
            large_ticks = tick_day.loc[tick_day["amount"] >= threshold].copy()
            side_names = {"buy": "买盘", "sell": "卖盘", "neutral": "中性"}
            large_ticks["方向"] = large_ticks["side"].map(side_names).fillna("未知")
            st.subheader("当日大额成交明细（单笔金额前5%）")
            st.dataframe(
                large_ticks.sort_values("amount", ascending=False).head(100)[[
                    "trade_time", "price", "volume_lots", "amount", "方向"
                ]].rename(columns={
                    "trade_time": "时间", "price": "价格",
                    "volume_lots": "成交量（手）", "amount": "成交金额",
                }),
                width="stretch",
                hide_index=True,
            )

with data_table_tab:
    if raw.empty:
        st.warning("没有可展示的数据。")
    else:
        table = raw.merge(
            features[["trade_date", "ma20", "volume_ratio_20", "rs_20"]],
            on="trade_date", how="left",
        ).tail(60)
        display = table[[
            "trade_date", "open", "high", "low", "close", "volume", "amount",
            "pct_change", "turnover_rate", "ma20", "volume_ratio_20", "rs_20",
        ]].rename(columns={
            "trade_date": "日期", "open": "开盘", "high": "最高", "low": "最低",
            "close": "收盘", "volume": "成交量", "amount": "成交额",
            "pct_change": "涨跌幅(%)", "turnover_rate": "换手率(%)",
            "ma20": "MA20", "volume_ratio_20": "20日量比", "rs_20": "20日相对强弱",
        })
        st.dataframe(display.sort_values("日期", ascending=False), width="stretch", hide_index=True)
        st.download_button(
            "下载最近60日 CSV",
            display.to_csv(index=False, encoding="utf-8-sig"),
            file_name=f"{selected.code}_latest_60.csv",
            mime="text/csv",
        )

with daily_report_tab:
    validation_path = online_validation_path()
    validation = (
        json.loads(validation_path.read_text(encoding="utf-8"))
        if validation_path.exists() else {"status": "not_run", "warnings": [], "errors": []}
    )
    if st.button(
        "在线快照不重新生成分析包",
        disabled=True,
        help="请在本地 AStockLab 更新并校验后，再同步新的在线快照。",
    ):
        try:
            markdown_path, _, _ = build_context_pack(database, selected, validation)
            st.success(f"已生成：{markdown_path}")
        except Exception as exc:
            st.error(f"生成失败：{exc}")
    reports = sorted(
        settings["resolved_paths"]["context_pack"].glob(
            f"*_{selected.code}_context_pack.md"
        ),
        reverse=True,
    )
    if reports:
        st.markdown(reports[0].read_text(encoding="utf-8"))
    else:
        st.info("尚无每日摘要，请先运行 build_context_pack.py。")

with data_health_tab:
    counts = database.counts_and_ranges(selected.code, selected.benchmark_code)
    latest_ingestion = database.latest_ingestion()
    validation_path = online_validation_path()
    validation = (
        json.loads(validation_path.read_text(encoding="utf-8"))
        if validation_path.exists() else {"status": "not_run"}
    )
    st.code(str(database.path))
    health_cols = st.columns(4)
    health_cols[0].metric("数据库大小", (
        f"{database.path.stat().st_size / 1024 / 1024:.2f} MB"
        if database.path.exists() else "0 MB"
    ))
    health_cols[1].metric("最新校验", validation.get("status", "not_run"))
    health_cols[2].metric("资金数据", f"{len(money_flow)} 个交易日")
    health_cols[3].metric("市场联动", f"{len(linkage)} 条")
    health_details = {
        "股票数据起止": f"{counts['raw_start']} 至 {counts['raw_end']}",
        "未复权记录数": counts["raw_count"],
        "前复权记录数": counts["qfq_count"],
        "主基准记录数": counts["benchmark_count"],
        "逐笔成交记录数": len(tick_trades),
        "分钟行情记录数": len(minute_bars),
        "快照校验记录": str(validation_path),
    }
    with st.expander("查看数据覆盖明细", expanded=True):
        st.dataframe(
            pd.DataFrame(
                [(key, str(value)) for key, value in health_details.items()],
                columns=["项目", "结果"],
            ),
            width="stretch",
            hide_index=True,
        )
    if latest_ingestion.empty:
        st.warning("没有抓取运行记录。")
    else:
        st.dataframe(latest_ingestion, width="stretch", hide_index=True)
    if validation.get("errors"):
        st.error("\n".join(validation["errors"]))
    if validation.get("warnings"):
        st.warning("\n".join(validation["warnings"]))
