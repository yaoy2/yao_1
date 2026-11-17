"""M34 · Editable, password-protected work playbooks and annual records."""

from datetime import date
import hashlib
import os

import streamlit as st

from utils import budget_auth
from utils import work_guides as guides
from utils import work_guides_sync as cloud
from utils.ui_theme import render_home_link


def clear_private_session(keep_auth=False):
    for key in list(st.session_state):
        if key.startswith("m34_") and not (keep_auth and key == "m34_authenticated"):
            del st.session_state[key]


def require_auth():
    password = budget_auth.get_budget_password(st.secrets, os.environ)
    if not password:
        clear_private_session()
        st.info("工作导航尚未配置访问密码，请沿用工具箱的统一访问密码配置。")
        st.stop()
    fingerprint = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if st.session_state.get("m34_authenticated") == fingerprint:
        return
    clear_private_session()
    st.caption("使用工具箱统一访问密码。")
    with st.form("m34_login"):
        entered = st.text_input("访问密码", type="password")
        submitted = st.form_submit_button("进入工作导航", type="primary")
    if submitted:
        if budget_auth.is_budget_password_valid(entered, password):
            st.session_state["m34_authenticated"] = fingerprint
            st.rerun()
        st.error("密码不正确，请重新输入。")
    st.stop()


def persist(document, guide_id=None):
    st.session_state["m34_draft"] = document
    with st.spinner("正在保存并核对云端内容…"):
        result = cloud.save_document(document, st.session_state["m34_sha"], secrets=st.secrets)
    if not result["ok"]:
        st.session_state["m34_error"] = result["message"]
        st.rerun()
    st.session_state["m34_document"] = result["document"]
    st.session_state["m34_sha"] = result["sha"]
    st.session_state.pop("m34_draft", None)
    st.session_state["m34_flash"] = "已保存，并核对云端内容。"
    st.session_state["m34_new_guide"] = False
    if guide_id:
        st.session_state["m34_selected"] = guide_id
    st.rerun()


def text_field(field, labels, values, prefix, multiline=True):
    renderer = st.text_area if multiline else st.text_input
    kwargs = {"height": 90} if multiline else {}
    return renderer(labels[field], value=values.get(field, ""), key=prefix + field, max_chars=30000, **kwargs)


def optional_date(field, labels, values, prefix):
    current = values.get(field)
    value = st.date_input(labels[field], value=date.fromisoformat(current) if current else None, key=prefix + field)
    return value.isoformat() if value else ""


def guide_editor(document, guide=None, disabled=False):
    guide_id = guide["id"] if guide else None
    prefix = f"m34_guide_{guide_id or 'new'}_{document['revision']}_"
    values = guide or {}
    with st.form(prefix + "form"):
        changes = {"title": text_field("title", guides.GUIDE_FIELDS, values, prefix, False)}
        left, right = st.columns(2)
        with left:
            changes["category"] = text_field("category", guides.GUIDE_FIELDS, values, prefix, False)
        with right:
            changes["frequency"] = text_field("frequency", guides.GUIDE_FIELDS, values, prefix, False)
        for pair in (("summary", "trigger"), ("contacts", "sources"), ("requirements", "pitfalls")):
            for column, field in zip(st.columns(2), pair):
                with column:
                    changes[field] = text_field(field, guides.GUIDE_FIELDS, values, prefix)
        changes["verified_on"] = optional_date("verified_on", guides.GUIDE_FIELDS, values, prefix)
        if guide:
            changes["archived"] = st.checkbox("归档此工作（保留指南和历年记录）", value=guide["archived"], key=prefix + "archived")
        submitted = st.form_submit_button("保存工作指南" if guide else "创建工作指南", type="primary", disabled=disabled)
    if submitted:
        try:
            draft, selected = guides.update_guide(document, changes, guide_id)
            persist(draft, selected)
        except ValueError as exc:
            st.error(str(exc))


def step_editor(document, guide, disabled=False):
    positions = {step["id"]: f"{index + 1} · {step['title']}" + ("（已停用）" if not step["enabled"] else "")
                 for index, step in enumerate(guide["steps"])}
    selected = st.selectbox("选择新增或修改的节点", [None, *positions],
                            format_func=lambda value: positions.get(value, "＋ 新增节点"),
                            key=f"m34_edit_node_{guide['id']}_{document['revision']}")
    step = next((s for s in guide["steps"] if s["id"] == selected), {})
    prefix = f"m34_step_{guide['id']}_{selected or 'new'}_{document['revision']}_"
    if selected:
        st.caption("调整顺序前，请先保存当前节点的文字修改。")
        index = next(i for i, s in enumerate(guide["steps"]) if s["id"] == selected)
        up, down, _space = st.columns([1, 1, 5])
        for column, label, direction, boundary in ((up, "上移", -1, index == 0),
                                                    (down, "下移", 1, index == len(guide["steps"]) - 1)):
            if column.button(label, key=prefix + label, disabled=disabled or boundary):
                persist(guides.move_step(document, guide["id"], selected, direction))
    st.caption("主线按节点顺序连接；可以补充分支或退回，并写明触发条件。")
    with st.form(prefix + "form"):
        changes = {"title": text_field("title", guides.STEP_FIELDS, step, prefix, False)}
        for pair in (("action", "contacts"), ("materials", "output"), ("pitfalls", "sources")):
            for column, field in zip(st.columns(2), pair):
                with column:
                    changes[field] = text_field(field, guides.STEP_FIELDS, step, prefix)
        left, right = st.columns(2)
        with left:
            changes["enabled"] = st.checkbox("显示在办理地图中", value=step.get("enabled", True), key=prefix + "enabled")
            changes["continue_next"] = st.checkbox("主线继续到下一个节点", value=step.get("continue_next", True), key=prefix + "continue_next")
            changes["next_label"] = text_field("next_label", guides.STEP_FIELDS, step, prefix, False)
        with right:
            targets = [None, *[s["id"] for s in guide["steps"] if s["enabled"]]]
            branch = step.get("branch_to") or None
            changes["branch_to"] = st.selectbox("分支 / 退回转到", targets, index=targets.index(branch),
                                                format_func=lambda value: positions.get(value, "无分支"), key=prefix + "branch_to") or ""
            changes["branch_label"] = text_field("branch_label", guides.STEP_FIELDS, step, prefix, False)
        submitted = st.form_submit_button("保存流程节点", type="primary", disabled=disabled)
    if submitted:
        try:
            draft, _step_id = guides.update_step(document, guide["id"], changes, selected)
            persist(draft)
        except ValueError as exc:
            st.error(str(exc))


def record_editor(document, guide, disabled=False):
    records = {record["id"]: record for record in guide["records"]}
    selected = st.selectbox("选择新增或修改的记录", [None, *records],
                            format_func=lambda value: (f"{records[value]['period']} · {records[value]['title']}"
                                                       if value else "＋ 新增办理记录"),
                            key=f"m34_edit_record_{guide['id']}_{document['revision']}")
    values = records.get(selected, {})
    prefix = f"m34_record_{guide['id']}_{selected or 'new'}_{document['revision']}_"
    st.caption("新增时保存一份当时的指南与流程快照；以后修改通用指南，仍可查到当年的做法。")
    with st.form(prefix + "form"):
        changes = {}
        left, right = st.columns(2)
        with left:
            changes["period"] = text_field("period", guides.RECORD_FIELDS, values, prefix, False)
        with right:
            changes["title"] = text_field("title", guides.RECORD_FIELDS, values, prefix, False)
        left, right = st.columns(2)
        with left:
            changes["status"] = st.selectbox("办理状态", guides.STATUSES,
                                             index=guides.STATUSES.index(values.get("status", guides.STATUSES[0])), key=prefix + "status")
        with right:
            changes["handled_on"] = optional_date("handled_on", guides.RECORD_FIELDS, values, prefix)
        for pair in (("contacts", "sources"), ("changes", "actual_steps"), ("materials", "receipt"),
                     ("pitfalls", "next_tips")):
            for column, field in zip(st.columns(2), pair):
                with column:
                    changes[field] = text_field(field, guides.RECORD_FIELDS, values, prefix)
        changes["notes"] = text_field("notes", guides.RECORD_FIELDS, values, prefix)
        submitted = st.form_submit_button("保存办理记录", type="primary", disabled=disabled)
    if submitted:
        try:
            draft, _record_id = guides.update_record(document, guide["id"], changes, selected)
            persist(draft)
        except ValueError as exc:
            st.error(str(exc))


def show_fields(item, labels, fields):
    filled = [field for field in fields if item[field]]
    if not filled:
        st.caption("尚未填写，可在维护指南或办理记录中补充。")
    for field in filled:
        st.markdown(f"**{labels[field]}**")
        st.write(item[field])


def flow_view(document, guide):
    active = [step for step in guide["steps"] if step["enabled"]]
    if not active:
        st.info("还没有启用的流程节点。到“维护指南 → 流程节点”添加第一步。")
        return
    options = {step["id"]: step for step in active}
    names = {step["id"]: f"{index + 1} · {step['title']}" for index, step in enumerate(active)}
    selected = st.radio("点击查看流程节点", list(options), format_func=names.get, horizontal=True,
                        key=f"m34_flow_{guide['id']}_{document['revision']}")
    st.graphviz_chart(guides.flow_dot(guide, selected), width="stretch")
    st.caption("上方点选节点查看做法；实线为主线，虚线为条件分支或退回。")
    step = options[selected]
    left, right = st.columns(2)
    with left:
        show_fields(step, guides.STEP_FIELDS, ("action", "contacts"))
    with right:
        show_fields(step, guides.STEP_FIELDS, ("materials", "output"))
    with st.expander("本步易错点与依据"):
        show_fields(step, guides.STEP_FIELDS, ("pitfalls", "sources"))


def history_view(document, guide, disabled):
    if guide["records"]:
        records = sorted(guide["records"], key=lambda r: (r["period"], r["handled_on"], r["created_at"]), reverse=True)
        options = {record["id"]: record for record in records}
        selected = st.selectbox("查看历年 / 批次记录", list(options),
                                format_func=lambda value: f"{options[value]['period']} · {options[value]['title']} · {options[value]['status']}",
                                key=f"m34_history_{guide['id']}_{document['revision']}")
        record = options[selected]
        st.caption(f"{record['status']} · 办理日期：{record['handled_on'] or '未填写'} · 更新于 {record['updated_at'][:10]}")
        with st.expander("本次要求、办理经过、材料与回执"):
            show_fields(record, guides.RECORD_FIELDS, ("contacts", "changes", "actual_steps", "materials", "receipt", "sources", "notes"))
        with st.expander("本次踩坑与下次提醒", expanded=True):
            show_fields(record, guides.RECORD_FIELDS, ("pitfalls", "next_tips"))
        with st.expander("查看这条记录创建时的指南快照"):
            st.markdown(guides.guide_markdown(record["guide_snapshot"]))
    else:
        st.info("尚未录入历年记录，可以从最近一次办理开始补充。")
    with st.expander("新增 / 修改办理记录", expanded=not guide["records"]):
        record_editor(document, guide, disabled)


def detail_view(document, guide, has_draft):
    if st.button("← 返回工作列表", key="m34_back"):
        st.session_state.pop("m34_selected", None)
        st.rerun()
    st.subheader(guide["title"] + (" · 已归档" if guide["archived"] else ""))
    st.caption("最近核对：" + (guide["verified_on"] or "尚未填写") + " · 往年要求请按本年度通知重新核对。")
    if guide["trigger"]:
        st.write("开始时机：" + guide["trigger"])
    with st.expander("工作简介与对接单位"):
        show_fields(guide, guides.GUIDE_FIELDS, ("summary", "contacts"))
    flow, rules, history, editor = st.tabs(["办理地图", "要求与踩坑", "历年记录", "维护指南"])
    with flow:
        flow_view(document, guide)
    with rules:
        show_fields(guide, guides.GUIDE_FIELDS, ("requirements", "pitfalls", "sources"))
    with history:
        history_view(document, guide, has_draft)
    with editor:
        with st.expander("修改工作基本信息"):
            guide_editor(document, guide, has_draft)
        with st.expander("流程节点：新增、修改与调整顺序", expanded=True):
            step_editor(document, guide, has_draft)
    st.download_button("导出这项工作指南", guides.guide_markdown(guide),
                       "M34_工作指南_" + guides.now()[:10].replace("-", "_") + ".md", "text/markdown", key="m34_export_guide")


def export_all(document):
    with st.expander("备份全部指南与历年记录"):
        st.caption("包含已归档工作、全部流程节点和历年办理快照。")
        st.download_button("下载完整备份", guides.serialize(document),
                           "M34_工作导航_" + guides.now()[:10].replace("-", "_") + ".json", "application/json", key="m34_export_all")


def workspace():
    if "m34_document" not in st.session_state:
        with st.spinner("正在读取工作指南…"):
            result = cloud.load_document(secrets=st.secrets)
        if not result["ok"]:
            st.error(result["message"])
            if st.button("重试读取", key="m34_retry"):
                st.rerun()
            if st.button("退出访问", key="m34_failed_logout"):
                clear_private_session()
                st.rerun()
            st.stop()
        st.session_state["m34_document"] = result["document"]
        st.session_state["m34_sha"] = result["sha"]
    document = st.session_state["m34_document"]
    if st.session_state.get("m34_flash"):
        st.success(st.session_state.pop("m34_flash"))
    if st.session_state.get("m34_error"):
        st.error(st.session_state.pop("m34_error"))
    has_draft = "m34_draft" in st.session_state
    may_refresh = True
    if has_draft:
        st.warning("有一次未确认保存的草稿。请先下载保留，再刷新核对；核对前暂不继续编辑。")
        st.download_button("下载未保存草稿", guides.serialize(st.session_state["m34_draft"]),
                           "M34_工作导航_未保存草稿_" + guides.now()[:10].replace("-", "_") + ".json",
                           "application/json", key="m34_download_draft")
        may_refresh = st.checkbox("我已保留草稿，允许重新读取云端", key="m34_allow_refresh")
    label, add, refresh, logout = st.columns([6, 1.3, 1.3, 1.3])
    label.caption("每件工作留下一份可复用的做法，按年度或批次保留办理经过。")
    if add.button("新增工作", disabled=has_draft, key="m34_add"):
        st.session_state["m34_new_guide"] = True
    if refresh.button("刷新云端", disabled=not may_refresh, key="m34_refresh"):
        clear_private_session(keep_auth=True)
        st.rerun()
    if logout.button("退出访问", key="m34_logout"):
        clear_private_session()
        st.rerun()
    if st.session_state.get("m34_new_guide"):
        st.subheader("新增工作指南")
        guide_editor(document, disabled=has_draft)
        if st.button("取消新增", key="m34_cancel_new"):
            st.session_state["m34_new_guide"] = False
            st.rerun()
        return
    if not document["guides"]:
        st.info("还没有工作指南。点击“新增工作”，先记录一件最容易忘记的年度工作。")
        return
    selected = st.session_state.get("m34_selected")
    if selected:
        detail_view(document, guides.get_guide(document, selected), has_draft)
        export_all(document)
        return
    search, category, archived = st.columns([4, 2, 2])
    query = search.text_input("查找工作、单位、节点或历年记录", key="m34_search")
    categories = ["全部分类", *sorted({g["category"] for g in document["guides"] if g["category"]})]
    selected_category = category.selectbox("工作分类", categories, key="m34_category")
    include_archived = archived.checkbox("含已归档工作", key="m34_archived")
    matching = guides.search_guides(document, query, selected_category, include_archived)
    st.caption(f"找到 {len(matching)} 项工作 · 点击“查看指南”进入详情")
    if not matching:
        st.info("没有匹配工作，可调整关键词、分类或归档选项。")
    page_size = 8
    total_pages = max(1, (len(matching) + page_size - 1) // page_size)
    page = st.number_input("工作列表页码", min_value=1, max_value=total_pages, value=1,
                           key="m34_list_page_" + hashlib.sha256(f"{query}|{selected_category}|{include_archived}|{total_pages}".encode()).hexdigest()[:12]) if total_pages > 1 else 1
    for guide in matching[(page - 1) * page_size:page * page_size]:
        with st.container(border=True):
            left, right = st.columns([7, 1.5])
            left.write(guide["title"] + (" · 已归档" if guide["archived"] else ""))
            left.caption(" · ".join(filter(None, [guide["category"], guide["frequency"],
                                                 f"{sum(s['enabled'] for s in guide['steps'])}个节点", f"{len(guide['records'])}条办理记录"])))
            if right.button("查看指南", key="m34_open_" + guide["id"], width="stretch"):
                st.session_state["m34_selected"] = guide["id"]
                st.rerun()
    export_all(document)


def main():
    st.set_page_config(page_title="M34 · 工作导航", page_icon="🧭", layout="wide")
    render_home_link()
    st.title("🧭 M34 · 工作导航")
    require_auth()
    workspace()


if __name__ == "__main__":
    main()
