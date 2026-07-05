"""第16个项目：小组报告评分与成绩表联动工具。"""

import os
import sys
from io import BytesIO

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import report_grader
from utils.ui_theme import render_home_link


st.set_page_config(page_title="报告评分与成绩表联动", page_icon="🧮", layout="wide")
render_home_link()


DEFAULT_RUBRIC = report_grader.DEFAULT_BUSINESS_PLAN_RUBRIC


def dataframe_download(df: pd.DataFrame, file_name: str, label: str):
    if df.empty:
        return
    st.download_button(
        label,
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=file_name,
        mime="text/csv",
        use_container_width=True,
    )


def reports_to_dataframe(reports):
    return pd.DataFrame(
        [
            {
                "group_name": item.group_name,
                "title": item.title,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "char_count": item.char_count,
                "member_count": len(item.members),
                "review_needed": sum(1 for member in item.members if member.needs_review),
            }
            for item in reports
        ]
    )


def members_to_dataframe(reports):
    rows = []
    for item in reports:
        for member in item.members:
            rows.append(
                {
                    "group_name": member.group_name,
                    "name": member.name,
                    "student_id": member.student_id,
                    "weight": member.weight,
                    "needs_review": member.needs_review,
                }
            )
    return pd.DataFrame(rows)


def group_scores_to_dataframe(group_scores):
    return pd.DataFrame(
        [
            {
                "group_name": item.group_name,
                "report_score": item.report_score,
                "dimension_scores": item.dimension_scores,
                "comment": item.comment,
                "warnings": item.warnings,
            }
            for item in group_scores
        ]
    )


def student_scores_to_dataframe(rows):
    return pd.DataFrame(
        [
            {
                "group_name": row.group_name,
                "name": row.name,
                "student_id": row.student_id,
                "weight": row.weight,
                "group_report_score": row.group_report_score,
                "report_score": row.report_score,
                "needs_review": row.needs_review,
            }
            for row in rows
        ]
    )


def grade_rows_to_dataframe(rows):
    return pd.DataFrame(
        [
            {
                "group_name": row.group_name,
                "name": row.name,
                "student_id": row.student_id,
                "report_score": row.report_score,
                "target_final_score": row.target_final_score,
                "calculated_final_score": row.calculated_final_score,
                "formative_average": row.formative_average,
                "terminal_average": row.terminal_average,
                "classroom": row.classroom,
                "online_test": row.online_test,
                "cost_budget": row.cost_budget,
                "org_risk": row.org_risk,
                "legal_form": row.legal_form,
                "mind_map": row.mind_map,
                "business_canvas": row.business_canvas,
                "marketing_plan": row.marketing_plan,
                "roadshow": row.roadshow,
                "business_plan": row.business_plan,
                "deduction": row.deduction,
                "addition": row.addition,
                "reason": row.reason,
                "warnings": "；".join(row.warnings),
            }
            for row in rows
        ]
    )


def build_adjustment_table(student_df: pd.DataFrame) -> pd.DataFrame:
    if student_df.empty:
        return pd.DataFrame(columns=["student_id", "name", "bonus", "target_final_score", "reason"])
    return pd.DataFrame(
        {
            "student_id": student_df["student_id"],
            "name": student_df["name"],
            "bonus": 0.0,
            "target_final_score": None,
            "reason": "",
        }
    )


def compose_grade_rows(student_df: pd.DataFrame, adjustment_df: pd.DataFrame):
    adjustment_map = {
        str(row["student_id"]).strip(): row
        for _, row in adjustment_df.fillna("").iterrows()
        if str(row.get("student_id", "")).strip()
    }
    rows = []
    for _, student in student_df.iterrows():
        student_id = str(student["student_id"]).strip()
        adjustment = adjustment_map.get(student_id, {})
        bonus = float(adjustment.get("bonus") or 0)
        target = adjustment.get("target_final_score")
        target_score = None if target in ("", None) else float(target)
        reason = str(adjustment.get("reason") or "")
        rows.append(
            report_grader.compose_grade_components(
                student_id=student_id,
                name=student["name"],
                group_name=student["group_name"],
                personal_report_score=float(student["report_score"]),
                bonus=bonus,
                target_final_score=target_score,
                reason=reason,
            )
        )
    return rows


st.title("第16个项目：小组报告评分与成绩表联动")
st.caption("先形成小组报告台账，再联动生成学校成绩总表。旧版 grader 不参与本流程。")

tab_report, tab_gradebook = st.tabs(["报告评分台账", "成绩总表合成"])

with tab_report:
    left, right = st.columns([1.05, 1])
    with left:
        uploaded_md = st.file_uploader("上传汇总 Markdown", type=["md", "txt"])
        rubric = st.text_area("评分标准框架", value=DEFAULT_RUBRIC, height=160)
        parse_clicked = st.button("识别报告与成员权重", type="primary", use_container_width=True)

    if parse_clicked and uploaded_md:
        markdown_text = uploaded_md.read().decode("utf-8-sig", errors="replace")
        st.session_state["report_grader_reports"] = report_grader.split_markdown_reports(markdown_text)
        st.session_state["report_grader_rubric"] = rubric

    reports = st.session_state.get("report_grader_reports", [])
    with right:
        st.metric("已识别报告", len(reports))
        st.metric("已识别成员", sum(len(item.members) for item in reports))
        st.metric("需复核权重", sum(1 for item in reports for member in item.members if member.needs_review))

    if reports:
        report_df = reports_to_dataframe(reports)
        member_df = members_to_dataframe(reports)
        st.dataframe(report_df, use_container_width=True, hide_index=True)
        with st.expander("成员权重识别结果", expanded=False):
            st.dataframe(member_df, use_container_width=True, hide_index=True)
            dataframe_download(member_df, "成员权重识别表.csv", "导出成员权重识别表")

        selected_title = st.selectbox("选择报告生成AI评分提示词", [item.title for item in reports])
        selected_report = next(item for item in reports if item.title == selected_title)
        prompt = report_grader.build_ai_prompt(selected_report, st.session_state.get("report_grader_rubric", rubric))
        st.text_area("AI评分提示词", value=prompt, height=260)

        ai_text = st.text_area(
            "粘贴AI返回的CSV/JSON评分结果",
            height=180,
            placeholder="group_name,report_score,dimension_scores,comment,warnings",
        )
        if st.button("导入AI小组评分", use_container_width=True):
            group_scores = report_grader.parse_group_scores(ai_text)
            st.session_state["report_grader_group_scores"] = group_scores

    group_scores = st.session_state.get("report_grader_group_scores", [])
    if group_scores:
        score_df = group_scores_to_dataframe(group_scores)
        st.subheader("小组报告评分")
        st.dataframe(score_df, use_container_width=True, hide_index=True)
        dataframe_download(score_df, "小组报告评分表.csv", "导出小组报告评分表")

        members = [member for report in reports for member in report.members]
        group_score_map = {score.group_name: score for score in group_scores}
        student_scores = report_grader.build_student_report_scores(group_score_map, members)
        warnings = report_grader.validate_same_weight_scores(student_scores)
        student_df = student_scores_to_dataframe(student_scores)
        st.session_state["report_grader_student_df"] = student_df

        if warnings:
            st.warning("；".join(warnings))
        st.subheader("学生个人报告基础分")
        st.dataframe(student_df, use_container_width=True, hide_index=True)
        dataframe_download(student_df, "学生报告基础分.csv", "导出学生报告基础分")

with tab_gradebook:
    student_df = st.session_state.get("report_grader_student_df", pd.DataFrame())
    if student_df.empty:
        st.info("请先在「报告评分台账」里完成报告拆分、成员权重识别和小组评分导入。")
    else:
        st.subheader("个别加分与最终成绩覆盖")
        default_adjustments = build_adjustment_table(student_df)
        adjustment_df = st.data_editor(
            default_adjustments,
            use_container_width=True,
            hide_index=True,
            column_config={
                "bonus": st.column_config.NumberColumn("bonus", min_value=0.0, max_value=20.0, step=0.5),
                "target_final_score": st.column_config.NumberColumn(
                    "target_final_score（留空=报告分+加分）", min_value=0.0, max_value=100.0, step=0.5
                ),
            },
        )
        grade_rows = compose_grade_rows(student_df, adjustment_df)
        grade_df = grade_rows_to_dataframe(grade_rows)

        mismatch_count = int((grade_df["target_final_score"].round(1) != grade_df["calculated_final_score"].round(1)).sum())
        review_count = int(grade_df["warnings"].astype(str).str.len().gt(0).sum())
        cols = st.columns(4)
        cols[0].metric("学生数", len(grade_df))
        cols[1].metric("平均目标分", f"{grade_df['target_final_score'].mean():.1f}")
        cols[2].metric("公式不一致", mismatch_count)
        cols[3].metric("需关注", review_count)

        if mismatch_count:
            st.warning("存在目标分与公式回算不一致的记录，请检查是否目标分过高或过低。")
        if review_count:
            st.info("部分记录触发配平提醒，可在明细表 warnings 列查看。")

        st.dataframe(grade_df, use_container_width=True, hide_index=True)
        dataframe_download(grade_df, "成绩总表联动明细.csv", "导出成绩总表联动明细")

        template = st.file_uploader("上传学校成绩Excel模板", type=["xlsx"])
        if template and st.button("填入模板并生成Excel", type="primary", use_container_width=True):
            output = report_grader.fill_gradebook_template(template.read(), grade_rows)
            st.download_button(
                "下载已填好的学校成绩表",
                data=output,
                file_name="第16项目_成绩总表.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
