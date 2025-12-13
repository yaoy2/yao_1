import streamlit as st

# 1. 页面配置
st.set_page_config(
    page_title="YaoYao's Space",
    page_icon="🐾",
    layout="wide"
)

# 2. 样式优化 (顶部留白)
st.write("")
st.write("")
st.write("")

# ==============================================================
# 🎨 字体配置
# ==============================================================
sub_font = "'Comic Sans MS', 'Chalkboard SE', 'NoteWorthy', sans-serif"
quote_font = "'Songti SC', 'SimSun', 'Times New Roman', serif"
# ==============================================================

# 3. 核心内容区 (标题)
# 保持顶格写 HTML，防止缩进报错
st.markdown(f"""
<h1 style="text-align: center; font-size: 5rem; margin-bottom: 0; letter-spacing: 5px; font-weight: 900;">
🐾 行政狗
</h1>
<p style="text-align: center; font-size: 1.5rem; color: #b2b2b2; margin-top: 10px; font-family: {sub_font};">
~ Don't worry. Be happy. ~
</p>
""", unsafe_allow_html=True) 

st.divider()

# 4. 底部文案 (固定在屏幕右下角)
# position: fixed -> 强制固定在浏览器窗口
# bottom: 30px; right: 30px -> 距离右下角的距离
# z-index: 999 -> 保证它浮在最上面
st.markdown(f"""
<div style="position: fixed; bottom: 30px; right: 30px; z-index: 999; text-align: right;">
<span style="font-size: 1.2rem; color: #333; font-weight: 600; letter-spacing: 1px; font-family: {quote_font};">
“ 前方没有胜利，挺住意味一切。”
</span>
</div>
""", unsafe_allow_html=True)
