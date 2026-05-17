# -*- coding: utf-8 -*-
"""
wechat_app.py
本地 GUI 窗口：四路线归档入口。
"""

import streamlit as st

from wechat_core import (
    TARGET_DIRS,
    archive_local_files,
    archive_urls,
    classify_archive_request,
)


st.set_page_config(
    page_title="微信公众号文章归档",
    page_icon="🗂️",
    layout="wide",
)

st.title("🗂️ 四路线归档窗口")
st.caption("专用端口建议：8502。8501 留给主工具箱或单页预览，避免串台。")

st.markdown(
    """
把公众号链接或本地文件路径粘贴到输入框，并写清楚归档目标：
`归档raw`、`归档学院`、`归档课题`、`归档竞赛`。
"""
)

route_data = [
    {"路线": "A", "触发词": "归档raw", "输入": "公众号链接", "Streamlit 执行": "抓取并保存 raw"},
    {"路线": "B", "触发词": "归档课题 / 归档竞赛", "输入": "公众号链接", "Streamlit 执行": "抓取并保存课题/竞赛目录"},
    {"路线": "C", "触发词": "归档学院", "输入": "本地文件", "Streamlit 执行": "仅识别提示，IMA 上传交给 WorkBuddy"},
    {"路线": "D", "触发词": "归档课题 / 归档竞赛", "输入": "本地文件", "Streamlit 执行": "复制到课题/竞赛目录"},
]
st.dataframe(route_data, use_container_width=True, hide_index=True)

example = """归档课题
https://mp.weixin.qq.com/s/xxxx

或：
归档竞赛 "E:\\材料\\比赛通知.pdf"

或：
归档学院 "E:\\材料\\学院通知.docx" """

col_input, col_settings = st.columns([2, 1])

with col_input:
    user_text = st.text_area(
        "输入区",
        value="",
        placeholder=example,
        height=260,
    )

with col_settings:
    st.subheader("默认归档目标")
    fallback_label = st.radio(
        "没有写明目标时默认：",
        ["课题", "竞赛"],
        index=0,
        horizontal=True,
    )
    fallback_type = "course" if fallback_label == "课题" else "competition"

    st.subheader("公众号抓取设置")
    headless = st.checkbox("后台运行浏览器", value=True)
    interval = st.number_input("每篇间隔秒数", min_value=0.0, max_value=30.0, value=2.0, step=1.0)
    timeout = st.number_input("超时秒数", min_value=10, max_value=120, value=30, step=5)

route = classify_archive_request(user_text, fallback=fallback_type)

st.divider()
summary_col, target_col = st.columns([1, 1])

with summary_col:
    st.subheader("识别结果")
    st.write(f"路线：**{route['title']}**")
    st.write(f"归档目标：**{route['archive_label']}**")
    st.write(f"输入类型：**{route['input_kind']}**")
    st.write(f"公众号链接：**{len(route['urls'])}** 个")
    st.write(f"本地文件：**{len(route['local_paths'])}** 个")
    st.caption(route["description"])

with target_col:
    st.subheader("本地目录")
    st.write("raw：")
    st.code(TARGET_DIRS["raw"], language="text")
    st.write("课题：")
    st.code(TARGET_DIRS["course"], language="text")
    st.write("竞赛：")
    st.code(TARGET_DIRS["competition"], language="text")

if route["urls"]:
    with st.expander("查看检测到的公众号链接"):
        for item in route["urls"]:
            st.code(item, language="text")

if route["local_paths"]:
    with st.expander("查看检测到的本地文件"):
        for item in route["local_paths"]:
            st.code(item, language="text")

st.info("涉及 IMA 知识库上传的部分，需要 WorkBuddy 执行；本窗口负责本地抓取、保存和文件复制。")

start = st.button("开始归档", type="primary", use_container_width=True)

if start:
    if not route["streamlit_supported"]:
        st.warning(route["description"])
    elif route["input_kind"] == "link":
        if not route["urls"]:
            st.error("没有检测到微信公众号文章链接。请粘贴 https://mp.weixin.qq.com/s/... 格式的链接。")
        else:
            st.info(f"开始执行：{route['title']}")
            log_box = st.empty()
            logs = []

            def report(msg: str):
                logs.append(msg)
                log_box.text("\n".join(logs[-80:]))

            with st.spinner("正在抓取，请不要关闭窗口..."):
                results = archive_urls(
                    urls=route["urls"],
                    archive_type=route["archive_type"],
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

    elif route["input_kind"] == "file":
        if not route["local_paths"]:
            st.error("没有检测到本地文件路径。请粘贴类似 E:\\材料\\通知.pdf 的完整路径。")
        else:
            st.info(f"开始执行：{route['title']}")
            log_box = st.empty()
            logs = []

            def report(msg: str):
                logs.append(msg)
                log_box.text("\n".join(logs[-80:]))

            results = archive_local_files(
                route["local_paths"],
                archive_type=route["archive_type"],
                progress_callback=report,
            )

            ok_count = sum(1 for r in results if r.get("ok"))
            fail_count = len(results) - ok_count
            if fail_count == 0:
                st.success(f"全部完成：成功 {ok_count} 个文件。")
            else:
                st.warning(f"处理完成：成功 {ok_count} 个，失败 {fail_count} 个。")

            st.subheader("结果")
            for r in results:
                if r.get("ok"):
                    st.success(f"✓ {r.get('path','')}")
                else:
                    st.error(f"✗ {r.get('source', r.get('path',''))} | {r.get('message','')}")
    else:
        st.error("还没有识别到可执行路线。请提供公众号链接或本地文件路径。")
