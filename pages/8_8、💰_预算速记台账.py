import streamlit as st
import pandas as pd
import sys
import os
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.budget_config import BUDGET_YEAR, BUDGET_CATEGORIES, REIMBURSEMENT_STATUSES, UNITS
from utils.budget_db import init_db, add_record, get_filtered_records, get_category_summary, set_status, update_record, get_all_records, get_unit_summary_by_category, get_category_unit_pivot

st.set_page_config(page_title="预算速记台账", page_icon="💰", layout="wide")
init_db()

st.title(f"💰 {BUDGET_YEAR}年度预算速记台账")

# ── 顶部速记区 ──
st.subheader("✍️ 快速录入")
with st.form("quick_add", clear_on_submit=True):
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        category = st.selectbox("费用类别", list(BUDGET_CATEGORIES.keys()))
    with col2:
        unit = st.selectbox("使用单位", UNITS)
    with col3:
        status = st.selectbox("报销状态", REIMBURSEMENT_STATUSES[:2], index=0)
    with col4:
        record_date = st.date_input("发生日期")
    description = st.text_input("支出明细")
    col5, col6 = st.columns([1, 3])
    with col5:
        amount = st.number_input("金额（元）", min_value=0.0, step=100.0, format="%.2f")
    with col6:
        st.write("")
        st.write("")
        submitted = st.form_submit_button("💾 保存记录", use_container_width=True)
    if submitted:
        if amount <= 0:
            st.error("金额必须大于 0")
        else:
            add_record(str(record_date), category, unit, description, amount, status)
            st.success(f"已保存：{category} · {unit} · {amount} 元")
            st.rerun()

st.divider()

# ── 分类预算看板 ──
st.subheader("📋 分类预算看板")
cat_summary = get_category_summary()
cat_rows = []
for cat, budget in BUDGET_CATEGORIES.items():
    info = cat_summary.get(cat, {"reimbursed": 0, "unreimbursed": 0})
    reimbursed = info["reimbursed"]
    unreimbursed = info["unreimbursed"]
    used = reimbursed + unreimbursed
    cat_remaining = budget - used
    pct = used / budget if budget > 0 else 0
    cat_rows.append({
        "费用类别": cat,
        "年度预算": budget,
        "已报销": reimbursed,
        "未报销": unreimbursed,
        "合计占用": used,
        "剩余额度": cat_remaining,
        "使用率": f"{pct:.1%}",
    })
df_cat = pd.DataFrame(cat_rows)
st.dataframe(df_cat, use_container_width=True, hide_index=True)

st.divider()

# ── 分类别单位支出看板 ──
st.subheader("🏢 分类别单位支出看板")

# 一、单类别单位支出明细
pick_cat = st.selectbox("选择费用类别", list(BUDGET_CATEGORIES.keys()), index=list(BUDGET_CATEGORIES.keys()).index("学生实践费") if "学生实践费" in BUDGET_CATEGORIES else 0)
unit_data = get_unit_summary_by_category(pick_cat)
cat_budget = BUDGET_CATEGORIES.get(pick_cat, 0)

if unit_data:
    cat_total_used = sum(d["reimbursed"] + d["unreimbursed"] for d in unit_data)
    unit_rows = []
    for d in unit_data:
        used = d["reimbursed"] + d["unreimbursed"]
        pct = used / cat_total_used if cat_total_used > 0 else 0
        unit_rows.append({
            "使用单位": d["unit"] or "(未填写)",
            "已报销金额": d["reimbursed"],
            "未报销金额": d["unreimbursed"],
            "合计占用金额": used,
            "占该类别支出比例": f"{pct:.1%}",
        })
    st.dataframe(pd.DataFrame(unit_rows), use_container_width=True, hide_index=True)
else:
    st.info(f"「{pick_cat}」暂无支出记录。")

# 二、类别 × 单位交叉透视表
with st.expander("展开查看：类别 × 单位交叉表"):
    pivot_data = get_category_unit_pivot()
    pivot_rows = []
    for cat in BUDGET_CATEGORIES:
        row = {"费用类别": cat}
        row_total = 0
        for u in UNITS:
            val = pivot_data.get((cat, u), 0)
            row[u] = val
            row_total += val
        row["类别合计"] = row_total
        pivot_rows.append(row)
    # 单位合计行
    total_row = {"费用类别": "合计"}
    grand = 0
    for u in UNITS:
        col_total = sum(r.get(u, 0) for r in pivot_rows)
        total_row[u] = col_total
        grand += col_total
    total_row["类别合计"] = grand
    pivot_rows.append(total_row)
    df_pivot = pd.DataFrame(pivot_rows)
    st.dataframe(df_pivot, use_container_width=True, hide_index=True)

st.divider()

# ── 流水明细 ──
st.subheader("📝 流水明细")
fc1, fc2, fc3, fc4 = st.columns(4)
with fc1:
    filter_month = st.text_input("月份筛选（如 2026-05）", placeholder="留空=全部")
with fc2:
    filter_cat = st.selectbox("费用类别筛选", ["全部"] + list(BUDGET_CATEGORIES.keys()))
with fc3:
    filter_status = st.selectbox("报销状态筛选", ["全部"] + REIMBURSEMENT_STATUSES)
with fc4:
    filter_keyword = st.text_input("关键词搜索", placeholder="搜索支出明细")

records = get_filtered_records(
    month=filter_month if filter_month else None,
    category=None if filter_cat == "全部" else filter_cat,
    status=None if filter_status == "全部" else filter_status,
    keyword=filter_keyword if filter_keyword else None,
)

if records:
    for rec in records:
        rid = rec["id"]
        status = rec["reimbursement_status"]
        status_icon = {"未报销": "🟡", "已报销": "🟢", "作废": "⚫"}.get(status, "")
        with st.container(border=True):
            rc1, rc2, rc3 = st.columns([4, 2, 2])
            with rc1:
                st.markdown(f"**{rec['record_date']}** · {rec['category']} · {rec.get('unit', '')} · {rec['amount']:,.0f} 元")
                if rec["description"]:
                    st.caption(rec["description"])
            with rc2:
                st.markdown(f"{status_icon} **{status}**")
                new_status = st.selectbox(
                    "变更状态",
                    REIMBURSEMENT_STATUSES,
                    index=REIMBURSEMENT_STATUSES.index(status),
                    key=f"status_{rid}",
                    label_visibility="collapsed",
                )
                if new_status != status:
                    set_status(rid, new_status)
                    st.rerun()
            with rc3:
                with st.expander("✏️ 编辑"):
                    with st.form(f"edit_{rid}", border=False):
                        e_date = st.date_input("日期", value=pd.to_datetime(rec["record_date"]))
                        e_cat = st.selectbox("类别", list(BUDGET_CATEGORIES.keys()), index=list(BUDGET_CATEGORIES.keys()).index(rec["category"]) if rec["category"] in BUDGET_CATEGORIES else 0)
                        cur_unit = rec.get("unit", "")
                        e_unit = st.selectbox("使用单位", UNITS, index=UNITS.index(cur_unit) if cur_unit in UNITS else 0)
                        e_desc = st.text_input("支出明细", value=rec["description"])
                        e_amt = st.number_input("金额", value=rec["amount"], min_value=0.0, step=100.0)
                        if st.form_submit_button("保存"):
                            update_record(rid, record_date=str(e_date), category=e_cat, unit=e_unit, description=e_desc, amount=e_amt)
                            st.rerun()
else:
    st.info("暂无记录，请在上方录入第一笔费用。")

st.divider()


def _to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="预算流水")
    return output.getvalue()


COL_RENAME = {
    "id": "ID", "record_date": "日期", "category": "类别", "unit": "使用单位",
    "description": "支出明细", "amount": "金额",
    "reimbursement_status": "报销状态", "created_at": "创建时间", "updated_at": "更新时间",
}


# ── 导出功能 ──
st.subheader("📥 导出 Excel")
ex_col1, ex_col2 = st.columns(2)

all_records = get_all_records()

with ex_col1:
    if all_records:
        df_all = pd.DataFrame(all_records).rename(columns=COL_RENAME)
        st.download_button(
            "📥 导出全部流水",
            _to_excel_bytes(df_all),
            file_name=f"预算流水_全部_{BUDGET_YEAR}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.button("导出全部流水", disabled=True)

with ex_col2:
    if records:
        df_filt = pd.DataFrame(records).rename(columns=COL_RENAME)
        st.download_button(
            "📥 导出当前筛选结果",
            _to_excel_bytes(df_filt),
            file_name=f"预算流水_筛选_{BUDGET_YEAR}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.button("导出当前筛选结果", disabled=True)
