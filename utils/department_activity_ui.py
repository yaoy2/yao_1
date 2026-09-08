"""Compact monthly department budget panel used by the existing budget page."""

from collections import Counter

import pandas as pd
import streamlit as st

from utils import department_activity as activity


def _month_text(months):
    return "、".join(f"{month}月" for month in months)


def _save(data, snapshot, state_key):
    try:
        result = activity.save_budget(data, snapshot, secrets=st.secrets)
    except (ValueError, RuntimeError) as exc:
        st.error(str(exc))
    except Exception:
        st.error("保存未获确认，请先刷新最新数据核对；当前填写内容仍保留在表单中。")
    else:
        st.session_state[state_key] = result
        st.session_state[f"{state_key}_expanded"] = True
        st.session_state[f"{state_key}_notice"] = result.get("warning") or (
            "部门活动预算已保存到云端。" if result["source"] == "github" else "部门活动预算已保存到本机。")
        st.rerun()


def _autosave_roster(state_key, grid_key, editor_key):
    """Run before rendering so totals reflect the edit in the same rerun."""
    snapshot = st.session_state[state_key]
    try:
        updated = activity.apply_roster_editor(
            snapshot["data"], st.session_state[grid_key], st.session_state.get(editor_key, {}))
        if updated["months"] == snapshot["data"]["months"]:
            st.session_state.pop(f"{state_key}_editor_error", None)
            st.session_state.pop(f"{state_key}_draft", None)
            return
        st.session_state[f"{state_key}_draft"] = updated
        result = activity.save_budget(updated, snapshot, secrets=st.secrets)
    except (ValueError, RuntimeError) as exc:
        st.session_state[f"{state_key}_editor_error"] = str(exc)
    except Exception:
        st.session_state[f"{state_key}_editor_error"] = "连接或保存未获确认，请重试；表内修改已保留。"
    else:
        # Keep both the grid base and widget key stable across saves. The widget
        # reports cumulative edits; rebuilding it here loses focus and edits.
        st.session_state[state_key] = result
        st.session_state[f"{state_key}_expanded"] = True
        st.session_state[f"{state_key}_notice"] = result.get("warning") or (
            "已自动保存到云端，人数和金额已更新。" if result["source"] == "github"
            else "已自动保存到本机，人数和金额已更新。")
        st.session_state.pop(f"{state_key}_editor_error", None)
        st.session_state.pop(f"{state_key}_draft", None)


def _editor_base(state_key, grid_key, editor_key):
    # Streamlit removes a widget's state when navigating away from its page.
    # Rebuild from saved data (or a retained draft) when returning, instead of
    # displaying the old base without its now-missing cumulative edits.
    if grid_key not in st.session_state or editor_key not in st.session_state:
        data = st.session_state.get(f"{state_key}_draft", st.session_state[state_key]["data"])
        st.session_state[grid_key] = activity.roster_editor_columns(data)
    return st.session_state[grid_key]


def render_department_activity_budget(year):
    with st.expander("👥 部门活动经费 · 点击展开详情",
                     expanded=st.session_state.get(f"department_activity_{year}_expanded", False)):
        _render_details(year)


def _render_details(year):
    today = activity.today_in_shanghai()
    cutoff = activity.cutoff_month(year, today)
    st.caption(f"{year}年度 · 每人每月{activity.MONTHLY_RATE}元 · 截至{today:%Y-%m-%d}（北京时间），"
               + (f"累计计入1—{cutoff}月，未来月份暂不计入。" if cutoff else "本年度尚未开始累计。"))
    state_key = f"department_activity_{year}"
    grid_key = f"{state_key}_editor_base"
    has_error = bool(st.session_state.get(f"{state_key}_editor_error"))
    refresh_label = "重新加载（放弃未保存修改）" if has_error else "↻ 刷新最新数据"
    if st.button(refresh_label, key=f"{state_key}_refresh"):
        for key in (state_key, grid_key, f"{state_key}_draft", f"{state_key}_editor_error"):
            st.session_state.pop(key, None)
        st.session_state[f"{state_key}_revision"] = st.session_state.get(f"{state_key}_revision", 0) + 1
    notice = st.session_state.pop(f"{state_key}_notice", None)
    if notice:
        st.info(notice)
    if state_key not in st.session_state:
        try:
            st.session_state[state_key] = activity.load_budget(year, secrets=st.secrets)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
            return
        except Exception:
            st.error("暂时无法读取部门活动预算，请稍后刷新最新数据。")
            return
    snapshot = st.session_state[state_key]
    data = st.session_state.get(f"{state_key}_draft", snapshot["data"])
    summary = activity.summarize(data, today)
    revision = st.session_state.get(f"{state_key}_revision", 0)
    widget_key = f"{state_key}_{snapshot['version']}_{revision}"
    editor_key = f"{state_key}_roster_editor_{revision}"
    base_columns = _editor_base(state_key, grid_key, editor_key)
    error = st.session_state.get(f"{state_key}_editor_error")
    if error:
        st.error(f"自动保存失败：{error}")
        st.caption("下方统计为当前修改的预览，尚未保存。可以继续修改表格或重试保存。")
        st.button("重试自动保存", on_click=_autosave_roster, args=(state_key, grid_key, editor_key),
                  key=f"{state_key}_retry")
    if snapshot["source"] == "local":
        st.caption("当前为本机保存模式；跨设备保留需要配置现有的预算云端备份。")
    if data.get("updated_at"):
        st.caption(f"名单与报销登记更新时间：{data['updated_at'].replace('T', ' ')}")

    total_col, paid_col, balance_col = st.columns(3)
    total_col.metric("截至当前月份的预算总额", "待补全" if summary["total"] is None else f"¥{summary['total']:,.2f}")
    if summary["missing_months"]:
        total_col.caption(f"已录入部分：¥{summary['known_total']:,.2f}；待补全：{_month_text(summary['missing_months'])}")
    paid_col.metric("已报销金额", "待确认" if summary["reimbursed"] is None else f"¥{summary['reimbursed']:,.2f}")
    paid_col.caption("已报销月份：" + (_month_text(summary["reimbursed_months"]) if summary["reimbursed_months"]
                                   else "尚未确认" if summary["reimbursed"] is None else "无"))
    balance_pending = "待补全名单" if summary["total"] is None else "待确认报销"
    balance_col.metric("余额", balance_pending if summary["balance"] is None else f"¥{summary['balance']:,.2f}")
    balance_col.caption("余额 = 当前预算总额 − 已报销月份金额")

    detail_tab, paid_tab = st.tabs(["月度名单（直接编辑）", "报销登记"])
    with detail_tab:
        st.caption("每格一人：清空姓名可减人，在空白格或表尾新增行输入姓名可加人。按 Enter 或点击别处后自动保存并更新统计，也支持复制粘贴。")
        monthly = activity.monthly_rows(data, today)
        totals = pd.DataFrame({row["月份"]: [
            "待补全" if row["预算（元）"] is None else f"{row['预算（元）']:,}",
            "待补全" if row["教师人数"] is None else str(row["教师人数"]),
        ] for row in monthly}, index=["费用（元）", "人数"])
        column_config = {f"{month}月": st.column_config.TextColumn(f"{month}月", width="small")
                         for month in range(1, 13)}
        st.dataframe(totals, width="stretch", height=126, row_height=30,
                     column_config=column_config)
        # This input frame remains unchanged until an explicit reload. Counts
        # above read the saved/draft budget, while the editor keeps empty cells.
        frame = pd.DataFrame(base_columns, dtype="string")
        frame.index = pd.RangeIndex(1, len(frame) + 1, name="序号")
        st.data_editor(frame, width="stretch", height=560, row_height=30,
                       num_rows="add", disabled=["_index"], placeholder="",
                       column_config=column_config, key=editor_key,
                       on_change=_autosave_roster, args=(state_key, grid_key, editor_key))
        duplicates = [f"{month}月：" + "、".join(name for name, count in Counter(names or []).items() if count > 1)
                      for month, names in data["months"].items()
                      if any(count > 1 for count in Counter(names or []).values())]
        if duplicates:
            st.caption("同名记录分别计人数，请核对：" + "；".join(duplicates))
        st.caption("每个月独立统计；已勾选报销的月份，其报销金额也随名单人数重新计算。")

    with paid_tab:
        eligible = [month for month in range(1, cutoff + 1) if data["months"][str(month)] is not None]
        st.caption("按预算所属月份勾选，可只选1月和3月；每月按整月预算登记，金额自动相加。")
        with st.form(f"{widget_key}_reimbursement"):
            paid = st.multiselect(
                "已报销月份", eligible,
                default=[month for month in data["reimbursed_months"] if month in eligible],
                format_func=lambda month: f"{month}月 · ¥{len(data['months'][str(month)]) * activity.MONTHLY_RATE:,.2f}")
            submitted_paid = st.form_submit_button("💾 保存报销月份（未选择表示暂无报销）", disabled=bool(error))
        if submitted_paid:
            try:
                updated = activity.set_reimbursed_months(data, paid, today)
            except ValueError as exc:
                st.error(str(exc))
            else:
                _save(updated, snapshot, state_key)
        st.caption("本区登记预算月份的报销情况；支出流水仍按实际费用记录，不会重复生成流水。")
        st.dataframe(pd.DataFrame(activity.monthly_rows(data, today)), use_container_width=True, hide_index=True)
