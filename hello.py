import streamlit as st

# 1. 页面配置
st.set_page_config(
    page_title="YaoYao's Space",
    page_icon="🐾",
    layout="wide"
)

# ==============================================================
# 📏 CSS 暴力修正区 (对齐左侧 hello)
# ==============================================================
# .block-container 是 Streamlit 的主内容容器
# 我们把它的顶部内边距 (padding-top) 强制设为 1.5rem (默认是 6rem)
# 这样标题就会大幅上移，跟左侧菜单对齐
st.markdown("""
    <style>
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 0rem !important;
        }
    </style>
""", unsafe_allow_html=True)

# ==============================================================
# 🎨 字体配置
# ==============================================================
sub_font = "'Comic Sans MS', 'Chalkboard SE', 'NoteWorthy', sans-serif"
quote_font = "'Songti SC', 'SimSun', 'Times New Roman', serif"
# ==============================================================

# 3. 核心内容区 (标题)
# 保持顶格写 HTML
# margin-top: 0 保证标题自己不往下掉
st.markdown(f"""
<h1 style="text-align: center; font-size: 5rem; margin-top: 0; margin-bottom: 0; letter-spacing: 5px; font-weight: 900;">
🐾 行政狗
</h1>
<p style="text-align: center; font-size: 1.5rem; color: #b2b2b2; margin-top: 10px; font-family: {sub_font};">
~ Don't worry. Be happy. ~
</p>
""", unsafe_allow_html=True) 

st.divider()

# 4. 底部文案 (右下角悬浮，已避让 Manage app 按钮)
# 保持之前的完美位置
st.markdown(f"""
<div style="position: fixed; bottom: 100px; right: 30px; z-index: 999; text-align: right;">
<span style="font-size: 1.2rem; color: #333; font-weight: 600; letter-spacing: 1px; font-family: {quote_font};">
“ 前方没有胜利，挺住意味一切。”
</span>
</div>
""", unsafe_allow_html=True)
