import streamlit as st

st.set_page_config(page_title="YaoYao's Space", page_icon="🐾", layout="wide")

st.write("")
st.write("")
st.write("")

sub_font = "'Comic Sans MS', 'Chalkboard SE', 'NoteWorthy', sans-serif"
quote_font = "'KaiTi', 'STKaiti', 'BiauKai', cursive"

# 核心内容区
st.markdown(f"""
    <h1 style='text-align: center; font-size: 5rem; margin-bottom: 0; letter-spacing: 5px; font-weight: 900;'>
        🐾 行政狗 v2
    </h1>
    <p style='text-align: center; font-size: 1.5rem; color: #b2b2b2; margin-top: 10px; font-family: {sub_font};'>
        ~ Don't worry. Be happy. ~
    </p>
""", unsafe_allow_html=True) 

st.divider()

# 底部文案 (重点修复区域)
st.markdown(f"""
    <div style='text-align: center; padding: 40px;'>
        <p style='font-size: 1rem; color: #999; margin-bottom: 30px;'>
            👋 欢迎回来，请在左侧选择工具
        </p>
        <div style='display: inline-block; padding: 20px 40px; background-color: #fcfcfc; border-radius: 4px; border: 1px dashed #ccc;'>
            <span style='font-size: 1.5rem; color: #555; line-height: 1.6; font-family: {quote_font};'>
                “ 前方没有胜利，挺住意味一切。”
            </span>
        </div>
    </div>
""", unsafe_allow_html=True)