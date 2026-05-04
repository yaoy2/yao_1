# -*- coding: utf-8 -*-
"""
wechat_app.py
本地 GUI 窗口：
把微信文章链接粘贴到输入框，写“归档竞赛”或“归档课题”，点击开始归档。
"""

import streamlit as st

from wechat_core import TARGET_DIRS, archive_urls, detect_archive_type, extract_urls


st.set_page_config(
    page_title="微信公众号文章归档",
    page_icon="🗂️",
    layout="wide",
)

st.title("🗂️ 微信公众号文章归档到 Obsidian")

st.markdown(
    """
把微信公众号文章链接直接粘贴到下面。可以是一篇，也可以是多篇。  
你只需要在输入里写清楚：**归档竞赛** 或 **归档课题**。
"""
)

example = """归档竞赛
https://mp.weixin.qq.com/s/xxxx
https://mp.weixin.qq.com/s/yyyy"""

col1, col2 = st.columns([2, 1])

with col1:
    user_text = st.text_area(
        "输入区",
        value="",
        placeholder=example,
        height=260,
    )

with col2:
    st.subheader("归档目录")
    st.write("课题：")
    st.code(TARGET_DIRS["course"], language="text")
    st.write("竞赛：")
    st.code(TARGET_DIRS["competition"], language="text")

    fallback_label = st.radio(
        "如果输入里没有写明归档类型，则默认：",
        ["课题", "竞赛"],
        index=0,
        horizontal=True,
    )
    fallback_type = "course" if fallback_label == "课题" else "competition"

    headless = st.checkbox("后台运行浏览器", value=True)
    interval = st.number_input("每篇间隔秒数", min_value=0.0, max_value=30.0, value=2.0, step=1.0)
    timeout = st.number_input("超时秒数", min_value=10, max_value=120, value=30, step=5)

archive_type = detect_archive_type(user_text, fallback=fallback_type)
urls = extract_urls(user_text)

st.divider()

detected_label = "教学课题" if archive_type == "course" else "学生竞赛"
st.write(f"检测到归档类型：**{detected_label}**")
st.write(f"检测到链接数量：**{len(urls)}**")

if urls:
    with st.expander("查看检测到的链接"):
        for u in urls:
            st.code(u, language="text")

start = st.button("开始归档", type="primary", use_container_width=True)

if start:
    if not urls:
        st.error("没有检测到微信公众号文章链接。请粘贴 https://mp.weixin.qq.com/s/... 格式的链接。")
    else:
        st.info(f"开始归档到：{detected_label}")
        log_box = st.empty()
        logs = []

        def report(msg: str):
            logs.append(msg)
            log_box.text("\n".join(logs[-80:]))

        with st.spinner("正在处理，请不要关闭窗口..."):
            results = archive_urls(
                urls=urls,
                archive_type=archive_type,
                headless=headless,
                interval=float(interval),
                timeout=int(timeout),
                progress_callback=report,
            )

        ok_count = sum(1 for r in results if r.get("ok"))
        fail_count = len(results) - ok_count

        if fail_count == 0:
            st.success(f"全部完成：成功 {ok_count} 篇。")
        else:
            st.warning(f"处理完成：成功 {ok_count} 篇，失败 {fail_count} 篇。")

        st.subheader("结果")
        for r in results:
            if r.get("ok"):
                st.success(f"✓ {r.get('title','')} | 图片 {r.get('images_ok',0)} 张 | {r.get('path','')}")
            else:
                st.error(f"✗ {r.get('url','')} | {r.get('message','')}")
