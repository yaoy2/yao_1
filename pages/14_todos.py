import os
import sys
from datetime import date, datetime

import streamlit as st


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import budget_auth, github_backup_sync, todo_db
from utils.ui_theme import render_home_link


st.set_page_config(page_title="待办清单", page_icon="✓", layout="wide")


def require_todo_auth():
    configured_password = budget_auth.get_budget_password(st.secrets, os.environ)
    if not configured_password:
        st.title("✓ 待办清单")
        st.warning("待办清单密码还没有配置。请在 Streamlit secrets 中设置 budget_password，或在本机设置 BUDGET_PASSWORD。")
        st.stop()

    if st.session_state.get("todo_authenticated"):
        return

    st.title("✓ 待办清单")
    st.info("请输入密码后查看和操作待办清单。")
    with st.form("todo_auth_form"):
        input_password = st.text_input("访问密码", type="password")
        submitted = st.form_submit_button("进入待办清单", use_container_width=True)

    if submitted:
        if budget_auth.is_budget_password_valid(input_password, configured_password):
            st.session_state["todo_authenticated"] = True
            st.rerun()
        else:
            st.error("密码不正确，请重新输入。")

    st.stop()


def restore_todo_backup_from_github():
    if todo_db.has_local_todos() or todo_db.has_markdown_backup_records():
        return
    try:
        github_backup_sync.download_file_from_github(
            todo_db.BACKUP_MD_PATH,
            "data/todo_items_backup.md",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"待办备份从 GitHub 读取失败，将继续使用当前环境本地备份：{exc}")


def merge_remote_todos_from_github():
    try:
        result = github_backup_sync.read_file_from_github(
            "data/todo_items_backup.md",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"待办备份从 GitHub 读取失败，将继续使用当前环境本地备份：{exc}")
        return
    if not result.get("ok"):
        return

    remote_records = todo_db.parse_markdown_backup(result.get("content", ""))
    if not remote_records:
        return
    inserted = todo_db.import_todo_records(remote_records)
    if inserted:
        st.info(f"已从 GitHub 备份合并 {inserted} 条待办。")


def sync_todo_backup_to_github():
    local_records = todo_db.get_todos(view="all")
    try:
        remote_result = github_backup_sync.read_file_from_github(
            "data/todo_items_backup.md",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"待办已保存在当前环境，但同步到 GitHub 前读取远端备份失败：{exc}")
        return
    if remote_result.get("skipped") and remote_result.get("reason") == "missing_token":
        st.info("待办已保存在当前环境；如需跨部署保留，请在 Streamlit secrets 配置 GITHUB_BACKUP_TOKEN。")
        return
    if remote_result.get("ok"):
        remote_records = todo_db.parse_markdown_backup(remote_result.get("content", ""))
        if remote_records and not local_records:
            st.warning("GitHub 上还有待办备份，当前环境为空，已阻止空备份覆盖远端。")
            return
        inserted = todo_db.import_todo_records(remote_records)
        if inserted:
            st.info(f"已与 GitHub 备份合并 {inserted} 条待办，再同步回远端。")

    try:
        result = github_backup_sync.sync_file_to_github(
            todo_db.BACKUP_MD_PATH,
            "data/todo_items_backup.md",
            "data: sync todo items backup",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"待办已保存在当前环境，但同步到 GitHub 失败：{exc}")
        return
    if result.get("skipped") and result.get("reason") == "missing_token":
        st.info("待办已保存在当前环境；如需跨部署保留，请在 Streamlit secrets 配置 GITHUB_BACKUP_TOKEN。")


def apply_style():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.5rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px !important;
            border-color: rgba(24,34,48,.12) !important;
            box-shadow: 0 10px 24px rgba(24,34,48,.06);
        }
        .todo-title {
            font-size: 2rem;
            line-height: 1.15;
            font-weight: 850;
            margin: 0 0 .25rem;
            color: #182230;
        }
        .todo-subtitle {
            color: #667085;
            margin-bottom: .9rem;
        }
        .todo-row-text {
            min-height: 30px;
            display: flex;
            align-items: center;
            font-size: 1rem;
            font-weight: 650;
            color: #182230;
            line-height: 1.18;
            overflow: hidden;
            padding-top: .05rem;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .todo-row-text.done {
            text-decoration: line-through;
            color: #98A2B3;
        }
        .todo-meta {
            display: flex;
            gap: .5rem;
            flex-wrap: wrap;
            margin-top: .2rem;
            color: #667085;
            font-size: .82rem;
        }
        .todo-pill {
            border: 1px solid rgba(24,34,48,.1);
            border-radius: 999px;
            padding: .08rem .45rem;
            background: rgba(255,255,255,.68);
        }
        .todo-row-separator {
            height: 1px;
            margin: .06rem 0 .32rem;
            background: rgba(24,34,48,.08);
        }
        .todo-date-inline {
            min-height: 30px;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            color: #475467;
            font-size: .86rem;
            line-height: 1;
            white-space: nowrap;
            padding-top: .05rem;
        }
        .todo-icon-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            text-decoration: none !important;
            font-size: 14px;
            line-height: 1;
            transition: background .15s;
        }
        .todo-save-btn {
            background: #e8f5e9;
            color: #2e7d32;
        }
        .todo-save-btn:hover {
            background: #c8e6c9;
            color: #1b5e20;
            text-decoration: none !important;
        }
        .todo-delete-btn {
            background: #ffebee;
            color: #c62828;
        }
        .todo-delete-btn:hover {
            background: #ffcdd2;
            color: #b71c1c;
            text-decoration: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _date_value(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _time_value(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def _escape_html(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def save_todo_due_fields(record_id):
    new_due_date = st.session_state.get(f"todo_due_date_{record_id}")
    new_due_time = st.session_state.get(f"todo_due_time_{record_id}")
    due_date_val = new_due_date.isoformat() if new_due_date else ""
    due_time_val = new_due_time.strftime("%H:%M") if new_due_time else ""
    todo_db.update_todo(record_id, due_date=due_date_val, due_time=due_time_val)
    sync_todo_backup_to_github()


def delete_todo_record(record_id):
    todo_db.delete_todo(record_id)
    sync_todo_backup_to_github()


def toggle_todo_done(record_id, checkbox_key):
    if st.session_state.get(checkbox_key):
        todo_db.complete_todo(record_id)
    else:
        todo_db.reopen_todo(record_id)
    sync_todo_backup_to_github()


def render_todo_record(record):
    done = record.get("status") == "done"
    stored_due_date = _date_value(record.get("due_date"))
    stored_due_time = _time_value(record.get("due_time"))

    check_col, body_col, created_col, due_date_col, due_time_col, save_col, delete_col = st.columns(
        [0.045, 1.2, 0.16, 0.24, 0.16, 0.045, 0.045],
        gap="small",
        vertical_alignment="center",
    )
    with check_col:
        checkbox_key = f"todo_done_{record['id']}_{record.get('status')}"
        checked = st.checkbox(
            "完成",
            value=done,
            key=checkbox_key,
            label_visibility="collapsed",
            on_change=toggle_todo_done,
            args=(record["id"], checkbox_key),
        )

    with body_col:
        content_class = "todo-row-text done" if done else "todo-row-text"
        st.markdown(
            f"""<div class="{content_class}">{_escape_html(record.get('content', ''))}</div>""",
            unsafe_allow_html=True,
        )
    with created_col:
        st.markdown(
            f"""<div class="todo-date-inline">{_escape_html(record.get('record_date', ''))}</div>""",
            unsafe_allow_html=True,
        )
    with due_date_col:
        new_due_date = st.date_input(
            "截止日期",
            value=stored_due_date,
            key=f"todo_due_date_{record['id']}",
            label_visibility="collapsed",
        )
    with due_time_col:
        new_due_time = st.time_input(
            "截止时间",
            value=stored_due_time,
            key=f"todo_due_time_{record['id']}",
            step=900,
            label_visibility="collapsed",
        )
    with save_col:
        st.button(
            "✓",
            key=f"save_due_{record['id']}",
            help="保存截止日期/时间",
            use_container_width=True,
            on_click=save_todo_due_fields,
            args=(record["id"],),
        )
    with delete_col:
        st.button(
            "×",
            key=f"delete_todo_{record['id']}",
            help="删除这条待办",
            use_container_width=True,
            on_click=delete_todo_record,
            args=(record["id"],),
        )

    st.markdown('<div class="todo-row-separator"></div>', unsafe_allow_html=True)


require_todo_auth()
apply_style()
render_home_link()
restore_todo_backup_from_github()
todo_db.init_db()
merge_remote_todos_from_github()

records_all = todo_db.get_todos(view="all")
active_count = len([record for record in records_all if not record.get("is_archived")])
archived_count = len([record for record in records_all if record.get("is_archived")])

st.markdown(
    f"""
    <div>
      <div class="todo-title">✓ 待办清单</div>
      <div class="todo-subtitle">新增在上，勾选即完成；完成项自动沉到未完成待办下面。</div>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_a, metric_b, metric_c = st.columns(3)
metric_a.metric("未完成", active_count)
metric_b.metric("已归档", archived_count)
metric_c.metric("全部记录", len(records_all))

with st.container(border=True):
    st.subheader("快速新增")
    with st.form("todo_quick_add", clear_on_submit=True):
        todo_text = st.text_area("待办文本", placeholder="例如：明天下午3点前提交学院材料", height=96)
        parsed_due_date, parsed_due_time = todo_db.extract_due_fields(todo_text, date.today())
        col_date, col_time, col_save = st.columns([1, 1, 1], vertical_alignment="bottom")
        with col_date:
            due_date = st.date_input("截止日期", value=_date_value(parsed_due_date))
        with col_time:
            due_time = st.time_input("截止时间", value=_time_value(parsed_due_time), step=900)
        with col_save:
            submitted = st.form_submit_button("保存待办", type="primary", use_container_width=True)
        if submitted:
            try:
                todo_db.add_todos_from_text(
                    todo_text,
                    record_date=date.today().isoformat(),
                    due_date=due_date,
                    due_time=due_time,
                )
            except ValueError:
                st.error("请输入待办内容后再保存。")
            else:
                sync_todo_backup_to_github()
                st.success("待办已保存。")
                st.rerun()

with st.container(border=True):
    search_col, = st.columns([1], gap="medium", vertical_alignment="bottom")
    with search_col:
        keyword = st.text_input("搜索", placeholder="搜索内容、发布日期、截止日期或时间")

    display_records = todo_db.get_todos(keyword=keyword, view="list")

    if not display_records:
        st.info("当前没有匹配的待办。")
    else:
        for record in display_records:
            render_todo_record(record)
