"""LLM Budget Tracker - 各家 LLM API 余额统一管理"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import github_backup_sync, llm_budget_accounts
from utils.llm_budget_providers import PROVIDERS, MANUAL_PROVIDERS
from utils.ui_theme import render_home_link

# ── 路径 ──
ROOT = Path(__file__).parent.parent
RECORDS_PATH = ROOT / "data" / "llm_budget_records.json"
ACCOUNTS_REPO_PATH = "data/llm_budget_accounts.json"


# ── 数据读写 ──
def get_api_key(provider_key: str) -> str:
    """从 st.secrets 读取 API Key"""
    secret_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_API_KEY",
    }
    secret_name = secret_map.get(provider_key, "")
    if secret_name:
        return st.secrets.get(secret_name, "")
    return ""


def load_records() -> list:
    if RECORDS_PATH.exists():
        with open(RECORDS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_record(record: dict):
    records = load_records()
    records.append(record)
    with open(RECORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def sync_llm_budget_accounts_to_github():
    return github_backup_sync.sync_file_to_github(
        llm_budget_accounts.ACCOUNTS_PATH,
        ACCOUNTS_REPO_PATH,
        "data: sync llm budget login accounts",
        st.secrets,
        os.environ,
    )


def render_account_editor(key: str) -> None:
    current_account = llm_budget_accounts.get_login_account(key)
    current_expiration = llm_budget_accounts.get_expiration_date(key)
    account_col, save_col = st.columns([3, 1], vertical_alignment="bottom")
    with account_col:
        account_value = st.text_input(
            "登录账号",
            value=current_account,
            placeholder="邮箱或手机号",
            key=f"account_{key}",
        )
    with save_col:
        save_clicked = st.button("保存", key=f"save_account_{key}", use_container_width=True)
    expiration_value = st.text_input(
        "expiration date: yy_mm_dd",
        value=current_expiration,
        placeholder="26_09_30",
        key=f"expiration_{key}",
    )
    if save_clicked:
        llm_budget_accounts.save_provider_profile(
            key,
            account=account_value,
            expiration_date=expiration_value,
        )
        sync_result = sync_llm_budget_accounts_to_github()
        if sync_result.get("ok") or sync_result.get("skipped"):
            st.success("账号已保存")
        st.rerun()


# ── 页面配置 ──
st.set_page_config(page_title="LLM 余额管理", page_icon="💰", layout="wide")

render_home_link()

st.title("💰 LLM 余额管理")
st.caption("各家 LLM API / Token Plan 余额统一管理")

# ── 侧栏 ──
with st.sidebar:
    st.header("⚙️ 配置")
    alert_threshold = st.number_input(
        "低余额预警阈值（元）",
        min_value=0.0,
        value=10.0,
        step=1.0,
    )
    st.divider()
    st.caption("API Key 在 Streamlit Cloud 的 Secrets 中配置：")
    st.code(
        'DEEPSEEK_API_KEY = "sk-xxx"\nKIMI_API_KEY = "sk-xxx"\nGITHUB_BACKUP_TOKEN = "ghp_xxx"',
        language="toml",
    )
    st.caption("登录账号在页面中填写并保存；有 GITHUB_BACKUP_TOKEN 时会同步到 GitHub。")

# ── 自动查询区 ──
st.header("📊 实时余额")

cols = st.columns(len(PROVIDERS) + len(MANUAL_PROVIDERS))

# 自动查询的厂商
for i, (key, provider) in enumerate(PROVIDERS.items()):
    with cols[i]:
        st.subheader(provider.display_name)
        render_account_editor(key)
        api_key = get_api_key(key)

        if not api_key:
            st.warning("未配置 API Key")
            st.caption("在 Manage app → Secrets 中添加")
            continue

        result = provider.query(api_key)

        if result.is_ok:
            if result.available < alert_threshold:
                st.error("⚠️ 低余额")
            else:
                st.success("余额正常")

            st.metric(label="可用余额", value=f"¥{result.available:.2f}")
            if result.granted is not None:
                st.caption(f"赠金: ¥{result.granted:.2f}  |  充值: ¥{result.topped_up:.2f}")

            save_record({
                "time": datetime.now().isoformat(),
                "provider": key,
                "available": result.available,
                "currency": result.currency,
                "source": "auto",
            })
        else:
            st.error(f"查询失败: {result.error}")

        st.link_button(f"🔗 {provider.display_name} 控制台", provider.console_url)

# 手动录入的厂商
for j, (key, info) in enumerate(MANUAL_PROVIDERS.items()):
    with cols[len(PROVIDERS) + j]:
        st.subheader(info["name"])
        render_account_editor(key)
        st.warning("手动录入")

        records = load_records()
        last_manual = [r for r in records if r.get("provider") == key and r.get("source") == "manual"]
        last_value = last_manual[-1]["available"] if last_manual else 0.0

        new_value = st.number_input(
            f"{info['name']} 余额（元）",
            min_value=0.0,
            value=float(last_value),
            step=1.0,
            key=f"manual_{key}",
        )

        if st.button("💾 保存", key=f"save_{key}"):
            save_record({
                "time": datetime.now().isoformat(),
                "provider": key,
                "available": new_value,
                "currency": "CNY",
                "source": "manual",
            })
            st.success("已保存")
            st.rerun()

        if 0 < new_value < alert_threshold:
            st.error("⚠️ 低余额")

        st.link_button(f"🔗 {info['name']} 控制台", info["console_url"])

# ── 历史趋势 ──
st.divider()
st.header("📈 历史趋势")

records = load_records()
if records:
    import pandas as pd

    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"])

    providers_in_data = df["provider"].unique()
    for prov in providers_in_data:
        prov_df = df[df["provider"] == prov].copy().sort_values("time")

        if prov in PROVIDERS:
            display = PROVIDERS[prov].display_name
        elif prov in MANUAL_PROVIDERS:
            display = MANUAL_PROVIDERS[prov]["name"]
        else:
            display = prov

        st.subheader(display)
        chart_data = prov_df.set_index("time")[["available"]]
        chart_data.columns = ["余额（元）"]
        st.line_chart(chart_data)

    st.subheader("📋 全部记录")
    display_df = df.copy()
    display_df["provider"] = display_df["provider"].map(
        lambda p: PROVIDERS[p].display_name if p in PROVIDERS
        else MANUAL_PROVIDERS.get(p, {}).get("name", p)
    )
    display_df = display_df.rename(columns={
        "time": "时间", "provider": "厂商",
        "available": "余额（元）", "source": "来源",
    })
    st.dataframe(
        display_df[["时间", "厂商", "余额（元）", "来源"]].iloc[::-1],
        use_container_width=True, hide_index=True,
    )
else:
    st.info("暂无记录。查询或手动录入后会自动保存。")
