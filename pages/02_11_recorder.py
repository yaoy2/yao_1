import os
import sys
from pathlib import Path

import streamlit as st


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import budget_auth, ding_minutes, github_backup_sync
from utils.ui_theme import render_home_link


st.set_page_config(page_title="Recorder_笔记", page_icon="🎙️", layout="wide")


STATUS_LABELS = {
    "done": "已整理",
    "pending": "待整理",
    "failed": "失败",
}


def apply_style():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.7rem !important;
            padding-bottom: 1.5rem !important;
        }
        .ding-hero {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            gap: 1.25rem;
            margin-bottom: 1.05rem;
        }
        .ding-kicker {
            color: #475467;
            font-size: .82rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: .45rem;
        }
        .ding-title {
            margin: 0;
            color: #182230;
            font-size: 2.2rem;
            line-height: 1.12;
            font-weight: 850;
            letter-spacing: 0;
        }
        .ding-subtitle {
            margin: .45rem 0 0;
            color: #667085;
            font-size: .96rem;
            line-height: 1.7;
        }
        .ding-stat-row {
            display: flex;
            gap: .65rem;
            flex-wrap: wrap;
            justify-content: flex-end;
        }
        .ding-stat {
            min-width: 96px;
            text-align: center;
            padding: .72rem .65rem;
            border: 1px solid rgba(24,34,48,.1);
            border-radius: 8px;
            background: rgba(255,255,255,.8);
            box-shadow: 0 10px 26px rgba(24,34,48,.07);
        }
        .ding-stat b {
            display: block;
            font-size: 1.25rem;
        }
        .ding-stat span {
            color: #667085;
            font-size: .76rem;
        }
        .record-meta {
            color: #667085;
            font-size: .78rem;
            line-height: 1.35;
            margin: .15rem 0 .2rem;
        }
        .record-title-row {
            display: flex;
            align-items: center;
            gap: .55rem;
            flex-wrap: wrap;
            margin-bottom: .2rem;
        }
        .record-title {
            margin: 0;
            color: #182230;
            font-size: 1.08rem;
            line-height: 1.28;
            font-weight: 800;
            letter-spacing: 0;
        }
        .status-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: .16rem .52rem;
            font-size: .76rem;
            font-weight: 800;
            border: 1px solid rgba(24,34,48,.1);
            background: #fff;
        }
        .status-done { color: #166534; background: #f0fdf4; }
        .status-pending { color: #92400e; background: #fffbeb; }
        .status-failed { color: #991b1b; background: #fef2f2; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding-top: .48rem !important;
            padding-bottom: .42rem !important;
        }
        div[data-testid="stExpander"] details {
            border-radius: 8px !important;
            border-color: rgba(24,34,48,.1) !important;
        }
        div[data-testid="stExpander"] summary {
            min-height: 2rem !important;
            font-weight: 700;
        }
        textarea {
            line-height: 1.45 !important;
        }
        @media (max-width: 980px) {
            .ding-hero {
                align-items: flex-start;
                flex-direction: column;
            }
            .ding-stat-row {
                justify-content: flex-start;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_label(status):
    return STATUS_LABELS.get(status, status or "未知")


def status_html(status):
    safe_status = status if status in STATUS_LABELS else "pending"
    return f'<span class="status-pill status-{safe_status}">{status_label(status)}</span>'


def require_recorder_auth():
    configured_password = budget_auth.get_budget_password(st.secrets, os.environ)
    if not configured_password:
        st.title("🎙️ Recorder_笔记")
        st.warning("上锁板块密码还没有配置。请在 Streamlit secrets 中设置 budget_password，或在本机设置 BUDGET_PASSWORD。")
        st.stop()

    if st.session_state.get("recorder_authenticated"):
        return

    st.title("🎙️ Recorder_笔记")
    st.info("请输入密码后查看和操作 Recorder_笔记。")
    with st.form("recorder_auth_form"):
        input_password = st.text_input("访问密码", type="password")
        submitted = st.form_submit_button("进入 Recorder_笔记", use_container_width=True)

    if submitted:
        if budget_auth.is_budget_password_valid(input_password, configured_password):
            st.session_state["recorder_authenticated"] = True
            st.rerun()
        else:
            st.error("密码不正确，请重新输入。")

    st.stop()


def filter_records(records, status=None, keyword=None):
    filtered = list(records)
    if status and status != "全部":
        filtered = [record for record in filtered if record.get("status") == status]
    if keyword:
        keyword = keyword.strip()
        filtered = [
            record
            for record in filtered
            if any(
                keyword in str(record.get(field, ""))
                for field in ("file_name", "original_text", "ai_summary", "remark")
            )
        ]
    return filtered


def sync_recorder_cloud_to_github():
    try:
        result = github_backup_sync.sync_file_to_github(
            ding_minutes.CLOUD_EXPORT_PATH,
            "data/ding_minutes_cloud.json",
            "data: sync recorder cloud notes",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"Recorder 备注已保存在当前环境，但同步到 GitHub 失败：{exc}")
        return
    if result.get("skipped") and result.get("reason") == "missing_token":
        st.info("Recorder 备注已保存在当前环境；如需跨部署保留，请在 Streamlit secrets 配置 GITHUB_BACKUP_TOKEN。")


require_recorder_auth()
apply_style()
render_home_link()
ding_minutes.init_db()
config = ding_minutes.load_config()
runtime_config = config | {"api_key": ding_minutes.get_deepseek_api_key(st.secrets, os.environ)}
local_scan_available = Path(config.get("watch_dir", "")).exists()
local_records = ding_minutes.get_records(limit=1000)
cloud_payload = ding_minutes.load_cloud_export()
cloud_records = cloud_payload.get("records", [])
display_records = local_records or cloud_records
display_source = "local" if local_records else "cloud"
counts = ding_minutes.get_cloud_status_counts(display_records)
records_total = sum(counts.values())

st.markdown(
    f"""
    <section class="ding-hero">
      <div>
        <div class="ding-kicker">RECORDER NOTES</div>
        <h1 class="ding-title">🎙️ Recorder_笔记</h1>
        <p class="ding-subtitle">
          每天 19:00 扫描 Downloads 中新建的 export_*.docx、dt*.docx 和文件名包含“原文”的 Word，保留原文，并生成适合归档和复盘的整理稿。
        </p>
      </div>
      <div class="ding-stat-row">
        <div class="ding-stat"><b>{records_total}</b><span>全部记录</span></div>
        <div class="ding-stat"><b>{counts.get("done", 0)}</b><span>已整理</span></div>
        <div class="ding-stat"><b>{counts.get("pending", 0)}</b><span>待整理</span></div>
        <div class="ding-stat"><b>{counts.get("failed", 0)}</b><span>失败</span></div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

with st.container(border=True):
    col_path, col_action = st.columns([2.2, 1], gap="medium")
    with col_path:
        st.caption("当前扫描目录")
        st.code(config.get("watch_dir", ""), language="text")
        if not local_scan_available:
            st.info("当前为云端展示模式：线上页面只读取已同步记录，本地电脑负责扫描和 AI 整理。")
        elif not runtime_config.get("api_key"):
            st.warning("尚未配置 DEEPSEEK_API_KEY。可以登记原文，但不会生成 AI 整理稿。")
    with col_action:
        st.caption("手动补扫")
        if st.button("扫描当前时间窗", use_container_width=True, disabled=not local_scan_available):
            result = ding_minutes.scan_once(config=runtime_config)
            if result.get("error"):
                st.error(result["error"])
            else:
                st.success(
                    f"扫描完成：发现 {result['found']} 个，处理 {result['processed']} 个，"
                    f"跳过 {result['skipped']} 个，失败 {result['failed']} 个。"
                )
                st.rerun()

with st.container(border=True):
    filter_col, keyword_col = st.columns([1, 2], gap="medium")
    with filter_col:
        selected_status = st.selectbox("状态", ["全部", "done", "pending", "failed"], format_func=status_label)
    with keyword_col:
        keyword = st.text_input("搜索", placeholder="搜索文件名、原文、整理稿或备注")

records = filter_records(display_records, selected_status, keyword.strip() or None)

if not records:
    if display_source == "cloud":
        st.info("暂无同步记录。等本地 19:00 任务运行并推送后，云端会显示整理结果。")
    else:
        st.info("暂无记录。等定时任务运行后，或点击上方按钮手动扫描。")
else:
    if display_source == "cloud" and cloud_payload.get("generated_at"):
        st.caption(f"云端同步时间：{cloud_payload['generated_at']}")
    for record in records:
        with st.container(border=True):
            info_col, remark_col = st.columns([1.55, 1], gap="medium")
            with info_col:
                st.markdown(
                    f"""
                    <div class="record-title-row">
                      <h3 class="record-title">{record["file_name"]}</h3>
                      {status_html(record["status"])}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"""
                    <div class="record-meta">
                    创建：{record["created_at_file"]}　
                    修改：{record["modified_at_file"]}　
                    大小：{record["file_size"]} 字节
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if record.get("error_message"):
                    st.error(record["error_message"])

                if display_source == "local" and record["status"] != "done":
                    if st.button("重新生成整理稿", key=f"retry_{record['id']}", use_container_width=True):
                        ok = ding_minutes.generate_summary_for_record(
                            record["id"],
                            model=config.get("model", "deepseek-v4-pro"),
                            config=runtime_config,
                        )
                        if ok:
                            st.success("整理稿已生成")
                        else:
                            st.error("整理失败，请查看错误信息。")
                        st.rerun()

            with remark_col:
                with st.form(f"remark_form_{display_source}_{record['id']}"):
                    remark_input_col, save_col = st.columns([4, 1], gap="small")
                    with remark_input_col:
                        remark = st.text_area(
                            "备注 / 分类标记",
                            value=record.get("remark") or "",
                            placeholder="备注 / 分类标记",
                            height=34,
                            label_visibility="collapsed",
                        )
                    with save_col:
                        st.write("")
                        saved = st.form_submit_button("保存", use_container_width=True)
                if saved:
                    if display_source == "local":
                        ding_minutes.update_remark(record["id"], remark)
                    else:
                        ding_minutes.update_cloud_remark(record["id"], remark)
                    sync_recorder_cloud_to_github()
                    st.success("备注已保存")
                    st.rerun()

            with st.expander("展开查看整理稿和原文"):
                summary_tab, original_tab = st.tabs(["AI整理稿", "原文"])
                with summary_tab:
                    st.text_area(
                        "AI整理稿",
                        value=record.get("ai_summary") or "尚未生成整理稿。",
                        height=220,
                        label_visibility="collapsed",
                        disabled=True,
                        key=f"summary_{record['id']}",
                    )
                with original_tab:
                    st.text_area(
                        "原文",
                        value=record.get("original_text") or "未提取到原文。",
                        height=220,
                        label_visibility="collapsed",
                        disabled=True,
                        key=f"original_{record['id']}",
                    )
