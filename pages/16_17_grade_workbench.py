from __future__ import annotations

import os
import sys
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.grade_workbench_export import build_review_workbook
from utils.grade_workbench import (
    GROUP_COLUMNS,
    STUDENT_COLUMNS,
    ScoreSettings,
    calculate_results,
    has_errors,
    normalize_groups,
    normalize_students,
    sync_groups_from_students,
    validate_all,
)
from utils.grade_workbench_db import (
    create_task,
    list_tasks,
    load_audit,
    load_groups,
    load_meta,
    load_settings,
    load_students,
    output_dir,
    save_groups,
    save_input_file,
    save_settings,
    save_students,
)
from utils.ui_theme import render_home_link


st.set_page_config(page_title="教学评分工作台", page_icon="📘", layout="wide")
render_home_link()


def read_roster(uploaded) -> pd.DataFrame:
    if uploaded.name.lower().endswith(".csv"):
        raw = pd.read_csv(uploaded, dtype=str)
    else:
        raw = pd.read_excel(uploaded, dtype=str)
    raw.columns = [str(column).strip() for column in raw.columns]
    aliases = {
        "student_no": ["学号", "学生学号", "student_no", "student id"],
        "name": ["姓名", "学生姓名", "name"],
        "class_name": ["班级", "行政班", "教学班", "class"],
        "group_code": ["小组", "组别", "组号", "小组编号", "group"],
    }
    mapping = {}
    lowered = {column.lower(): column for column in raw.columns}
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate.lower() in lowered:
                mapping[target] = lowered[candidate.lower()]
                break
    missing = [key for key in ("student_no", "name") if key not in mapping]
    if missing:
        raise ValueError("花名册必须至少包含“学号”和“姓名”列。")
    result = pd.DataFrame()
    for target in ("student_no", "name", "class_name", "group_code"):
        result[target] = raw[mapping[target]] if target in mapping else ""
    result["other_score"] = 0.0
    result["coefficient"] = 1.0
    result["individual_adjustment"] = 0.0
    result["adjustment_reason"] = ""
    return normalize_students(result)


def read_group_scores(uploaded) -> pd.DataFrame:
    if uploaded.name.lower().endswith(".csv"):
        raw = pd.read_csv(uploaded)
    else:
        raw = pd.read_excel(uploaded)
    raw.columns = [str(column).strip() for column in raw.columns]
    aliases = {
        "group_code": ["小组编号", "组别", "组号", "小组", "group_code", "group_name"],
        "project_name": ["项目名称", "报告标题", "project_name", "title"],
        "pitch_score": ["路演原始分", "路演分", "项目路演", "pitch_score", "roadshow"],
        "report_score": ["报告原始分", "报告分", "创业计划书", "report_score", "business_plan"],
        "group_adjustment": ["小组调整", "小组加减分", "group_adjustment"],
        "adjustment_reason": ["调整原因", "group_adjustment_reason"],
        "score_comment": ["评分评语", "简单评语", "评语", "score_comment", "comment"],
    }
    lowered = {column.lower(): column for column in raw.columns}
    mapping = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate.lower() in lowered:
                mapping[target] = lowered[candidate.lower()]
                break
    if "group_code" not in mapping:
        raise ValueError("评分表必须包含“小组编号、组别或组号”列。")
    result = pd.DataFrame()
    for target in GROUP_COLUMNS:
        if target in mapping:
            result[target] = raw[mapping[target]]
        elif target in {"pitch_score", "report_score"}:
            result[target] = None
        elif target == "group_adjustment":
            result[target] = 0.0
        else:
            result[target] = ""
    return normalize_groups(result)


def editor_config_students() -> dict:
    return {
        "student_no": st.column_config.TextColumn("学号", required=True),
        "name": st.column_config.TextColumn("姓名", required=True),
        "class_name": st.column_config.TextColumn("班级"),
        "group_code": st.column_config.TextColumn("小组编号", required=True),
        "other_score": st.column_config.NumberColumn("其他考核成绩", min_value=0.0, max_value=100.0, step=1.0),
        "coefficient": st.column_config.NumberColumn("个人贡献系数", min_value=0.0, max_value=2.0, step=0.05, format="%.2f"),
        "individual_adjustment": st.column_config.NumberColumn("个人加减分", step=1.0),
        "adjustment_reason": st.column_config.TextColumn("个人调整原因"),
    }


def editor_config_groups() -> dict:
    return {
        "group_code": st.column_config.TextColumn("小组编号", disabled=True),
        "project_name": st.column_config.TextColumn("项目名称"),
        "pitch_score": st.column_config.NumberColumn("路演原始分", min_value=0.0, max_value=100.0, step=1.0),
        "report_score": st.column_config.NumberColumn("报告原始分", min_value=0.0, max_value=100.0, step=1.0),
        "group_adjustment": st.column_config.NumberColumn("小组加减分", step=1.0),
        "adjustment_reason": st.column_config.TextColumn("小组调整原因"),
        "score_comment": st.column_config.TextColumn("报告评分评语"),
    }


st.title("教学评分工作台")
st.caption("原始小组分、个人贡献折算和最终调整分开保存；校验通过后再导出。")

tasks = list_tasks()
if not tasks:
    st.subheader("先创建第一个评分任务")
    st.write("每个班级或教学批次单独建一个任务，花名册、评分、调整记录和导出文件不会互相混在一起。")
    step1, step2, step3 = st.columns(3)
    step1.info("① 创建任务\n\n填写学期、课程和任务名称")
    step2.info("② 导入资料\n\n上传花名册和小组评分表")
    step3.info("③ 审核导出\n\n校验通过后生成审核工作簿")
    with st.form("create_first_task"):
        task_name = st.text_input("任务名称", placeholder="例如：2026春季内班评分")
        term = st.text_input("学期", value="2025-2026学年第2学期")
        course = st.text_input("课程", value="从非商业计划到商业计划")
        submitted = st.form_submit_button("创建并进入评分任务", type="primary", use_container_width=True)
        if submitted:
            if not task_name.strip():
                st.error("请填写任务名称。")
            else:
                created = create_task(task_name, term, course)
                st.session_state["active_task"] = created
                st.rerun()
    st.stop()

with st.sidebar:
    st.header("评分任务")
    with st.expander("新建其他任务"):
        with st.form("create_additional_task"):
            task_name = st.text_input("任务名称", placeholder="例如：2026春季内班评分")
            term = st.text_input("学期", value="2025-2026学年第2学期")
            course = st.text_input("课程", value="从非商业计划到商业计划")
            submitted = st.form_submit_button("创建任务", type="primary")
            if submitted:
                if not task_name.strip():
                    st.error("请填写任务名称。")
                else:
                    created = create_task(task_name, term, course)
                    st.session_state["active_task"] = created
                    st.rerun()

    tasks = list_tasks()
    labels = {item["task_id"]: item.get("name", item["task_id"]) for item in tasks}
    task_ids = list(labels)
    active = st.session_state.get("active_task", task_ids[0])
    if active not in task_ids:
        active = task_ids[0]
    task_id = st.selectbox("当前任务", task_ids, index=task_ids.index(active), format_func=lambda value: labels[value])
    st.session_state["active_task"] = task_id

meta = load_meta(task_id)
settings = load_settings(task_id)
students = load_students(task_id)
groups = sync_groups_from_students(students, load_groups(task_id))
if set(groups["group_code"]) != set(load_groups(task_id)["group_code"]):
    save_groups(task_id, groups, "同步学生分组")

top1, top2, top3, top4 = st.columns(4)
top1.metric("学生", len(students))
top2.metric("小组", len(groups))
top3.metric("统一调整", f"{settings.global_adjustment:+g}")
validation = validate_all(students, groups, settings)
top4.metric("当前状态", "有错误" if has_errors(validation) else "可审核")

tab_setup, tab_students, tab_groups, tab_results, tab_export = st.tabs([
    "① 任务与规则", "② 学生与个人调整", "③ 小组原始评分", "④ 成绩审核", "⑤ 导出与记录"
])

with tab_setup:
    st.subheader("导入花名册")
    st.write("支持 `.xlsx` 和 `.csv`。至少需要“学号、姓名”两列；若有班级和小组列会自动识别。")
    uploaded = st.file_uploader("选择花名册", type=["xlsx", "csv"], key=f"roster-{task_id}")
    if uploaded and st.button("导入并替换当前花名册", type="primary"):
        try:
            payload = uploaded.getvalue()
            roster_copy = BytesIO(payload)
            roster_copy.name = uploaded.name
            roster = read_roster(roster_copy)
            save_input_file(task_id, uploaded.name, payload)
            save_students(task_id, roster, "导入花名册")
            save_groups(task_id, sync_groups_from_students(roster, groups), "按花名册同步小组")
            st.success(f"已导入 {len(roster)} 名学生。")
            st.rerun()
        except Exception as exc:
            st.error(f"导入失败：{exc}")

    st.subheader("成绩计算规则")
    with st.form("settings_form"):
        c1, c2, c3 = st.columns(3)
        other_weight = c1.number_input("其他考核权重", 0.0, 1.0, settings.other_weight, 0.05, format="%.2f")
        pitch_weight = c2.number_input("路演权重", 0.0, 1.0, settings.pitch_weight, 0.05, format="%.2f")
        report_weight = c3.number_input("三级项目报告权重", 0.0, 1.0, settings.report_weight, 0.05, format="%.2f")
        d1, d2, d3 = st.columns(3)
        global_adjustment = d1.number_input("全体统一加减分", value=settings.global_adjustment, step=1.0)
        coefficient_min = d2.number_input("个人系数下限", 0.0, 2.0, settings.coefficient_min, 0.05)
        coefficient_max = d3.number_input("个人系数上限", 0.0, 2.0, settings.coefficient_max, 0.05)
        e1, e2, e3 = st.columns(3)
        rounding_options = ["四舍五入为整数", "保留一位小数", "向下取整"]
        rounding = e1.selectbox("取整方式", rounding_options, index=rounding_options.index(settings.rounding))
        score_floor = e2.number_input("最终成绩下限", 0.0, 100.0, settings.score_floor, 1.0)
        score_cap = e3.number_input("最终成绩上限", 0.0, 100.0, settings.score_cap, 1.0)
        global_adjustment_reason = st.text_input("全体统一调整原因", value=settings.global_adjustment_reason)
        st.caption(f"当前权重合计：{other_weight + pitch_weight + report_weight:.2f}（必须等于 1.00）")
        if st.form_submit_button("保存规则", type="primary"):
            save_settings(task_id, ScoreSettings(
                other_weight=other_weight,
                pitch_weight=pitch_weight,
                report_weight=report_weight,
                global_adjustment=global_adjustment,
                global_adjustment_reason=global_adjustment_reason,
                coefficient_min=coefficient_min,
                coefficient_max=coefficient_max,
                rounding=rounding,
                score_floor=score_floor,
                score_cap=score_cap,
            ))
            st.success("规则已保存，并写入审计日志。")
            st.rerun()

with tab_students:
    st.subheader("学生、分组与个人调整")
    st.info("“其他考核成绩”代表除路演和三级项目报告外的综合成绩；个人加减分不会修改任何小组原始分。")
    edited_students = st.data_editor(
        students,
        column_config=editor_config_students(),
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key=f"students-{task_id}",
    )
    if st.button("保存学生与个人调整", type="primary"):
        try:
            normalized = normalize_students(edited_students)
            save_students(task_id, normalized)
            save_groups(task_id, sync_groups_from_students(normalized, groups), "按学生数据同步小组")
            st.success("学生数据已保存。")
            st.rerun()
        except Exception as exc:
            st.error(f"保存失败：{exc}")

with tab_groups:
    st.subheader("小组原始评分与小组调整")
    st.warning("路演原始分和报告原始分是评分证据。统一、小组、个人加减分均不会回写这两列。")
    score_upload = st.file_uploader("可选：导入小组评分表", type=["xlsx", "csv"], key=f"scores-{task_id}")
    if score_upload and st.button("导入并替换当前小组评分"):
        try:
            payload = score_upload.getvalue()
            score_copy = BytesIO(payload)
            score_copy.name = score_upload.name
            imported_groups = read_group_scores(score_copy)
            save_input_file(task_id, score_upload.name, payload)
            save_groups(task_id, imported_groups, "导入小组评分表")
            st.success(f"已导入 {len(imported_groups)} 个小组的评分记录。")
            st.rerun()
        except Exception as exc:
            st.error(f"导入失败：{exc}")
    edited_groups = st.data_editor(
        groups,
        column_config=editor_config_groups(),
        use_container_width=True,
        hide_index=True,
        disabled=["group_code"],
        key=f"groups-{task_id}",
    )
    if st.button("保存小组评分", type="primary"):
        try:
            save_groups(task_id, normalize_groups(edited_groups))
            st.success("小组原始分与调整记录已分别保存。")
            st.rerun()
        except Exception as exc:
            st.error(f"保存失败：{exc}")

with tab_results:
    settings = load_settings(task_id)
    students = load_students(task_id)
    groups = load_groups(task_id)
    results = calculate_results(students, groups, settings)
    validation = validate_all(students, groups, settings)
    st.subheader("校验摘要")
    if has_errors(validation):
        st.error("存在硬错误。可以继续检查和修改，但不能作为正式成绩。")
    else:
        st.success("硬校验通过。请继续人工复核调整理由和成绩分布。")
    st.dataframe(validation, use_container_width=True, hide_index=True)
    st.subheader("个人成绩计算")
    display_columns = [
        "student_no", "name", "class_name", "group_code", "other_score", "pitch_raw", "report_raw",
        "coefficient", "pitch_personal", "report_personal", "global_adjustment", "group_adjustment",
        "individual_adjustment", "score_before_limit", "final_score",
    ]
    st.dataframe(results[display_columns] if not results.empty else results, use_container_width=True, hide_index=True)
    if not results.empty:
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("平均分", f"{results['final_score'].mean():.2f}")
        s2.metric("最高分", f"{results['final_score'].max():g}")
        s3.metric("最低分", f"{results['final_score'].min():g}")
        s4.metric("不及格人数", int((results["final_score"] < 60).sum()))

with tab_export:
    settings = load_settings(task_id)
    students = load_students(task_id)
    groups = load_groups(task_id)
    results = calculate_results(students, groups, settings)
    validation = validate_all(students, groups, settings)
    audit = load_audit(task_id)
    st.subheader("生成审核工作簿")
    st.write("导出的工作簿会同时保留小组原始分、个人系数、各层调整、最终成绩、校验摘要和审计记录。")
    export_disabled = students.empty
    if st.button("生成审核工作簿", type="primary", disabled=export_disabled):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        status = "有错误_草稿" if has_errors(validation) else "校验通过"
        destination = output_dir(task_id) / f"评分审核工作簿_{status}_{stamp}.xlsx"
        build_review_workbook(destination, meta, settings, students, groups, results, validation, audit)
        st.session_state["last_export"] = str(destination)
        st.success(f"已生成：{destination.name}")
    last_export = st.session_state.get("last_export")
    if last_export:
        path = __import__("pathlib").Path(last_export)
        if path.exists():
            st.download_button(
                "下载最近生成的审核工作簿",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    st.subheader("审计日志")
    st.dataframe(audit, use_container_width=True, hide_index=True)
