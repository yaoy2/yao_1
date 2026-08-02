from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.prediction.artifacts import load_forecast_artifact
from src.reporting.prediction_chart import (
    make_prediction_figure,
    make_prediction_range_figure,
)


def build_prediction_path_table(
    artifact: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    previous_cumulative = 0.0
    for item in artifact["forecast_path"]:
        cumulative = float(item["median_return"])
        daily_change = (
            (1.0 + cumulative) / (1.0 + previous_cumulative) - 1.0
        )
        rows.append({
            "预测日": f"T+{item['day']}",
            "中位预测价": float(item["median_price"]),
            "单日预测涨跌": daily_change,
            "累计预测涨跌": cumulative,
            "校准下界": float(item["lower_return"]),
            "校准上界": float(item["upper_return"]),
        })
        previous_cumulative = cumulative
    return pd.DataFrame(rows)


def render_prediction_panel(
    *,
    stock: Any,
    qfq: pd.DataFrame,
    prediction_path: str | Path,
    show_prediction: bool,
) -> None:
    st.subheader(f"{stock.name}（{stock.code}）未来数日概率预测")
    st.caption(
        "预测单独集中在本页。侧栏开关只控制结果是否显示，"
        "不会运行模型或触发交易。"
    )
    if not show_prediction:
        st.info("预测结果当前隐藏。请打开左侧“显示概率预测”开关。")
        return

    prediction_root = Path(prediction_path)
    artifact = load_forecast_artifact(
        prediction_root, stock.code
    )
    if artifact is None:
        st.warning(
            "尚未生成该股票的预测结果。请运行 run_predictions.bat；"
            "页面不会自行启动模型。"
        )
        return
    reliability = artifact["reliability"]
    if reliability["status"] == "rejected":
        st.error(reliability["message"])
    else:
        st.warning(reliability["message"])

    as_of_date = artifact["input"]["as_of_trade_date"]
    if qfq.empty:
        st.warning("本地前复权行情为空，无法核对预测是否过期。")
    else:
        latest_qfq_date = qfq["trade_date"].max().date().isoformat()
        if as_of_date != latest_qfq_date:
            st.error(
                f"预测截止 {as_of_date}，本地个股行情已到 "
                f"{latest_qfq_date}；结果已过期，不应继续使用。"
            )

    final_path = artifact["forecast_path"][-1]
    shape_probabilities = artifact["probability"]["shape_probabilities"]
    calibrated_shape, calibrated_probability = max(
        shape_probabilities.items(),
        key=lambda item: item[1],
    )
    raw_shape_probabilities = artifact[
        "probability"
    ]["raw_analog_shape_frequencies"]
    raw_shape, raw_probability = max(
        raw_shape_probabilities.items(),
        key=lambda item: item[1],
    )
    headline_columns = st.columns(4)
    headline_columns[0].metric(
        "T+5中位累计涨跌",
        f"{float(final_path['median_return']):+.2%}",
    )
    headline_columns[1].metric(
        "模型原始主形态",
        raw_shape,
    )
    headline_columns[2].metric(
        "原始路径占比",
        f"{raw_probability:.1%}",
    )
    headline_columns[3].metric(
        "历史校准后最高结果",
        f"{calibrated_shape} {calibrated_probability:.1%}",
    )
    if raw_shape != calibrated_shape:
        st.warning(
            f"模型原始路径集中在“{raw_shape}”（{raw_probability:.1%}），"
            f"但历史校准后最高结果是“{calibrated_shape}”"
            f"（{calibrated_probability:.1%}）。两者方向冲突，说明该模型"
            "过去在相似输出下经常看错，不能把校准结果解释成模型正在看涨。"
        )
    candle_method = (
        "收盘采用模型中位路径，实体和上下影线采用最接近中位路径的"
        "一条完整历史相似样本结构，避免逐项平均成十字星"
    )
    st.info(
        f"图中未来T+1至T+5为概率合成K线：{candle_method}。"
        "半透明预测K线不是确定报价。"
    )
    history_count = st.selectbox(
        "预测图显示多少根前序真实K线",
        [10, 15, 20],
        index=0,
        key=f"prediction_history_count_{stock.code}",
    )
    st.plotly_chart(
        make_prediction_figure(artifact, history_count=history_count),
        width="stretch",
        config={"displayModeBar": False},
        key=f"prediction_path_{stock.code}",
    )
    st.caption(
        "红色K线表示收盘高于开盘，绿色表示收盘低于开盘；"
        "分界线左侧为真实历史，右侧半透明部分为预测。"
        "预测K线形态不代表结果已通过可靠性门槛。"
    )
    st.dataframe(
        build_prediction_path_table(artifact),
        width="stretch",
        hide_index=True,
        column_config={
            "中位预测价": st.column_config.NumberColumn(
                "中位预测价",
                format="%.2f",
            ),
            "单日预测涨跌": st.column_config.NumberColumn(
                "单日预测涨跌",
                format="percent",
            ),
            "累计预测涨跌": st.column_config.NumberColumn(
                "累计预测涨跌",
                format="percent",
            ),
            "校准下界": st.column_config.NumberColumn(
                "校准下界",
                format="percent",
            ),
            "校准上界": st.column_config.NumberColumn(
                "校准上界",
                format="percent",
            ),
        },
    )
    with st.expander("查看宽幅风险区间"):
        st.plotly_chart(
            make_prediction_range_figure(artifact),
            width="stretch",
            config={"displayModeBar": False},
            key=f"prediction_range_{stock.code}",
        )
        st.caption(
            "区间很宽时，表示历史误差大、模型不确定性高；"
            "它会让中位路径在同一尺度下看起来接近水平。"
        )
    validation = artifact["validation"]
    columns = st.columns(5)
    columns[0].metric(
        "历史方向命中",
        f"{validation['direction_accuracy']:.1%}",
    )
    columns[1].metric(
        "简单基线",
        f"{validation['direction_baseline_accuracy']:.1%}",
        delta=f"{validation['direction_edge']:+.1%}",
    )
    columns[2].metric(
        "5日误差",
        f"{validation['mae_final']:.2%}",
        delta=f"技能值 {validation['mae_skill']:+.1%}",
        delta_color="normal",
    )
    columns[3].metric(
        "区间实测覆盖",
        f"{validation['interval_evaluation_coverage']:.1%}",
        delta=f"目标 {validation['interval_target_coverage']:.0%}",
        delta_color="off",
    )
    columns[4].metric(
        "滚动验证次数",
        str(validation["sample_count"]),
    )

    probability_rows = [
        {
            "未来形态": label,
            "模型原始路径占比": raw_shape_probabilities[label],
            "历史校准结果概率": probability,
        }
        for label, probability in shape_probabilities.items()
    ]
    st.dataframe(
        pd.DataFrame(probability_rows),
        width="stretch",
        hide_index=True,
        column_config={
            "模型原始路径占比": st.column_config.ProgressColumn(
                "模型原始路径占比",
                min_value=0.0,
                max_value=1.0,
                format="percent",
            ),
            "历史校准结果概率": st.column_config.ProgressColumn(
                "历史校准结果概率",
                min_value=0.0,
                max_value=1.0,
                format="percent",
            )
        },
    )

    selection = artifact["selection"]
    st.info(selection["market_value_conclusion"])
    with st.expander("查看校准与限制"):
        st.json({
            "预测引擎": artifact["engine"],
            "预测模式": selection["mode"],
            "采用指数": selection["benchmark_name"],
            "输入截止日": as_of_date,
            "历史样本行数": artifact["input"]["history_rows"],
            "相似路径数": artifact["input"]["analog_count"],
            "校准邻居数": artifact[
                "probability"
            ]["calibration_sample_count"],
            "可靠性检查": reliability["checks"],
            "自动交易": "禁止",
        })
    st.caption(
        "中位路径不是目标价；概率来自无未来数据的历史滚动验证与"
        "局部校准。市场制度、题材和突发事件变化会使历史关系失效。"
    )
