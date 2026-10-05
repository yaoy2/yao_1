"""M27：众声室，本机 GPT / Grok / Gemini 独立回答对照入口。"""

import streamlit as st

from utils.ui_theme import render_home_link


st.set_page_config(page_title="M27 · 众声室", page_icon="💬", layout="wide")
render_home_link()
st.markdown("### 💬 众声室 · M27")
st.caption("同题对照｜同一个问题，同时查看 GPT、Grok、Gemini 的独立回答；每栏只延续自己的前文。")

st.link_button("进入同题对照 ↗", "http://127.0.0.1:8766/", type="primary")
st.caption("打开当前电脑上的众声室。请先完成下方的本机启动；成员是否可用，以各栏的实际状态为准。")

with st.container(border=True):
    st.markdown("**开始使用**")
    st.markdown(
        "1. 在本机仓库中双击下面的启动文件，打开众声室。\n"
        "2. 勾选可用成员，在共同输入框写下问题，一次发送，同时查看三栏回答。\n"
        "3. 继续输入即可分别追问；新建会话会保留上一场，可从会话列表随时恢复。"
    )
    st.code(r"zhongshengshi\local-room\start-room.cmd", language="text")

st.markdown("**支持：**三栏独立滚动 · 并发回答 · Markdown 阅读 · 单栏重试与重新生成 · 取消全部 · 会话恢复 · 复制与导出")
st.info("众声室在本机运行，复用已安装工具的登录。在线工具箱中的入口也指向您当前的电脑；不会使用网站服务器上的账号。")

with st.expander("成员登录与记录说明"):
    st.markdown(
        "GPT、Grok、Gemini 分别通过本机 Codex、Grok、Google 官方 Antigravity CLI 接入，相关工具需要分别安装并完成登录。"
        "默认勾选可用成员；暂不可用的成员会跳过。完成登录后，回到页面点击“刷新连接”。\n\n"
        "**GPT：**沿用本机 Codex 的登录账号；实际模型由本机 Codex 配置决定。\n\n"
        "**Grok：**可在本机双击 `zhongshengshi/local-room/login-grok.cmd` 完成登录。\n\n"
        "**Gemini（通过 Google 官方 Antigravity CLI）：**可在本机双击 `zhongshengshi/local-room/login-gemini.cmd`，"
        "亲自完成 Antigravity CLI 的 Google 账号登录。本栏指定使用 Gemini 模型；"
        "账号权限、订阅权益和额度以该账号的实际可用情况及调用结果为准。\n\n"
        "旧版 Gemini CLI 的个人、Google AI Pro / Ultra 登录方式已于 2026-06-18 退役，"
        "详见 [Google 官方迁移说明](https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals)。\n\n"
        "重新生成只请求当前一栏，使用该问题之前的本栏历史。新回答成功后，上一版仍可查看和导出，"
        "后续对话只使用新版；重新生成失败时保留原有完整回答。\n\n"
        "本机会话按第一问和时间列出，新建时自动保留上一场。旧版群聊记录保持原样，"
        "页面提供“导出旧讨论”；旧记录不会传入新的独立对话。失败或取消产生的片段保留供查看和导出，不进入后续上下文。\n\n"
        "界面记录只保存在当前浏览器；命令行工具也可能按各自设置保存会话。"
        "“导出三栏”保存当前会话；“备份会话”保存全部本机会话及草稿。"
        "“恢复备份”支持同题对照 v1 / v2 JSON 备份，先校验并确认，再加入为新会话；原有会话保持不变，"
        "同一个备份文件不会重复导入。未完成回答只恢复供查看，不进入后续上下文。"
        "如遇保存失败或其他页面更新，页面会暂停覆盖并提示先导出，避免静默丢失记录。"
    )
