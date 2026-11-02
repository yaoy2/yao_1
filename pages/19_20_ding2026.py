"""M20: shared rules and entry instructions for the local distribution tool."""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.ui_theme import render_home_link
from integrations.file_distribution.rules import (
    ENTRY_FILENAME,
    RELEASE_DATE,
    RULE_ROWS,
    USER_GUIDE,
    VERSION,
)

st.set_page_config(page_title="M20 · 文件分发", page_icon="📂", layout="wide")
render_home_link()
st.title("M20 · 文件分发")
st.caption("月报、系部及学院党政联席会纪要、考勤和发票，共用一套规则，预览后分发。")
st.markdown(
    f"在 **Ding2026** 文件夹内双击 **{ENTRY_FILENAME}**，分别勾选 **会议纪要**、**考勤记录**、**月报**、**发票**。"
    "默认只选纪要和考勤；点击预览，核对文件去向后点击分发，界面显示实时过程与结果。未选规则不处理。"
)
st.table(RULE_ROWS)
st.info("本页展示与本地程序共用的规则；文件预览和分发在双击程序中完成。")

with st.expander("使用与 Drive 同步说明"):
    st.markdown(USER_GUIDE)
    st.write(
        "Drive 同步完成后，可以在办公电脑 L 的 Ding2026 文件夹中双击同一入口。"
        "程序按所在位置定位文件夹，无需使用家庭电脑 D 的盘符。"
        "分发时只在一台电脑操作，完成后等待 Drive 同步。"
    )
    st.caption("首次在 L 使用时，先核对根目录、预览去向与分发结果。")

st.link_button(
    "使用与维护说明",
    "https://github.com/yaoy2/yao_1/blob/main/integrations/file_distribution/README.md",
)
st.caption(f"M20 · 规则与程序版本 {VERSION} · 更新日期 {RELEASE_DATE}")
