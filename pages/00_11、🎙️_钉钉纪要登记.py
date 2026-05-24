import os
import sys

import streamlit as st


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import ding_minutes


st.set_page_config(page_title="钉钉纪要登记", page_icon="🎙️", layout="wide")


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
            font-size: .82rem;
            line-height: 1.65;
            margin-bottom: .5rem;
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
        textarea {
            line-height: 1.75 !important;
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


apply_style()
ding_minutes.init_db()
config = ding_minutes.load_config()
counts = ding_minutes.get_status_counts()
records_total = sum(counts.values())

st.markdown(
    f"""
    <section class="ding-hero">
      <div>
        <div class="ding-kicker">DING MINUTES</div>
        <h1 class="ding-title">🎙️ 钉钉纪要登记</h1>
        <p class="ding-subtitle">
          每天 19:00 扫描 Ding2026 中新建的 export_*.docx 和 dt*.docx，保留原文，并生成适合归档和复盘的整理稿。
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
        if not os.environ.get("DEEPSEEK_API_KEY"):
            st.warning("本机尚未配置 DEEPSEEK_API_KEY。可以登记原文，但不会生成 AI 整理稿。")
    with col_action:
        st.caption("手动补扫")
        if st.button("扫描当前时间窗", use_container_width=True):
            result = ding_minutes.scan_once(config=config)
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

records = ding_minutes.get_records(status=selected_status, keyword=keyword.strip() or None)

if not records:
    st.info("暂无记录。等定时任务运行后，或点击上方按钮手动扫描。")
else:
    for record in records:
        with st.container(border=True):
            title_col, status_col = st.columns([3, 1], gap="medium")
            with title_col:
                st.subheader(record["file_name"])
                st.markdown(
                    f"""
                    <div class="record-meta">
                    创建：{record["created_at_file"]}　
                    修改：{record["modified_at_file"]}　
                    大小：{record["file_size"]} 字节<br/>
                    路径：{record["file_path"]}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with status_col:
                st.markdown(status_html(record["status"]), unsafe_allow_html=True)

            if record.get("error_message"):
                st.error(record["error_message"])

            if record["status"] != "done":
                if st.button("重新生成整理稿", key=f"retry_{record['id']}", use_container_width=True):
                    ok = ding_minutes.generate_summary_for_record(
                        record["id"],
                        model=config.get("model", "deepseek-v4-pro"),
                        config=config,
                    )
                    if ok:
                        st.success("整理稿已生成")
                    else:
                        st.error("整理失败，请查看错误信息。")
                    st.rerun()

            summary_tab, original_tab, remark_tab = st.tabs(["AI整理稿", "原文", "备注"])
            with summary_tab:
                st.text_area(
                    "AI整理稿",
                    value=record.get("ai_summary") or "尚未生成整理稿。",
                    height=260,
                    label_visibility="collapsed",
                    disabled=True,
                    key=f"summary_{record['id']}",
                )
            with original_tab:
                st.text_area(
                    "原文",
                    value=record.get("original_text") or "未提取到原文。",
                    height=260,
                    label_visibility="collapsed",
                    disabled=True,
                    key=f"original_{record['id']}",
                )
            with remark_tab:
                with st.form(f"remark_form_{record['id']}"):
                    remark = st.text_area(
                        "备注",
                        value=record.get("remark") or "",
                        placeholder="可写用途、处理意见、后续动作或个人标记",
                        height=120,
                    )
                    saved = st.form_submit_button("保存备注", use_container_width=True)
                if saved:
                    ding_minutes.update_remark(record["id"], remark)
                    st.success("备注已保存")
                    st.rerun()
