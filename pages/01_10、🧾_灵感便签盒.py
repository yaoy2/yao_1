import os
import sys
from datetime import date

import streamlit as st


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import github_backup_sync, web_memo_db
from utils.ui_theme import render_home_link


st.set_page_config(page_title="灵感便签盒", page_icon="🧾", layout="wide")


def color_text(hex_code):
    hex_code = hex_code or "#1B3A5C"
    r = int(hex_code[1:3], 16)
    g = int(hex_code[3:5], 16)
    b = int(hex_code[5:7], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#ffffff" if lum < 140 else "#182230"


def get_available_tags():
    fallback_tags = [
        "摘录",
        "观点",
        "待办",
        "写作素材",
        "工作记录",
        "工具想法",
        "金句",
        "行政日常",
        "学生工作",
        "竞赛",
    ]
    if hasattr(web_memo_db, "get_all_tags"):
        return web_memo_db.get_all_tags()
    return fallback_tags


def parse_manual_tags(selected_tags, new_tags):
    if hasattr(web_memo_db, "split_tags"):
        typed_tags = web_memo_db.split_tags(new_tags)
    else:
        typed_tags = [tag.strip() for tag in str(new_tags).replace(",", "、").replace("，", "、").split("、") if tag.strip()]
    if hasattr(web_memo_db, "merge_tags"):
        return web_memo_db.merge_tags(selected_tags, typed_tags)
    merged = []
    for tag in list(selected_tags or []) + typed_tags:
        if tag and tag not in merged:
            merged.append(tag)
    return merged


def restore_web_memo_backup_from_github():
    if web_memo_db.has_local_memos() or web_memo_db.has_markdown_backup_records():
        return
    try:
        github_backup_sync.download_file_from_github(
            web_memo_db.BACKUP_MD_PATH,
            "data/web_memos_backup.md",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"便签备份从 GitHub 读取失败，将继续使用当前环境本地备份：{exc}")


def merge_remote_web_memos_from_github():
    try:
        result = github_backup_sync.read_file_from_github(
            "data/web_memos_backup.md",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"便签备份从 GitHub 读取失败，将继续使用当前环境本地备份：{exc}")
        return
    if not result.get("ok"):
        return

    remote_records = web_memo_db.parse_markdown_backup(result.get("content", ""))
    if not remote_records:
        return
    inserted = web_memo_db.import_memo_records(remote_records)
    if inserted:
        st.info(f"已从 GitHub 备份补回 {inserted} 条便签。")


def sync_web_memo_backup_to_github():
    local_records = web_memo_db.get_memos()
    try:
        remote_result = github_backup_sync.read_file_from_github(
            "data/web_memos_backup.md",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"便签已保存在当前环境，但同步到 GitHub 前读取远端备份失败：{exc}")
        return
    if remote_result.get("skipped") and remote_result.get("reason") == "missing_token":
        st.info("便签已保存在当前环境；如需跨部署保留，请在 Streamlit secrets 配置 GITHUB_BACKUP_TOKEN。")
        return
    if remote_result.get("ok"):
        remote_records = web_memo_db.parse_markdown_backup(remote_result.get("content", ""))
        if remote_records and not local_records:
            st.warning("GitHub 上还有便签备份，当前环境是空的，已阻止空备份覆盖远端。")
            return
        inserted = web_memo_db.import_memo_records(remote_records)
        if inserted:
            st.info(f"已与 GitHub 备份合并 {inserted} 条便签，再同步回远端。")

    try:
        result = github_backup_sync.sync_file_to_github(
            web_memo_db.BACKUP_MD_PATH,
            "data/web_memos_backup.md",
            "data: sync web memo backup",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"便签已保存在当前环境，但同步到 GitHub 失败：{exc}")
        return
    if result.get("skipped") and result.get("reason") == "missing_token":
        st.info("便签已保存在当前环境；如需跨部署保留，请在 Streamlit secrets 配置 GITHUB_BACKUP_TOKEN。")


def apply_style():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.7rem !important;
            padding-bottom: 1.5rem !important;
        }
        .memo-hero {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            gap: 1.5rem;
            margin-bottom: 1.1rem;
        }
        .memo-mark {
            display: inline-flex;
            gap: .5rem;
            align-items: center;
            color: #344054;
            font-size: .82rem;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: .45rem;
        }
        .memo-dot {
            width: 9px;
            height: 9px;
            border-radius: 999px;
            background: #2D6A4F;
            box-shadow: 14px 0 0 #1B3A5C, 28px 0 0 #810000;
        }
        .memo-title {
            font-size: 2.35rem;
            line-height: 1.1;
            margin: 0;
            font-weight: 850;
            color: #182230;
        }
        .memo-subtitle {
            margin: .45rem 0 0;
            color: #667085;
            font-size: 1.42rem;
            font-weight: 500;
            font-family: "STXingcao", "华文行草", "FZShuTi", "方正舒体", "STXinwei", "华文新魏", cursive;
            letter-spacing: 0;
        }
        .memo-stat-row {
            display: flex;
            gap: .65rem;
            flex-wrap: wrap;
            justify-content: flex-end;
        }
        .memo-stat {
            min-width: 96px;
            text-align: center;
            padding: .72rem .65rem;
            border: 1px solid rgba(24,34,48,.1);
            border-radius: 8px;
            background: rgba(255,255,255,.78);
            box-shadow: 0 10px 26px rgba(24,34,48,.07);
        }
        .memo-stat b {
            display: block;
            font-size: 1.3rem;
        }
        .memo-stat span {
            color: #667085;
            font-size: .76rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px !important;
            border-color: rgba(24,34,48,.11) !important;
            box-shadow: 0 12px 30px rgba(24,34,48,.06);
        }
        textarea {
            min-height: 130px !important;
            line-height: 1.8 !important;
        }
        div[data-testid="stForm"] div[data-testid="stHorizontalBlock"] {
            align-items: flex-start;
        }
        div[data-testid="stForm"] div[data-baseweb="select"] > div,
        div[data-testid="stForm"] input {
            min-height: 54px !important;
        }
        .inline-field-label {
            min-height: 54px;
            display: flex;
            align-items: center;
            color: #182230;
            font-weight: 700;
            white-space: nowrap;
        }
        .memo-card {
            position: relative;
            width: 100%;
            min-height: 168px;
            padding: .95rem .95rem .85rem 1.08rem;
            margin: 0 0 .82rem;
            border: 1px solid rgba(24,34,48,.1);
            border-radius: 8px;
            box-shadow: 0 12px 26px rgba(24,34,48,.16);
            overflow: hidden;
        }
        .memo-card::before {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 6px;
            background: var(--card-text);
        }
        .memo-card-top {
            position: relative;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: .6rem;
            margin-bottom: .7rem;
        }
        .memo-date {
            color: var(--card-text);
            font-size: .82rem;
            font-weight: 800;
            line-height: 1.35;
        }
        .memo-palette {
            font-size: .72rem;
            color: var(--card-text);
            background: var(--card-pill-bg);
            border: 1px solid var(--card-border);
            border-radius: 999px;
            padding: .22rem .5rem;
        }
        .memo-content {
            position: relative;
            color: var(--card-text);
            font-family: "Kaiti SC", KaiTi, STKaiti, "Songti SC", SimSun, serif;
            font-size: 1.08rem;
            font-weight: 600;
            line-height: 1.9;
            letter-spacing: .02em;
            white-space: pre-wrap;
        }
        .memo-tags {
            position: relative;
            margin-top: .75rem;
            display: flex;
            gap: .38rem;
            flex-wrap: wrap;
        }
        .memo-tag {
            font-size: .74rem;
            background: var(--card-pill-bg);
            color: var(--card-text);
            border: 1px solid var(--card-border);
            border-radius: 999px;
            padding: .16rem .48rem;
        }
        .memo-tag-main {
            color: var(--card-text);
            font-weight: 700;
        }
        .export-strip {
            margin-top: 1.15rem;
            padding: .95rem 1rem;
            border: 1px solid rgba(24,34,48,.11);
            border-radius: 8px;
            background: rgba(255,255,255,.8);
            box-shadow: 0 12px 30px rgba(24,34,48,.07);
        }
        @media (max-width: 980px) {
            .memo-hero {
                align-items: flex-start;
                flex-direction: column;
            }
            .memo-stat-row {
                justify-content: flex-start;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

apply_style()
render_home_link()
restore_web_memo_backup_from_github()
web_memo_db.init_db()
merge_remote_web_memos_from_github()

records = web_memo_db.get_memos()
categories = ["全部"] + web_memo_db.get_categories()
available_tags = get_available_tags()
palettes = web_memo_db.parse_palettes()

st.markdown(
    f"""
    <section class="memo-hero">
      <div>
        <div class="memo-mark"><span class="memo-dot"></span><span>Web Memo</span></div>
        <h1 class="memo-title">🧾 灵感便签盒</h1>
        <p class="memo-subtitle">“我来监督沙瑞金”</p>
      </div>
      <div class="memo-stat-row">
        <div class="memo-stat"><b>{len(records)}</b><span>全部摘录</span></div>
        <div class="memo-stat"><b>{len([r for r in records if r["memo_date"][:7] == date.today().strftime("%Y-%m")])}</b><span>本月新增</span></div>
        <div class="memo-stat"><b>{len(palettes)}</b><span>循环色卡</span></div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

with st.container(border=True):
    st.subheader("快速记录")
    with st.form("web_memo_form", clear_on_submit=True):
        entry_col, tag_col = st.columns([2.05, 1.25], gap="medium")
        with entry_col:
            content = st.text_area("内容", placeholder="请输入", label_visibility="collapsed", height=130)
        with tag_col:
            tag_label_col, tag_input_col = st.columns([0.22, 0.78], gap="small")
            with tag_label_col:
                st.markdown('<div class="inline-field-label">标签</div>', unsafe_allow_html=True)
            with tag_input_col:
                selected_tags = st.multiselect(
                    "标签",
                    available_tags,
                    placeholder="选择已有标签",
                    label_visibility="collapsed",
                )
            new_label_col, new_input_col = st.columns([0.22, 0.78], gap="small")
            with new_label_col:
                st.markdown('<div class="inline-field-label">新增标签</div>', unsafe_allow_html=True)
            with new_input_col:
                new_tags = st.text_input(
                    "新增标签",
                    placeholder="用顿号或逗号分隔",
                    label_visibility="collapsed",
                )
        col_save, col_plain = st.columns(2)
        save_classified = col_save.form_submit_button("保存并打标签", use_container_width=True)
        save_plain = col_plain.form_submit_button("只保存", use_container_width=True)

    if save_classified or save_plain:
        try:
            manual_tags = parse_manual_tags(selected_tags, new_tags)
            try:
                web_memo_db.add_memo(
                    date.today().isoformat(),
                    content,
                    classify=save_classified,
                    manual_tags=manual_tags,
                )
            except TypeError:
                web_memo_db.add_memo(date.today().isoformat(), content, classify=save_classified)
            sync_web_memo_backup_to_github()
            st.success("已保存")
            st.rerun()
        except ValueError:
            st.error("请输入内容后再保存。")

with st.container(border=True):
    top_a, top_b = st.columns([1, 1])
    with top_a:
        st.subheader("备忘列表")
    with top_b:
        selected_category = st.selectbox("分类", categories, label_visibility="collapsed")
    keyword = st.text_input("搜索", placeholder="按关键词搜索", label_visibility="collapsed")

    display_records = web_memo_db.get_memos(category=selected_category, keyword=keyword.strip() or None)
    if not display_records:
        st.info("还没有记录。先在上方粘贴一条。")
    else:
        memo_columns = st.columns(3, gap="medium")
        for index, record in enumerate(display_records):
            with memo_columns[index % 3]:
                with st.container(border=True):
                    st.markdown(web_memo_db.build_memo_card_html(record, palette_index=index), unsafe_allow_html=True)
                    move_up, move_down, edit_col, hide_col, _spacer = st.columns([0.18, 0.18, 0.18, 0.18, 1], gap="small")
                    if move_up.button("↑", key=f"memo_up_{record['id']}", disabled=index == 0, help="上移"):
                        web_memo_db.move_memo(record["id"], "up")
                        sync_web_memo_backup_to_github()
                        st.rerun()
                    if move_down.button("↓", key=f"memo_down_{record['id']}", disabled=index == len(display_records) - 1, help="下移"):
                        web_memo_db.move_memo(record["id"], "down")
                        sync_web_memo_backup_to_github()
                        st.rerun()
                    if edit_col.button("✎", key=f"memo_edit_{record['id']}", help="编辑"):
                        st.session_state["editing_memo_id"] = record["id"]
                    if hide_col.button("×", key=f"memo_archive_{record['id']}", help="隐藏"):
                        web_memo_db.archive_memo(record["id"])
                        sync_web_memo_backup_to_github()
                        st.rerun()

                    if st.session_state.get("editing_memo_id") == record["id"]:
                        with st.form(f"memo_edit_form_{record['id']}"):
                            edited_content = st.text_area("内容", value=record.get("content", ""), height=160, key=f"memo_edit_content_{record['id']}")
                            edit_category_options = [cat for cat in categories if cat != "全部"]
                            current_category = record.get("category") or "待整理"
                            if current_category not in edit_category_options:
                                edit_category_options.insert(0, current_category)
                            edited_category = st.selectbox(
                                "分类",
                                edit_category_options,
                                index=edit_category_options.index(current_category),
                                key=f"memo_edit_category_{record['id']}",
                            )
                            edited_tags = st.multiselect(
                                "标签",
                                available_tags,
                                default=[tag for tag in record.get("tags", []) if tag in available_tags],
                                key=f"memo_edit_tags_{record['id']}",
                            )
                            extra_tags = st.text_input("新增标签", key=f"memo_edit_extra_tags_{record['id']}")
                            save_edit, cancel_edit = st.columns(2)
                            if save_edit.form_submit_button("保存修改", use_container_width=True):
                                try:
                                    web_memo_db.update_memo(
                                        record["id"],
                                        content=edited_content,
                                        category=edited_category,
                                        tags=parse_manual_tags(edited_tags, extra_tags),
                                    )
                                except ValueError:
                                    st.error("内容不能为空。")
                                else:
                                    sync_web_memo_backup_to_github()
                                    st.session_state.pop("editing_memo_id", None)
                                    st.rerun()
                            if cancel_edit.form_submit_button("取消", use_container_width=True):
                                st.session_state.pop("editing_memo_id", None)
                                st.rerun()

st.markdown('<section class="export-strip">', unsafe_allow_html=True)
export_records = web_memo_db.get_memos()
export_format = st.radio("导出格式", ["Markdown", "PDF"], horizontal=True)
if export_format == "Markdown":
    export_data = web_memo_db.build_markdown_export(export_records).encode("utf-8")
    st.download_button(
        "导出全部",
        data=export_data,
        file_name=f"灵感便签盒_{date.today().isoformat()}.md",
        mime="text/markdown",
        use_container_width=True,
    )
else:
    export_data = web_memo_db.build_pdf_export(export_records)
    st.download_button(
        "导出全部",
        data=export_data,
        file_name=f"灵感便签盒_{date.today().isoformat()}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
st.markdown("</section>", unsafe_allow_html=True)
