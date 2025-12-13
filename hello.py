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

# 4. 底部文案 (右下角极简风)
# 样式逻辑：
# text-align: right -> 右对齐
# padding-right: 10% -> 距离右边框留出 10% 的空隙，不贴边
# padding-top: 80px -> 距离分割线往下推一点，不要太挤
st.markdown(f"""
<div style="text-align: right; padding-right: 10%; padding-top: 80px; padding-bottom: 40px;">
<span style="font-size: 1.2rem; color: #333; font-weight: 600; letter-spacing: 1px; font-family: {quote_font};">
“ 前方没有胜利，挺住意味一切。”
</span>
</div>
""", unsafe_allow_html=True)
