"""M24: public mail summary view with authenticated action-status editing."""

import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from html import escape
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import parse_qsl, urlsplit

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import budget_auth
from utils.mail_report_view import REPORT_CSS, report_body_html, report_title
from utils.ui_theme import render_home_link


BJT = timezone(timedelta(hours=8), "Asia/Shanghai")
STATUSES = {
    "pending": "待处理",
    "in_progress": "进行中",
    "done": "已完成",
    "needs_confirmation": "待确认",
}
KINDS = {"daily": "每日归档与简报", "morning": "早间到期提醒", "weekly": "每周汇总", "sample": "样本试跑"}
ATTACHMENT_STATUSES = {"success": "已归档并核验", "missing": "未取得文件", "error": "归档失败", "pending": "待下载"}
ERRORS = {
    "missing_token": "私有邮件数据源尚未配置，暂时无法读取邮件。",
    "missing_config": "私有邮件数据源尚未配置，暂时无法读取邮件。",
    "invalid_config": "私有邮件数据源配置有误，暂时无法读取邮件。",
    "repo_not_found": "私有邮件数据仓库不存在，或当前连接无权访问。",
    "snapshot_not_found": "私有数据源尚无邮件快照，请先完成一次采集和同步。",
    "local_read_error": "指定的本机邮件快照无法读取，请核对归档结果。",
    "unauthorized": "私有邮件数据源授权已失效，需要更新连接授权。",
    "forbidden": "当前连接没有访问私有邮件数据源的权限。",
    "public_repo": "邮件数据源指向公开仓库，已停止读取。请使用私有数据源。",
    "conflict": "数据已有更新，本次未保存。您的编辑已保留；请刷新数据，核对最新状态后再保存。",
    "readonly": "当前为本机只读数据，暂不支持保存状态。",
    "invalid_update": "待办已变化或状态无效，本次未保存。请刷新数据后核对。",
    "invalid_snapshot": "邮件数据格式不完整，无法展示。请检查最近一次采集结果。",
    "not_found": "尚未找到邮件数据。请先完成一次采集和私有同步。",
}


def plain_label(value):
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|~-])", r"\\\1", str(value or ""))


def parse_time(value, *, deadline=False):
    """Use Beijing time, and never turn a date-only deadline into midnight."""
    if not value:
        return None
    text = str(value).strip()
    try:
        if len(text) == 10:
            parsed_date = date.fromisoformat(text)
            return datetime.combine(parsed_date, time.max if deadline else time.min, BJT)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=BJT) if parsed.tzinfo is None else parsed.astimezone(BJT)
    except (ValueError, TypeError):
        return None


def display_time(value, *, deadline=False):
    parsed = parse_time(value, deadline=deadline)
    if not parsed:
        return "未明确" if deadline else "未记录"
    if len(str(value).strip()) == 10:
        return parsed.strftime("%Y-%m-%d") + ("（具体时刻以截止原文为准）" if deadline else "")
    return parsed.strftime("%Y-%m-%d %H:%M")


def safe_source_url(value):
    """Only the known school OWA item page may become a clickable source."""
    if not isinstance(value, str) or any(char.isspace() for char in value):
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme != "https" or parts.hostname != "mail.nsu.edu.cn"
                or parts.port not in (None, 443) or parts.username or parts.password
                or parts.path != "/owa/" or parts.fragment):
            return None
        allowed = {"ae", "a", "t", "id", "ItemID", "exvsurl", "viewmodel"}
        if any(key not in allowed for key, _ in parse_qsl(parts.query, keep_blank_values=True)):
            return None
        return value
    except ValueError:
        return None


def relative_archive_path(value):
    """The cloud page displays an index; it never dereferences a local path."""
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return "未记录"
    win_path, posix_path = PureWindowsPath(text), PurePosixPath(text)
    if win_path.drive or win_path.root or posix_path.is_absolute() or ".." in posix_path.parts:
        return "需补充相对位置"
    return text


def source_link_label(url):
    if not safe_source_url(url):
        return None
    query = {key.lower(): value for key, value in parse_qsl(urlsplit(url).query)}
    if query.get("ae", "").lower() == "item" and (query.get("id") or query.get("itemid")):
        return "打开原邮件"
    return "打开学校邮箱"


def incomplete_attachment_count(messages):
    return sum(attachment.get("status") != "success"
               for message in messages for attachment in message.get("attachments", []))


def coverage_warning(snapshot):
    coverage = snapshot.get("coverage") or {}
    runs = snapshot.get("runs", [])
    if runs and all(run.get("kind") == "sample" for run in runs):
        return "当前为试跑数据，用于检查读取和展示效果；还没有完成首次正式采集。"
    if not coverage.get("complete"):
        return "部分邮件或附件仍待核对，尚不能确认该时段已检查完整。详情见运行记录。"
    if not parse_time(coverage.get("since")) or not parse_time(coverage.get("through")):
        return "尚未记录检查的起止时间，需要核对运行记录。"
    return None


def snapshot_status_html(snapshot):
    runs = snapshot.get("runs", [])
    if runs and all(run.get("kind") == "sample" for run in runs):
        label = "试跑数据"
    elif coverage_warning(snapshot):
        label = "采集待补全" if runs else "待首次采集"
    else:
        label = "已完成时段核对"
    messages = snapshot.get("messages", [])
    incomplete = incomplete_attachment_count(messages)
    attachment_count = sum(len(message.get("attachments", [])) for message in messages)
    attachment_label = (f'{incomplete} 份附件待补' if incomplete else
                        ("现有附件均已归档" if attachment_count else "暂无附件记录"))
    attachment_class = "mail-attachment-pending" if incomplete else ""
    return (f'<div class="mail-status-bar"><span class="mail-status-chip">{escape(label)}</span>'
            f'<span>已整理 {len(messages)} 封邮件</span>'
            f'<span class="{attachment_class}">{attachment_label}</span></div>')


def run_status_label(run):
    if run.get("kind") == "sample" and run.get("status") == "success":
        return "样本处理成功（不代表全量）"
    return {"success": "本次任务成功", "partial": "部分完成", "error": "失败", "failed": "失败"}.get(run.get("status"), "结果未确认")


def filter_messages(messages, start, end, category="全部"):
    selected = []
    for message in messages:
        received = parse_time(message.get("received_at"))
        if received and start <= received.date() <= end:
            if category == "全部" or (message.get("category") or "未分类") == category:
                selected.append(message)
    return sorted(selected, key=lambda item: parse_time(item["received_at"]), reverse=True)


def filter_actions(actions, messages, view, now, category="全部"):
    by_id = {item.get("id"): item for item in messages}
    selected = []
    for action in actions:
        message = by_id.get(action.get("message_id"), {})
        if category != "全部" and (message.get("category") or "未分类") != category:
            continue
        due = parse_time(action.get("due_at"), deadline=True)
        active = action.get("status") != "done"
        matches = {
            "未完成": active,
            "今天": active and due is not None and due.date() == now.date(),
            "未来7天": active and due is not None and now.date() <= due.date() <= now.date() + timedelta(days=6),
            "逾期": active and due is not None and due < now,
            "待确认": active and (action.get("status") == "needs_confirmation" or due is None),
            "已完成": not active,
            "全部": True,
        }
        if matches.get(view, False):
            selected.append(action)
    return sorted(selected, key=lambda item: (
        item.get("status") == "done",
        parse_time(item.get("due_at"), deadline=True) or datetime.max.replace(tzinfo=BJT),
        str(item.get("id", "")),
    ))


def build_action_updates(actions, drafts):
    return {str(item["id"]): drafts[str(item["id"])] for item in actions
            if str(item["id"]) in drafts and drafts[str(item["id"])] in STATUSES
            and drafts[str(item["id"])] != item.get("status")}


def render_edit_access():
    password = budget_auth.get_budget_password(st.secrets, os.environ)
    if not password:
        st.session_state.pop("mail_authenticated", None)
        st.caption("可直接浏览。待办编辑密码尚未配置，暂不能修改状态。")
        return False
    if st.session_state.get("mail_authenticated"):
        st.caption("待办编辑已启用。")
        return True
    with st.expander("启用待办编辑", expanded=False):
        st.caption("浏览不需要密码；修改待办状态时，使用预算台账的访问密码确认。")
        with st.form("mail_auth_form"):
            value = st.text_input("编辑密码", type="password")
            if st.form_submit_button("启用编辑", use_container_width=True):
                if budget_auth.is_budget_password_valid(value, password):
                    st.session_state["mail_authenticated"] = True
                    st.rerun()
                st.error("密码不正确，请重新输入。")
    return False


def show_data_error(exc, *, saving=False):
    code = getattr(exc, "code", "")
    fallback = ("保存失败，您的编辑已保留。请检查连接后重试。" if saving
                else "邮件数据读取失败，无法确认最新内容。请检查数据源连接后重试。")
    st.error(ERRORS.get(code, fallback))


def refresh_snapshot(gateway):
    # Keep drafts separately: neither a network error nor refresh may erase edits.
    loaded = gateway.load_snapshot(secrets=st.secrets, environ=os.environ)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("snapshot"), dict):
        raise ValueError("Invalid snapshot envelope")
    st.session_state["mail_loaded"] = loaded
    return loaded


def save_drafts(gateway, loaded, drafts):
    # Enforce write authorization here, independent of disabled browser widgets.
    if not st.session_state.get("mail_authenticated") or not budget_auth.get_budget_password(st.secrets, os.environ):
        raise PermissionError("请先启用待办编辑，再保存状态。")
    updates = build_action_updates(loaded["snapshot"].get("actions", []), drafts)
    if not updates:
        return False
    saved = gateway.save_action_updates(
        updates, expected_version=loaded["version"], secrets=st.secrets, environ=os.environ,
    )
    if not isinstance(saved, dict) or not isinstance(saved.get("snapshot"), dict):
        raise ValueError("Invalid save response")
    st.session_state["mail_loaded"] = saved
    for action_id in updates:
        drafts.pop(action_id, None)
        # Widget state is cleared before widgets are constructed on the next run.
        st.session_state.pop(f"mail_status_{action_id}", None)
    return True


def render_source(message):
    url = safe_source_url(message.get("source_url"))
    if url:
        label = source_link_label(url)
        st.link_button(label, url)
        if label == "打开学校邮箱":
            st.caption("当前保存的是邮箱入口，请按主题和发件人查找原邮件。")
    else:
        st.caption("原邮件直达链接未记录或不可用；可在学校邮箱按主题和发件人搜索。")


def render_message(message):
    with st.expander(plain_label(f"{display_time(message.get('received_at'))} · {message.get('subject') or '无主题'}")):
        st.caption(plain_label(f"发件人：{message.get('sender') or '未记录'} · 分类：{message.get('category') or '未分类'} · 文件夹：{message.get('folder') or '未记录'}"))
        st.text(message.get("summary") or "尚未生成摘要。")
        render_source(message)


def render_reports(reports, kinds, start=None, end=None):
    selected = []
    for report in reports:
        report_date = parse_time(report.get("date") or report.get("generated_at"))
        if report.get("kind") in kinds and (start is None or (report_date and start <= report_date.date() <= end)):
            selected.append(report)
    for report in sorted(selected, key=lambda item: str(item.get("generated_at", "")), reverse=True):
        with st.expander(plain_label(report_title(report))):
            st.caption(f"统计时段：{display_time(report.get('period_start'))} 至 {display_time(report.get('period_end'))} · 生成于 {display_time(report.get('generated_at'))}")
            # Only fixed HTML elements are emitted; all mail text is escaped.
            st.markdown(report_body_html(report.get("markdown")), unsafe_allow_html=True)
    if not selected:
        st.info("此范围内尚无已生成的报告。")


def render_actions(snapshot, loaded, gateway, category, now):
    drafts = st.session_state.setdefault("mail_action_drafts", {})
    by_id = {item.get("id"): item for item in snapshot.get("messages", [])}
    readonly = loaded.get("source") != "github" or not st.session_state.get("mail_authenticated")
    st.caption("待办按截止时间筛选，不受收件日期范围限制。未明确的时间单列待确认；这里的状态只更新工作台。")
    view = st.radio("待办视图", ["未完成", "今天", "未来7天", "逾期", "待确认", "已完成", "全部"], horizontal=True)
    pending = build_action_updates(snapshot.get("actions", []), drafts)
    if loaded.get("source") != "github":
        st.info("当前读取本机快照；连接私有同步数据源后可在网页更新状态。")
    elif readonly:
        st.info("当前为公开浏览。需要修改状态时，请在页面上方启用待办编辑。")
    if st.button(f"保存状态修改（{len(pending)}项）", disabled=readonly or not pending, type="primary"):
        try:
            if save_drafts(gateway, loaded, drafts):
                st.session_state["mail_save_notice"] = "状态已保存到私有数据源。"
                st.rerun()
        except Exception as exc:
            show_data_error(exc, saving=True)
    actions = filter_actions(snapshot.get("actions", []), snapshot.get("messages", []), view, now, category)
    if not actions:
        st.info("此视图内没有匹配的待办。")
    for action in actions:
        action_id = str(action["id"])
        message = by_id.get(action.get("message_id"), {})
        body, due_col, status_col = st.columns([5, 2.3, 1.8], vertical_alignment="center")
        with body:
            st.text(action.get("title") or action.get("requirement") or "未命名事项")
            st.caption(plain_label(f"责任对象：{action.get('owner') or '待确认'} · 来源：{message.get('subject') or '原邮件索引未提供'}"))
        with due_col:
            due = parse_time(action.get("due_at"), deadline=True)
            label = display_time(action.get("due_at"), deadline=True)
            st.caption(("🔴 已逾期 · " if due and due < now and action.get("status") != "done" else "截止：") + label)
            if action.get("due_text"):
                st.caption(plain_label("原文：" + str(action["due_text"])))
        with status_col:
            key = f"mail_status_{action_id}"
            current = action.get("status") if action.get("status") in STATUSES else "needs_confirmation"
            # A separate draft survives Streamlit's cleanup of hidden widget state.
            st.session_state[key] = current if readonly else drafts.get(action_id, current)
            st.selectbox("处理状态", list(STATUSES), key=key, format_func=STATUSES.get,
                         disabled=readonly, label_visibility="collapsed",
                         on_change=remember_status, args=(action_id,))
        with st.expander("要求、截止依据与提交方式", expanded=False):
            st.text(action.get("requirement") or "具体要求待确认。")
            st.text("截止原文：" + str(action.get("due_text") or "原文未明确截止时间。"))
            st.text("判断依据：" + str(action.get("due_basis") or "未提供，需核对原邮件及附件。"))
            st.text("提交对象：" + str(action.get("recipient") or "待确认"))
            st.text("提交方式：" + str(action.get("submission_method") or "待确认"))
            st.caption(f"已存状态：{STATUSES.get(action.get('status'), '待确认')} · 最近更新：{display_time(action.get('updated_at'))}")
            render_source(message)


def remember_status(action_id):
    st.session_state.setdefault("mail_action_drafts", {})[action_id] = st.session_state[f"mail_status_{action_id}"]


def render_attachments(messages):
    st.caption("显示本机归档目录下的相对位置。附件文件保存在本机，网页不提供本机文件的下载按钮。")
    incomplete = incomplete_attachment_count(messages)
    if incomplete:
        st.caption(f"当前筛选范围有 {incomplete} 份附件待补，具体原因见下表。")
    rows = []
    for message in messages:
        for attachment in message.get("attachments", []):
            rows.append({
                "收件时间": display_time(message.get("received_at")), "邮件主题": message.get("subject", ""),
                "附件": attachment.get("name", ""), "状态": ATTACHMENT_STATUSES.get(attachment.get("status"), "未核验"),
                "字节数": attachment.get("size"), "本机相对位置": relative_archive_path(attachment.get("path")),
                "失败原因": attachment.get("error") or "", "SHA-256": attachment.get("sha256") or "未核验",
            })
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("当前筛选范围内没有附件索引。")


def main():
    st.set_page_config(page_title="M24 · 邮件工作台", page_icon="✉️", layout="wide")
    render_home_link()
    st.title("邮件工作台")
    editing = render_edit_access()
    # Summaries are public; the private-source module still protects the backing
    # repository and excludes raw mail bodies. Passwords authorize status writes.
    from utils import mail_private_sync

    st.markdown("""<style>
    .block-container {padding-top:1.3rem; padding-bottom:2rem;}
    [data-testid="stVerticalBlock"] {gap:.6rem;}
    [data-testid="stMetricValue"] {font-size:1.55rem;}
    [data-testid="stExpander"] details summary p {font-size:.88rem;}
    </style>""", unsafe_allow_html=True)
    st.markdown("<style>" + REPORT_CSS + "</style>", unsafe_allow_html=True)
    st.caption("计划时间（北京时间）：每日 20:00 归档与简报 · 周一至五 09:00 到期提醒 · 周五 17:00 每周汇总")
    refresh_col, logout_col = st.columns([5, 1])
    refresh = refresh_col.button("刷新数据（保留未保存编辑）")
    if editing and logout_col.button("退出编辑"):
        for key in list(st.session_state):
            if key in {"mail_authenticated", "mail_action_drafts"} or str(key).startswith("mail_status_"):
                del st.session_state[key]
        st.rerun()
    loaded = st.session_state.get("mail_loaded")
    if refresh or loaded is None:
        try:
            loaded = refresh_snapshot(mail_private_sync)
            if st.session_state.get("mail_action_drafts"):
                st.info("已刷新最新数据并保留编辑。请核对各事项的已存状态，再保存修改。")
        except Exception as exc:
            st.session_state.pop("mail_loaded", None)
            show_data_error(exc)
            st.stop()
    snapshot = loaded["snapshot"]
    coverage = snapshot.get("coverage") or {}
    st.caption(plain_label(f"账户：{snapshot.get('account') or '未记录'} · 数据更新：{display_time(snapshot.get('updated_at'))} · 来源：{'私有同步' if loaded.get('source') == 'github' else '本机只读快照'}"))
    st.markdown(snapshot_status_html(snapshot), unsafe_allow_html=True)
    with st.expander("数据状态详情", expanded=False):
        warning = coverage_warning(snapshot)
        if warning:
            st.text(warning)
        if parse_time(coverage.get("since")) and parse_time(coverage.get("through")):
            st.caption(f"已检查时段：{display_time(coverage.get('since'))} 至 {display_time(coverage.get('through'))}")
            st.caption("该时段之外的历史邮件不在本次完整检查范围内。")
        incomplete = incomplete_attachment_count(snapshot.get("messages", []))
        if incomplete:
            st.caption(f"另有 {incomplete} 份附件待补，文件名和原因见“附件索引”。")
        elif not warning:
            st.caption("上述时段已核对完成，现有附件均已归档。")
    if st.session_state.get("mail_save_notice"):
        st.success(st.session_state.pop("mail_save_notice"))

    now = datetime.now(BJT)
    date_col, category_col = st.columns([3, 2])
    period = date_col.date_input("收件 / 报告日期范围", value=(now.date() - timedelta(days=6), now.date()))
    categories = sorted({str(item.get("category") or "未分类") for item in snapshot.get("messages", [])})
    category = category_col.selectbox("邮件分类", ["全部", *categories])
    if not isinstance(period, (tuple, list)) or len(period) != 2:
        st.info("请选择起止两个日期。")
        st.stop()
    start, end = period
    messages = filter_messages(snapshot.get("messages", []), start, end, category)
    daily, actions_tab, attachments_tab, runs_tab = st.tabs(["每日简报", "到期待办", "附件索引", "运行与周报"])
    with daily:
        cols = st.columns(3)
        cols[0].metric("范围内邮件", len(messages))
        cols[1].metric("附件索引", sum(len(item.get("attachments", [])) for item in messages))
        cols[2].metric("未完成事项（不限收件日期）", len(filter_actions(snapshot.get("actions", []), snapshot.get("messages", []), "未完成", now, category)))
        st.caption("报告覆盖选定日期的全部分类；下方逐封邮件遵循分类筛选。")
        render_reports(snapshot.get("reports", []), {"daily", "morning"}, start, end)
        st.subheader("邮件摘要")
        for message in messages:
            render_message(message)
        if not messages:
            st.info("此范围内未记录邮件；不代表邮箱没有来信，请同时核对采集范围与运行结果。")
    with actions_tab:
        render_actions(snapshot, loaded, mail_private_sync, category, now)
    with attachments_tab:
        render_attachments(messages)
    with runs_tab:
        st.caption("这里记录实际执行结果。计划时间不等于已经执行；周一至五暂不调整节假日和调休。")
        st.subheader("实际运行记录")
        runs = snapshot.get("runs", [])
        if runs:
            rows = [{"任务": KINDS.get(run.get("kind"), run.get("kind", "未记录")),
                     "开始": display_time(run.get("started_at")), "结束": display_time(run.get("finished_at")),
                     "结果": run_status_label(run), "邮件数": run.get("message_count", 0),
                     "附件数": run.get("attachment_count", 0),
                     "失败与待补项": "；".join(str(item) for item in (run.get("errors") or []))}
                    for run in sorted(runs, key=lambda item: str(item.get("started_at", "")), reverse=True)]
            st.dataframe(rows, hide_index=True, use_container_width=True)
        else:
            st.info("尚无实际运行记录，不能据计划时间判断任务已执行。")
        st.subheader("每周汇总")
        render_reports(snapshot.get("reports", []), {"weekly"}, start, end)


if __name__ == "__main__":
    main()
