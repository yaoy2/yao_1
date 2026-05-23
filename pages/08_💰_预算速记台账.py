import streamlit as st
import pandas as pd
import sys
import os
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.budget_config import BUDGET_YEAR, BUDGET_CATEGORIES, REIMBURSEMENT_STATUSES, UNITS
from utils import budget_auth, budget_db

init_db = budget_db.init_db
add_record = budget_db.add_record
get_filtered_records = budget_db.get_filtered_records
get_category_summary = budget_db.get_category_summary
update_record = budget_db.update_record
get_all_records = budget_db.get_all_records
get_unit_summary_by_category = budget_db.get_unit_summary_by_category
get_category_unit_pivot = budget_db.get_category_unit_pivot
replace_all_records = getattr(budget_db, "replace_all_records", None)

st.set_page_config(page_title="预算速记台账", page_icon="💰", layout="wide")


def require_budget_auth():
    configured_password = budget_auth.get_budget_password(st.secrets, os.environ)
    if not configured_password:
        st.title("💰 预算速记台账")
        st.warning("预算台账密码还没有配置。请在 Streamlit secrets 中设置 budget_password，或在本机设置 BUDGET_PASSWORD。")
        st.stop()

    if st.session_state.get("budget_authenticated"):
        return

    st.title("💰 预算速记台账")
    st.info("请输入密码后查看和操作预算台账。")
    with st.form("budget_auth_form"):
        input_password = st.text_input("预算台账密码", type="password")
        submitted = st.form_submit_button("进入台账", use_container_width=True)

    if submitted:
        if budget_auth.is_budget_password_valid(input_password, configured_password):
            st.session_state["budget_authenticated"] = True
            st.rerun()
        else:
            st.error("密码不正确，请重新输入。")

    st.stop()


require_budget_auth()
init_db()

st.title(f"💰 {BUDGET_YEAR}年度预算速记台账")

st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.25rem 0.85rem;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"] {
        gap: 0.65rem;
        align-items: center;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlock"] {
        gap: 0;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stSelectbox"] {
        margin-bottom: 0;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        min-height: 2.35rem;
        padding-top: 0;
        padding-bottom: 0;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] details {
        margin-bottom: 0;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] details summary {
        min-height: 2.35rem;
        padding-top: 0.35rem;
        padding-bottom: 0.35rem;
    }
    .budget-record-line {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        line-height: 2.35rem;
    }
    .budget-record-line strong {
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
    table_rows = []
    for rec in records:
        table_rows.append({
            "ID": rec["id"],
            "日期": pd.to_datetime(rec["record_date"]).date(),
            "费用类别": rec["category"],
            "使用单位": rec.get("unit", ""),
            "金额": float(rec["amount"]),
            "支出明细": rec.get("description", ""),
            "报销状态": rec["reimbursement_status"],
        })

    df_records = pd.DataFrame(table_rows)
    edited_records = st.data_editor(
        df_records,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        height=min(560, 38 * (len(df_records) + 1) + 4),
        column_config={
            "ID": None,
            "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD", required=True, width="small"),
            "费用类别": st.column_config.SelectboxColumn("费用类别", options=list(BUDGET_CATEGORIES.keys()), required=True, width="medium"),
            "使用单位": st.column_config.SelectboxColumn("使用单位", options=UNITS, width="medium"),
            "金额": st.column_config.NumberColumn("金额", min_value=0.01, step=100.0, format="%.2f", width="small"),
            "支出明细": st.column_config.TextColumn("支出明细", width="large"),
            "报销状态": st.column_config.SelectboxColumn("报销状态", options=REIMBURSEMENT_STATUSES, required=True, width="small"),
        },
        key="budget_records_editor",
    )

    if st.button("💾 保存表格修改", type="primary"):
        original_records = {rec["id"]: rec for rec in records}
        changed_count = 0
        try:
            for _, row in edited_records.iterrows():
                rid = int(row["ID"])
                original = original_records[rid]
                record_date = pd.to_datetime(row["日期"]).strftime("%Y-%m-%d")
                category = str(row["费用类别"]).strip()
                unit = "" if pd.isna(row["使用单位"]) else str(row["使用单位"]).strip()
                description = "" if pd.isna(row["支出明细"]) else str(row["支出明细"]).strip()
                amount = float(row["金额"])
                status = str(row["报销状态"]).strip()

                if category not in BUDGET_CATEGORIES:
                    raise ValueError(f"ID {rid} 的费用类别无效：{category}")
                if status not in REIMBURSEMENT_STATUSES:
                    raise ValueError(f"ID {rid} 的报销状态无效：{status}")
                if amount <= 0:
                    raise ValueError(f"ID {rid} 的金额必须大于 0")

                if (
                    record_date != original["record_date"]
                    or category != original["category"]
                    or unit != original.get("unit", "")
                    or description != original.get("description", "")
                    or amount != float(original["amount"])
                    or status != original["reimbursement_status"]
                ):
                    update_record(
                        rid,
                        record_date=record_date,
                        category=category,
                        unit=unit,
                        description=description,
                        amount=amount,
                        status=status,
                    )
                    changed_count += 1
        except Exception as exc:
            st.error(f"保存失败：{exc}")
        else:
            st.success(f"已保存 {changed_count} 条修改。")
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


def _clean_excel_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def _clean_excel_date(value):
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    parsed = pd.to_datetime(value, errors="coerce")
    if not pd.isna(parsed):
        return parsed.strftime("%Y-%m-%d")
    return str(value).strip()


def _records_from_excel(uploaded_file):
    df = pd.read_excel(uploaded_file)
    if df.empty:
        raise ValueError("Excel 里没有可恢复的流水记录。")

    reverse_columns = {v: k for k, v in COL_RENAME.items()}
    df = df.rename(columns=reverse_columns)
    required = ["record_date", "category", "amount"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        readable = "、".join(COL_RENAME.get(col, col) for col in missing)
        raise ValueError(f"Excel 缺少必要列：{readable}")

    records = []
    for row_index, row in df.iterrows():
        line_no = row_index + 2
        record_date = _clean_excel_date(row.get("record_date"))
        category = _clean_excel_text(row.get("category"))
        unit = _clean_excel_text(row.get("unit"))
        description = _clean_excel_text(row.get("description"))
        status = _clean_excel_text(row.get("reimbursement_status")) or "未报销"
        amount = pd.to_numeric(row.get("amount"), errors="coerce")

        if not record_date:
            raise ValueError(f"第 {line_no} 行缺少日期。")
        if category not in BUDGET_CATEGORIES:
            raise ValueError(f"第 {line_no} 行费用类别不在配置中：{category}")
        if pd.isna(amount) or amount <= 0:
            raise ValueError(f"第 {line_no} 行金额无效：{row.get('amount')}")
        if status not in REIMBURSEMENT_STATUSES:
            raise ValueError(f"第 {line_no} 行报销状态无效：{status}")

        records.append({
            "record_date": record_date,
            "category": category,
            "unit": unit,
            "description": description,
            "amount": float(amount),
            "reimbursement_status": status,
            "created_at": _clean_excel_text(row.get("created_at")),
            "updated_at": _clean_excel_text(row.get("updated_at")),
        })
    return records


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

st.divider()

# ── Excel 备份恢复 ──
with st.expander("♻️ 从 Excel 备份恢复"):
    uploaded_backup = st.file_uploader(
        "上传之前导出的预算流水 Excel",
        type=["xlsx"],
        accept_multiple_files=False,
    )
    confirm_restore = st.checkbox("我确认用这个 Excel 覆盖当前台账")

    if st.button("覆盖恢复台账", type="primary", disabled=not uploaded_backup or not confirm_restore):
        try:
            if replace_all_records is None:
                raise RuntimeError("当前线上环境还没有加载到恢复函数，请在 Streamlit Cloud 重新部署后再试。")
            restore_records = _records_from_excel(uploaded_backup)
            replace_all_records(restore_records)
        except Exception as exc:
            st.error(f"恢复失败：{exc}")
        else:
            st.success(f"已从 Excel 恢复 {len(restore_records)} 条流水。")
            st.rerun()
