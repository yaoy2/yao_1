from __future__ import annotations

import html
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.db import db_session, file_stats, init_db, list_plans, set_plan_approved
from app.openlist_client import OpenListClient
from app.operations import approve_safe_plans
from app.reporting import collect_report, export_reports


st.set_page_config(page_title="115 文件整理系统", page_icon="📁", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 1rem; max-width: 1400px;}
    div[data-testid="stMetric"] {background: #f6f8fb; border: 1px solid #e6ebf2; padding: 8px 10px; border-radius: 8px;}
    .plan-row {display:flex; gap:12px; align-items:flex-start; border:1px solid #e6ebf2; border-radius:8px; padding:8px 10px; margin-bottom:6px; background:#fff;}
    .plan-main {flex: 1 1 auto; min-width: 0;}
    .plan-side {width: 280px; flex: 0 0 280px; font-size: 13px;}
    .name {font-weight: 650; font-size: 14px;}
    .muted {color:#5b6573; font-size:12px;}
    .tag {display:inline-block; padding:1px 6px; border-radius:999px; font-size:11px; margin-right:6px; background:#eef3fb;}
    .tag-low {background:#fff4e5;}
    .tag-medium {background:#eef6ff;}
    .tag-high {background:#e7f8ed;}
    .tag-wait {background:#fdecec;}
    </style>
    """,
    unsafe_allow_html=True,
)


def format_size(num: int | None) -> str:
    value = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return "0 B"


def confidence_class(confidence: str, category: str) -> str:
    if category == "待识别":
        return "tag tag-wait"
    if confidence == "high":
        return "tag tag-high"
    if confidence == "medium":
        return "tag tag-medium"
    return "tag tag-low"


def load_app_settings():
    return load_settings()


def connection_status(settings):
    if not settings.openlist_password or settings.openlist_password == "please-change-me":
        return {
            "reachable": False,
            "logged_in": False,
            "error": "还没有配置只读账号。请先完成 OpenList 授权，再填写 .env。",
            "username": settings.openlist_username,
            "base_path": "",
        }
    try:
        return OpenListClient(settings).ping()
    except Exception as exc:
        return {
            "reachable": False,
            "logged_in": False,
            "error": str(exc),
            "username": settings.openlist_username,
            "base_path": "",
        }


settings = load_app_settings()
init_db(settings.db_path)
status = connection_status(settings)

st.title("115 网盘整理系统")
st.caption("扫描和报告默认只读；真正改名、移动必须使用已批准清单和一次性确认码。删除功能不存在。")

report_snapshot = collect_report(settings)
info_cols = st.columns(7)
with db_session(settings.db_path) as conn:
    stats = file_stats(conn)

info_cols[0].metric("OpenList", "已连接" if status.get("logged_in") else "未连接")
info_cols[1].metric("扫描目录", settings.default_scan_dir)
info_cols[2].metric("文件数", stats["file_count"])
info_cols[3].metric("总容量", format_size(stats["total_size"]))
info_cols[4].metric("待识别", stats["pending_count"])
info_cols[5].metric("最近扫描", (stats["last_scan_time"] or "尚未扫描")[:19])
info_cols[6].metric("重复风险", report_snapshot["duplicate_file_count"])

if status.get("error"):
    st.warning(status["error"])
else:
    st.success(
        f"账号 `{status.get('username')}` 已登录。基本路径：{status.get('base_path') or settings.openlist_mount_path}"
    )

if stats["latest_run"]:
    run = stats["latest_run"]
    native = "有原生 file_id" if run.get("native_file_id_found") else "没有原生 file_id"
    st.caption(
        f"最近一次扫描：{run.get('scan_dir')}，最多 {run.get('max_files')} 个文件，"
        f"文件夹 {run.get('folder_count')}，文件 {run.get('file_count')}，{native}，状态 {run.get('status')}"
    )

cats = stats["categories"] or {}
if cats:
    st.write("分类统计：" + "  ·  ".join(f"{name} {count}" for name, count in sorted(cats.items())))

st.subheader("整理计划")
filter_cols = st.columns([1.2, 1, 1, 2, 1, 1])
category = filter_cols[0].selectbox("分类", ["全部"] + sorted(cats.keys()) if cats else ["全部"])
confidence = filter_cols[1].selectbox("置信度", ["全部", "high", "medium", "low"])
approved = filter_cols[2].selectbox("批准状态", ["全部", "pending", "approved"])
keyword = filter_cols[3].text_input("搜索文件名或路径")

with db_session(settings.db_path) as conn:
    plans = list_plans(
        conn,
        category="" if category == "全部" else category,
        confidence="" if confidence == "全部" else confidence,
        keyword=keyword.strip(),
        approved="" if approved == "全部" else approved,
    )

ids = [row["id"] for row in plans]
if filter_cols[4].button("批准筛选结果", use_container_width=True):
    with db_session(settings.db_path) as conn:
        set_plan_approved(conn, ids, True)
    st.rerun()
if filter_cols[5].button("取消批准", use_container_width=True):
    with db_session(settings.db_path) as conn:
        set_plan_approved(conn, ids, False)
    st.rerun()

# 分页：文件量大时一次渲染全部计划会让页面卡在骨架屏几分钟。
PAGE_SIZES = (50, 200, 1000)
page_state = st.session_state
if "plan_page" not in page_state:
    page_state.plan_page = 0
page_size = filter_cols[3].selectbox(
    "每页条数", PAGE_SIZES, index=0, key="plan_page_size"
)
total = len(plans)
total_pages = max(1, (total + page_size - 1) // page_size)
page_state.plan_page = min(page_state.plan_page, total_pages - 1)
page_start = page_state.plan_page * page_size
plans = plans[page_start : page_start + page_size]

page_cols = st.columns([1, 2, 1])
if page_cols[0].button("上一页", disabled=page_state.plan_page == 0):
    page_state.plan_page -= 1
    st.rerun()
page_cols[1].caption(
    f"第 {page_state.plan_page + 1} / {total_pages} 页，"
    f"显示 {page_start + 1}-{page_start + len(plans)}，共 {total} 条"
)
if page_cols[2].button("下一页", disabled=page_state.plan_page >= total_pages - 1):
    page_state.plan_page += 1
    st.rerun()

action_cols = st.columns([1, 1, 3])
if action_cols[0].button("批准安全候选", use_container_width=True):
    result = approve_safe_plans(settings)
    st.success(f"已批准 {result['approved']} 项；重复、低置信度和待识别项目均已排除。")
    st.rerun()
if action_cols[1].button("生成完整报告", use_container_width=True):
    result = export_reports(settings, ROOT / "reports")
    st.success(f"报告已生成：{result['html']}")
action_cols[2].caption("安全批准只改本地审核状态；生成报告只写本地文件，不会修改115。")

if not plans:
    st.info("还没有整理计划。请先运行最多 50 个文件的扫描。")
else:
    for row in plans:
        approved_label = "已批准" if row["approved"] else "未批准"
        tag_class = confidence_class(row["confidence"], row["category"])
        st.markdown(
            f"""
            <div class="plan-row">
              <div class="plan-main">
                <div class="name">{html.escape(str(row["original_name"]))}
                  <span class="{tag_class}">{html.escape(str(row["category"]))}</span>
                  <span class="tag">{html.escape(str(row["confidence"]))}</span>
                  <span class="tag">{approved_label}</span>
                </div>
                <div class="muted">原路径：{html.escape(str(row["original_path"]))}</div>
                <div class="muted">建议路径：{html.escape(str(row["suggested_path"]))}</div>
              </div>
              <div class="plan-side">
                <div>建议文件名：{html.escape(str(row["suggested_name"]))}</div>
                <div class="muted">{html.escape(str(row["reason"]))}</div>
                <div class="muted">大小 {format_size(row.get("size"))} · 执行状态 {html.escape(str(row["execute_status"]))}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("查看详情 / 单独批准"):
            st.code(row["reason"])
            col_a, col_b = st.columns(2)
            if col_a.button("批准", key=f"ok-{row['id']}"):
                with db_session(settings.db_path) as conn:
                    set_plan_approved(conn, [row["id"]], True)
                st.rerun()
            if col_b.button("取消批准", key=f"no-{row['id']}"):
                with db_session(settings.db_path) as conn:
                    set_plan_approved(conn, [row["id"]], False)
                st.rerun()

st.caption("网页用于查看、批准和生成报告。远程执行必须在操作清单中核对确认码后单独启动。")
