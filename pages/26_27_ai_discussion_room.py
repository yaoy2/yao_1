"""M27：众声室，本机 Codex / Claude / Grok 群聊入口。"""

import streamlit as st

from utils.ui_theme import render_home_link


st.set_page_config(page_title="M27 · 众声室", page_icon="💬", layout="wide")
render_home_link()
st.markdown("### 💬 众声室 · M27")
st.caption("个人 · AI 群聊｜您提出问题，Codex、Claude、Grok 阅读彼此的发言并继续讨论。")

st.link_button("进入群聊讨论室 ↗", "http://127.0.0.1:8766/", type="primary")
st.caption("打开当前电脑上的讨论室。请先完成下方的本机启动；成员是否可用，以讨论室左侧的连接状态为准。")

with st.container(border=True):
    st.markdown("**开始使用**")
    st.markdown(
        "1. 在本机仓库中双击下面的启动文件，打开讨论室。\n"
        "2. 输入议题，选择所有可用成员或点名一位，发送后依次回复。\n"
        "3. 用“继续一轮”接着讨论，或请一位成员整理共识、分歧和下一步。"
    )
    st.code(r"zhongshengshi\local-room\start-room.cmd", language="text")

st.markdown("**支持：**共享本场前文 · 点名追问 · 1–3 轮讨论 · 停止生成 · 恢复记录 · 导出 Markdown")
st.info("讨论室在本机运行，复用已安装工具的登录。在线工具箱中的这个入口也指向您当前的电脑；不会使用网站服务器上的账号。")

with st.expander("成员登录与记录说明"):
    st.markdown(
        "Codex、Claude Code、Grok 命令行工具需要分别安装并完成登录。"
        "尚未连接的成员会跳过，其他成员仍可参与。完成登录后，回到讨论室点击“刷新”。\n\n"
        "**Claude：**可在本机双击 `zhongshengshi/local-room/login-claude-official.cmd`，"
        "亲自完成官方登录。该入口保留原来的第三方接口配置。\n\n"
        "**Grok：**可在本机双击 `zhongshengshi/local-room/login-grok.cmd` 完成登录。\n\n"
        "界面记录保存在当前浏览器，所选成员会收到本场已完成的发言；"
        "命令行工具也可能按各自设置保存会话。需要长期保留的讨论请导出，清空前先保存。"
    )
