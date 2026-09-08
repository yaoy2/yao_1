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
        st.session_state.pop(state_key, None)
        st.session_state[f"{state_key}_expanded"] = True
        st.session_state[f"{state_key}_notice"] = result.get("warning") or (
            "部门活动预算已保存到云端。" if result["source"] == "github" else "部门活动预算已保存到本机。")
        st.rerun()


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
    if st.button("↻ 刷新最新数据", key=f"{state_key}_refresh"):
        st.session_state.pop(state_key, None)
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
    data = snapshot["data"]
    summary = activity.summarize(data, today)
    revision = st.session_state.get(f"{state_key}_revision", 0)
    widget_key = f"{state_key}_{snapshot['version']}_{revision}"
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

    selected = st.selectbox("人员变动月份", list(range(1, 13)), index=max(1, cutoff) - 1,
                            format_func=lambda month: f"{month}月", key=f"{state_key}_month")
    names = data["months"][str(selected)]
    detail_tab, people_tab, paid_tab, bulk_tab = st.tabs(["月度明细", "新入职 / 离职", "报销登记", "整月名单"])

    with detail_tab:
        st.markdown(activity.build_roster_html(data, selected), unsafe_allow_html=True)
        st.caption(f"浅绿色为{selected}月。费用 = 当月人数 × {activity.MONTHLY_RATE}元；月份、费用和人数固定在表格顶部。")

    with people_tab:
        if names is None:
            st.info(f"{selected}月尚未录入完整名单，请在“整月名单”中录入或从已有月份复制，再增减人员。")
        else:
            st.caption(f"{selected}月现有{len(names)}人，预算{len(names) * activity.MONTHLY_RATE:,}元。")
            with st.form(f"{widget_key}_people_{selected}"):
                add_col, remove_col = st.columns(2)
                with add_col:
                    additions = st.text_input("新入职姓名", placeholder="可输入多人，用逗号或顿号分隔")
                with remove_col:
                    removals = st.multiselect("选择离职人员", list(range(len(names))),
                                              format_func=lambda index: f"{index + 1}. {names[index]}")
                changed = st.form_submit_button("保存人员变动并更新金额", type="primary")
            if changed:
                try:
                    updated = activity.change_people(data, selected, activity.parse_names(additions), removals)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    _save(updated, snapshot, state_key)
            duplicates = [name for name, count in Counter(names).items() if count > 1]
            if duplicates:
                st.caption("以下同名记录分别计人数，请核对：" + "、".join(duplicates))
        st.caption("变动只影响所选月份。保存后，当月经费、累计预算和余额自动重算；后续月份可复制调整后的名单。")
        st.caption("已勾选报销的月份，报销金额也按更新后的当月人数重新计算。")

    with bulk_tab:
        sources = [month for month in range(1, 13) if month != selected and data["months"][str(month)] is not None]
        if sources:
            earlier = [month for month in sources if month < selected]
            source = st.selectbox("从已有月份复制完整名单", sources,
                                  index=sources.index(max(earlier) if earlier else sources[0]),
                                  format_func=lambda month: f"{month}月 · {len(data['months'][str(month)])}人",
                                  key=f"{widget_key}_copy_source_{selected}")
            if st.button(f"将{source}月名单复制到{selected}月（覆盖该月名单）", key=f"{widget_key}_copy_{selected}"):
                updated = activity.set_rosters(data, [selected], data["months"][str(source)])
                _save(updated, snapshot, state_key)
        with st.form(f"{widget_key}_roster_{selected}"):
            targets = st.multiselect("保存到哪些月份（名单相同可多选）", list(range(1, 13)),
                                     default=[selected], format_func=lambda month: f"{month}月")
            text = st.text_area("教师名单（每行一人，也支持逗号、顿号分隔）", value="\n".join(names or []), height=230)
            confirmed = st.checkbox("确认所选月份的名单完整；空名单表示该月确实为0人", value=names is not None)
            submitted = st.form_submit_button("💾 保存月份名单")
        if submitted:
            if not confirmed:
                st.error("请确认名单完整后保存，避免将缺失名单计为0人。")
            else:
                try:
                    entered_names = activity.parse_names(text)
                    updated = activity.set_rosters(data, targets, entered_names)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    _save(updated, snapshot, state_key)
        st.caption("每个月保留独立名单；费用、累计金额及余额随人数自动更新。")

    with paid_tab:
        eligible = [month for month in range(1, cutoff + 1) if data["months"][str(month)] is not None]
        st.caption("按预算所属月份勾选，可只选1月和3月；每月按整月预算登记，金额自动相加。")
        with st.form(f"{widget_key}_reimbursement"):
            paid = st.multiselect(
                "已报销月份", eligible,
                default=[month for month in data["reimbursed_months"] if month in eligible],
                format_func=lambda month: f"{month}月 · ¥{len(data['months'][str(month)]) * activity.MONTHLY_RATE:,.2f}")
            submitted_paid = st.form_submit_button("💾 保存报销月份（未选择表示暂无报销）")
        if submitted_paid:
            try:
                updated = activity.set_reimbursed_months(data, paid, today)
            except ValueError as exc:
                st.error(str(exc))
            else:
                _save(updated, snapshot, state_key)
        st.caption("本区登记预算月份的报销情况；支出流水仍按实际费用记录，不会重复生成流水。")
        st.dataframe(pd.DataFrame(activity.monthly_rows(data, today)), use_container_width=True, hide_index=True)
