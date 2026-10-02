import importlib
import os
import re
import sys
import tempfile
from time import monotonic
from datetime import date, datetime
from pathlib import Path

import streamlit as st


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import budget_auth, github_backup_sync, todo_db
from utils.todo_backup_validation import validate_todo_backup
from utils.todo_calendar import render_calendar_html, shift_month
from utils.ui_theme import render_home_link


# A running Cloud session can retain the pre-chat module after the page updates.
# Refresh it before init_db so the UID migration and date helpers update together.
if getattr(todo_db, "CHAT_SCHEMA_VERSION", 0) < 2:
    todo_db = importlib.reload(todo_db)


st.set_page_config(page_title="待办清单", page_icon="✓", layout="wide")
render_home_link()


DUE_TIME_OPTIONS = ["", "09:30", "10:00", "11:30", "14:00", "17:00"]


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
    if todo_db.has_local_todos():
        return
    backup_path = Path(todo_db.BACKUP_MD_PATH)
    if backup_path.exists() and backup_path.stat().st_size:
        try:
            local_records = validate_todo_remote_backup(
                {"ok": True, "sha": "local-backup", "content": backup_path.read_text(encoding="utf-8")})
            if local_records:
                return
        except (ValueError, OSError, UnicodeError) as exc:
            st.error(f"本机待办备份无法完整读取，已保留原文件并停止初始化，避免覆盖：{exc}")
            st.stop()
    try:
        result = github_backup_sync.read_file_from_github(
            "data/todo_items_backup.md",
            secrets=st.secrets,
            environ=os.environ,
        )
        if not result.get("ok"):
            st.warning("待办远端备份未能核对，已暂停初始化以保留原有记录；恢复连接后重试。")
            st.stop()
        validate_todo_remote_backup(result)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=backup_path.parent,
                                             prefix=".todo-restore-", suffix=".tmp", delete=False) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(result["content"])
            os.replace(temporary_path, backup_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        github_backup_sync.remember_local_sync_baseline(
            backup_path, "data/todo_items_backup.md", result["content"], result["sha"],
            secrets=st.secrets, environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"待办备份从 GitHub 恢复失败，已暂停初始化以保留原有记录：{exc}")
        st.stop()


def validate_todo_remote_backup(result):
    """Reject partial or ambiguous snapshots before importing or publishing records."""
    text = result.get("content")
    if not result.get("ok") or not result.get("sha") or not isinstance(text, str):
        raise ValueError("备份版本无效")
    return validate_todo_backup(text)


def todo_record_snapshot(records):
    # UID identifies a task across devices; numeric IDs can legitimately be remapped.
    return {todo_db.record_uid(record): {
                **{key: value for key, value in record.items() if key not in {"id", "uid"}},
                "uid": todo_db.record_uid(record)}
            for record in records}


def pending_todo_sync_sha():
    pending_sha = st.session_state.get("todo_pending_sync_sha")
    if pending_sha:
        return pending_sha
    try:
        baseline = github_backup_sync.get_local_sync_baseline(
            todo_db.BACKUP_MD_PATH, "data/todo_items_backup.md", secrets=st.secrets, environ=os.environ)
    except (OSError, ValueError, RuntimeError) as exc:
        st.session_state["todo_pending_sync_sha"] = "invalid-local-baseline"
        st.session_state["todo_sync_error"] = f"本机同步基线无法读取，已暂停合并和写入以保留待办记录：{exc}"
        return "invalid-local-baseline"
    if not baseline:
        return None
    try:
        baseline_records = validate_todo_backup(baseline["content"])
        baseline_sha = baseline["sha"]
        if not baseline_sha:
            raise ValueError("同步基线缺少版本")
    except (KeyError, ValueError):
        # An unreadable baseline cannot establish that overwriting the local DB is safe.
        st.session_state["todo_pending_sync_sha"] = "invalid-local-baseline"
        st.session_state["todo_sync_error"] = "本机同步基线无效，已暂停合并和写入以保留待办记录。"
        return "invalid-local-baseline"
    if todo_record_snapshot(baseline_records) != todo_record_snapshot(todo_db.get_todos(view="all")):
        pending_sha = baseline_sha
        st.session_state["todo_pending_sync_sha"] = pending_sha
        return pending_sha
    return None


def warn_todo_sync_pending(message):
    st.session_state["todo_sync_error"] = message
    st.warning(message)


def merge_remote_todos_from_github():
    pending_sha = pending_todo_sync_sha()
    try:
        result = github_backup_sync.read_file_from_github(
            "data/todo_items_backup.md",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        st.warning(f"待办备份从 GitHub 读取失败，将继续使用当前环境本地备份：{exc}")
        return False
    if not result.get("ok"):
        st.warning("暂时无法核对 GitHub 上的待办备份；当前环境记录仍保留，恢复连接后再同步。")
        return False

    try:
        remote_records = validate_todo_remote_backup(result)
    except ValueError as exc:
        st.warning(f"GitHub 待办备份无法完整核对，已停止合并和写入：{exc}")
        return False
    if pending_sha:
        if result["sha"] != pending_sha:
            warn_todo_sync_pending("远端待办已变化，当前环境未同步的修改仍保留；已暂停合并，请先核对双方记录。")
            return False
        st.session_state["todo_observed_remote_sha"] = result["sha"]
        return True
    inserted = todo_db.import_todo_records(remote_records)
    if inserted:
        st.info(f"已从 GitHub 备份合并 {inserted} 条待办。")
    github_backup_sync.remember_local_sync_baseline(
        todo_db.BACKUP_MD_PATH, "data/todo_items_backup.md", result["content"], result["sha"],
        secrets=st.secrets, environ=os.environ)
    st.session_state["todo_observed_remote_sha"] = result["sha"]
    return True


def refresh_todos_if_needed():
    """Throttle passive refreshes; edit callbacks still check the remote every time."""
    last_refresh = st.session_state.get("todo_remote_refreshed_at")
    if last_refresh is None or monotonic() - last_refresh >= 30:
        if merge_remote_todos_from_github():
            st.session_state["todo_remote_refreshed_at"] = monotonic()


def sync_todo_backup_to_github(expected_sha=None):
    expected_sha = expected_sha or pending_todo_sync_sha()
    if not expected_sha:
        warn_todo_sync_pending("没有已核对的待办版本，本次未写入远端；请先刷新并核对记录。")
        return False
    st.session_state["todo_pending_sync_sha"] = expected_sha
    local_records = todo_db.get_todos(view="all")
    try:
        remote_result = github_backup_sync.read_file_from_github(
            "data/todo_items_backup.md",
            secrets=st.secrets,
            environ=os.environ,
        )
    except Exception as exc:
        warn_todo_sync_pending(f"待办已保存在当前环境，但同步到 GitHub 前读取远端备份失败：{exc}")
        return False
    if remote_result.get("skipped") and remote_result.get("reason") == "missing_token":
        warn_todo_sync_pending("待办已保存在当前环境；如需跨部署保留，请在 Streamlit secrets 配置 GITHUB_BACKUP_TOKEN。")
        return False
    if not remote_result.get("ok"):
        warn_todo_sync_pending("待办已保存在当前环境，但未能核对 GitHub 备份，本次未写入远端。")
        return False
    try:
        remote_records = validate_todo_remote_backup(remote_result)
        if remote_result["sha"] != expected_sha:
            warn_todo_sync_pending("远端待办已在本次修改后变化；当前环境修改仍保留，本次未合并或覆盖，请先核对双方记录。")
            return False
        if remote_records and not local_records:
            warn_todo_sync_pending("GitHub 上还有待办备份，当前环境为空，已阻止空备份覆盖远端。")
            return False
        # Validate the file that will actually be uploaded, including any local additions.
        local_snapshot = validate_todo_remote_backup(
            {"ok": True, "sha": remote_result["sha"],
             "content": Path(todo_db.BACKUP_MD_PATH).read_text(encoding="utf-8")})
        if local_snapshot != todo_db.get_todos(view="all"):
            raise ValueError("本机备份与当前待办数据库不一致，需先核对")
    except (ValueError, OSError, UnicodeError) as exc:
        warn_todo_sync_pending(f"待办已保存在当前环境，但备份无法完整核对，本次未写入远端：{exc}")
        return False

    try:
        result = github_backup_sync.sync_file_to_github(
            todo_db.BACKUP_MD_PATH,
            "data/todo_items_backup.md",
            "data: sync todo items backup",
            secrets=st.secrets,
            environ=os.environ,
            expected_sha=expected_sha,
        )
    except Exception as exc:
        warn_todo_sync_pending(f"待办已保存在当前环境，但同步到 GitHub 失败：{exc}")
        return False
    if result.get("skipped") and result.get("reason") == "missing_token":
        warn_todo_sync_pending("待办已保存在当前环境；如需跨部署保留，请在 Streamlit secrets 配置 GITHUB_BACKUP_TOKEN。")
    elif not result.get("ok"):
        warn_todo_sync_pending("待办已保存在当前环境，但尚未同步到 GitHub；请恢复连接后重试。")
    if result.get("ok"):
        st.session_state.pop("todo_pending_sync_sha", None)
        st.session_state.pop("todo_sync_error", None)
        return True
    return False


def add_todo_from_page(todo_text, due_date, due_time):
    if re.search(r"^## TODO-|^### 内容\s*$", todo_text, re.M):
        raise ValueError("待办正文不能包含备份控制标题。")
    if not merge_remote_todos_from_github():
        st.warning("暂时无法核对最新待办，本次未新增，请稍后重试。")
        return False
    expected_sha = st.session_state.get("todo_observed_remote_sha")
    if not expected_sha:
        st.warning("暂时无法核对待办版本，本次未新增，请稍后重试。")
        return False
    todo_db.add_todos_from_text(todo_text, record_date=todo_db.today().isoformat(),
                               due_date=due_date, due_time=due_time)
    st.session_state["todo_pending_sync_sha"] = expected_sha
    st.session_state["todo_quick_add_saved"] = True
    synced = sync_todo_backup_to_github(expected_sha=expected_sha)
    st.session_state["todo_save_notice"] = "synced" if synced else "pending"
    # Clear the submitted text and show the saved row even when the network failed.
    st.rerun()
    return True


def apply_style():
    st.markdown(
        """
        <style>
        /* Dense editing applies only to saved task rows, not forms or navigation. */
        [class*="st-key-todo-row-"] [data-testid="stHorizontalBlock"] { gap: .35rem; }
        [class*="st-key-todo-row-"] :is([data-testid="stTextInput"], [data-testid="stSelectbox"]) { margin-bottom: 0; }
        [class*="st-key-todo-row-"] div[data-baseweb="input"],
        [class*="st-key-todo-row-"] div[data-baseweb="select"] > div {
            min-height: 32px;
            border: 1px solid var(--colors-hairline);
            border-radius: var(--rounded-sm);
        }
        [class*="st-key-todo-row-"] input { padding: .25rem .4rem; font-size: .82rem; }
        [class*="st-key-todo-row-"] [data-testid="stButton"] button {
            min-height: 32px;
            padding: .2rem .35rem;
        }
        [class*="st-key-delete_todo_"] button { color: var(--colors-danger); }
        .todo-row-text {
            display: flex;
            align-items: center;
            min-height: 32px;
            color: var(--colors-ink);
            font-size: .9rem;
            font-weight: 400;
            line-height: 1.45;
            overflow-wrap: anywhere;
        }
        .todo-row-text.done { color: var(--colors-ink-muted-48); text-decoration: line-through; }
        .todo-date-inline {
            min-height: 32px;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            color: var(--colors-ink-muted-48);
            font-size: .78rem;
            font-variant-numeric: tabular-nums;
        }
        .todo-meta { display: flex; flex-wrap: wrap; gap: .5rem; color: var(--colors-ink-muted-48); font-size: .82rem; }
        .todo-pill { padding: .15rem .5rem; border-radius: var(--rounded-pill); background: var(--colors-canvas-parchment); }
        @media (max-width: 720px) {
            [class*="st-key-todo-row-"] [data-testid="stButton"] button,
            [class*="st-key-todo-row-"] div[data-baseweb="input"],
            [class*="st-key-todo-row-"] div[data-baseweb="select"] > div { min-height: 44px; }
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


def _compact_date_label(value):
    date_value = _date_value(value)
    if date_value:
        return date_value.strftime("%m-%d") if date_value.year == todo_db.today().year else date_value.isoformat()
    return str(value or "")


def _full_date_from_compact(value, fallback_year=None):
    text = str(value or "").strip()
    if not text:
        return ""
    if _date_value(text):
        return text
    normalized = text.replace("/", "-").replace(".", "-")
    year = fallback_year or todo_db.today().year
    try:
        return datetime.strptime(f"{year}-{normalized}", "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def _due_time_options(value=""):
    stored_value = str(value or "").strip()
    if stored_value and stored_value not in DUE_TIME_OPTIONS:
        return ["", stored_value, *DUE_TIME_OPTIONS[1:]]
    return DUE_TIME_OPTIONS


def _due_time_index(value, options):
    stored_value = str(value or "").strip()
    try:
        return options.index(stored_value)
    except ValueError:
        return 0


def _escape_html(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def change_calendar_month(offset):
    today = todo_db.today()
    current = st.session_state.get("todo_calendar_month", today.replace(day=1))
    st.session_state["todo_calendar_month"] = shift_month(current, offset) if offset else today.replace(day=1)


def render_todo_calendar(records):
    today = todo_db.today()
    month = st.session_state.get("todo_calendar_month", today.replace(day=1))
    with st.container(border=True):
        with st.container(key="todo-calendar-navigation"):
            previous_year_col, previous_month_col, month_col, next_month_col, next_year_col = st.columns(
                [1, 1, 4, 1, 1], gap="small", vertical_alignment="center"
            )
            with previous_year_col:
                st.button("«", help="上一年", key="todo_calendar_previous_year",
                          on_click=change_calendar_month, args=(-12,),
                          disabled=month.year == 1, use_container_width=True)
            with previous_month_col:
                st.button("‹", help="上一月", key="todo_calendar_previous", on_click=change_calendar_month,
                          args=(-1,), disabled=month == date.min, use_container_width=True)
            with month_col:
                st.markdown(
                    f'<div class="todo-calendar-month-label" role="heading" aria-level="3">{month.year} 年 {month.month} 月</div>',
                    unsafe_allow_html=True,
                )
            with next_month_col:
                st.button("›", help="下一月", key="todo_calendar_next", on_click=change_calendar_month,
                          args=(1,), disabled=month == date(9999, 12, 1), use_container_width=True)
            with next_year_col:
                st.button("»", help="下一年", key="todo_calendar_next_year",
                          on_click=change_calendar_month, args=(12,),
                          disabled=month.year == 9999, use_container_width=True)
        st.caption("按截止日期排列，点击简称展开详情；已完成任务显示中划线。")
        st.html(render_calendar_html(records, month, today=today))


def prepare_todo_edit(record_id):
    expected = st.session_state.get(f"todo_revision_{record_id}")
    if not merge_remote_todos_from_github():
        st.warning("暂时无法核对最新待办，本次未修改，请稍后重试。")
        return False
    record = next((r for r in todo_db.get_todos(view="all") if r["id"] == record_id), None)
    current = f"{record['uid']}:{record['updated_at']}" if record else None
    if not expected or current != expected or record.get("status") == "deleted":
        st.warning("这条待办已在其他入口变化，已刷新；请核对后再操作。")
        return False
    sync_sha = st.session_state.get("todo_observed_remote_sha")
    if not sync_sha:
        st.warning("暂时无法核对待办版本，本次未修改，请稍后重试。")
        return False
    record["_sync_sha"] = sync_sha
    return record


def save_todo_due_fields(record_id):
    record = prepare_todo_edit(record_id)
    if not record:
        return
    new_due_date = st.session_state.get(f"todo_due_date_{record_id}")
    new_due_time = st.session_state.get(f"todo_due_time_{record_id}")
    original_date = _date_value(record.get("due_date"))
    due_date_val = _full_date_from_compact(new_due_date, original_date.year if original_date else None)
    if str(new_due_date or "").strip() and not due_date_val:
        st.warning("截止日期无效，请填写 MM-DD 或 YYYY-MM-DD。")
        return
    due_time_val = str(new_due_time or "")
    todo_db.update_todo(record_id, due_date=due_date_val, due_time=due_time_val)
    st.session_state["todo_pending_sync_sha"] = record["_sync_sha"]
    sync_todo_backup_to_github(expected_sha=record["_sync_sha"])


def delete_todo_record(record_id):
    record = prepare_todo_edit(record_id)
    if not record:
        return
    todo_db.delete_todo(record_id)
    st.session_state["todo_pending_sync_sha"] = record["_sync_sha"]
    sync_todo_backup_to_github(expected_sha=record["_sync_sha"])


def toggle_todo_done(record_id, checkbox_key):
    record = prepare_todo_edit(record_id)
    if not record:
        return
    if st.session_state.get(checkbox_key):
        todo_db.complete_todo(record_id)
    else:
        todo_db.reopen_todo(record_id)
    st.session_state["todo_pending_sync_sha"] = record["_sync_sha"]
    sync_todo_backup_to_github(expected_sha=record["_sync_sha"])


def render_todo_record(record):
    # Refresh saved values when another device changes this record, preserving unsaved edits otherwise.
    revision_key = f"todo_revision_{record['id']}"
    revision = f"{record['uid']}:{record['updated_at']}"
    if st.session_state.get(revision_key) != revision:
        st.session_state[f"todo_due_date_{record['id']}"] = _compact_date_label(record.get("due_date"))
        st.session_state[f"todo_due_time_{record['id']}"] = str(record.get("due_time") or "")
        st.session_state[revision_key] = revision
    with st.container(key=f"todo-row-{record['id']}"):
        done = record.get("status") == "done"
        stored_due_date = _compact_date_label(record.get("due_date"))
        stored_due_time = str(record.get("due_time") or "")

        check_col, body_col, created_col, spacer_col, due_date_col, due_time_col, save_col, delete_col = st.columns(
            [0.25, 5, 0.75, 0.2, 1, 0.8, 0.35, 0.35],
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
                f"""<div class="todo-date-inline">{_escape_html(_compact_date_label(record.get('record_date', '')))}</div>""",
                unsafe_allow_html=True,
            )
        with spacer_col:
            st.empty()
        with due_date_col:
            new_due_date = st.text_input(
                "截止日期",
                value=stored_due_date,
                key=f"todo_due_date_{record['id']}",
                label_visibility="collapsed",
            )
        with due_time_col:
            due_time_options = _due_time_options(stored_due_time)
            new_due_time = st.selectbox(
                "截止时间",
                options=due_time_options,
                index=_due_time_index(stored_due_time, due_time_options),
                key=f"todo_due_time_{record['id']}",
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


require_todo_auth()
apply_style()
restore_todo_backup_from_github()
todo_db.init_db()
refresh_todos_if_needed()

records_all = todo_db.get_todos(view="all")
active_count = len([record for record in records_all if not record.get("is_archived")])
archived_count = len(
    [record for record in records_all if record.get("is_archived") and record.get("status") != "deleted"]
)

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

render_todo_calendar(records_all)

if st.session_state.pop("todo_save_notice", None) == "synced":
    st.success("待办已保存并同步。")
if pending_todo_sync_sha():
    st.warning(st.session_state.get("todo_sync_error") or "当前环境有已保存、尚未同步的待办修改。")
    if st.button("重试同步", key="todo_retry_sync", help="仅同步已保存的修改，不会重复新增待办"):
        if sync_todo_backup_to_github():
            st.session_state["todo_save_notice"] = "synced"
            st.rerun()

with st.container(border=True):
    st.subheader("快速新增")
    if st.session_state.pop("todo_quick_add_saved", False):
        st.session_state["todo_quick_add_text"] = ""
    with st.form("todo_quick_add", clear_on_submit=False):
        todo_text = st.text_area("待办文本", placeholder="例如：明天下午3点前提交学院材料", height=96,
                                 key="todo_quick_add_text")
        parsed_due_date, parsed_due_time = todo_db.extract_due_fields(todo_text, todo_db.today())
        col_date, col_time, col_save = st.columns([1, 1, 1], vertical_alignment="bottom")
        with col_date:
            due_date = st.date_input("截止日期", value=_date_value(parsed_due_date))
        with col_time:
            quick_due_time_options = _due_time_options(parsed_due_time)
            due_time = st.selectbox(
                "截止时间",
                options=quick_due_time_options,
                index=_due_time_index(parsed_due_time, quick_due_time_options),
            )
        with col_save:
            submitted = st.form_submit_button("保存待办", type="primary", use_container_width=True)
        if submitted:
            try:
                add_todo_from_page(todo_text, due_date, due_time)
            except ValueError as exc:
                st.error(str(exc) or "请输入待办内容后再保存。")

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
