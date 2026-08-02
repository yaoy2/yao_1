"""M19：A股研究与公开信息搜索中心。"""

from __future__ import annotations

import os
import sys

import streamlit as st


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stock.portal import render_stock_portal
from utils import budget_auth
from utils.ui_theme import render_home_link


st.set_page_config(page_title="股票研究中心", page_icon="📈", layout="wide")


def require_stock_portal_auth() -> None:
    """Protect M19 with the same password used by the other locked tools."""
    configured_password = budget_auth.get_budget_password(st.secrets, os.environ)
    if not configured_password:
        st.title("📈 股票研究中心")
        st.warning(
            "股票研究中心密码还没有配置。请在 Streamlit secrets 中设置 "
            "budget_password，或在本机设置 BUDGET_PASSWORD。"
        )
        st.stop()

    if st.session_state.get("stock_portal_authenticated"):
        return

    st.title("📈 股票研究中心")
    st.info("请输入与其他上锁页面相同的访问密码。")
    with st.form("stock_portal_auth_form"):
        input_password = st.text_input("访问密码", type="password")
        submitted = st.form_submit_button("进入股票研究中心", use_container_width=True)

    if submitted:
        if budget_auth.is_budget_password_valid(input_password, configured_password):
            st.session_state["stock_portal_authenticated"] = True
            st.rerun()
        else:
            st.error("密码不正确，请重新输入。")

    st.stop()


require_stock_portal_auth()
render_home_link()
render_stock_portal()
