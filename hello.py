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
# 保持顶格，防止缩进错误
st.markdown(f"""
<h1 style="text-align: center; font-size: 5rem; margin-bottom: 0; letter-spacing: 5px; font-weight: 900;">
🐾 行政狗
</h1>
<p style="text-align: center; font-size: 1.5rem; color: #b2b2b2; margin-top: 10px; font-family: {sub_font};">
~ Don't worry. Be happy. ~
</p>
""", unsafe_allow_html=True) 

st.divider()

# 4. 底部文案 (石碑风格)
# 已删除欢迎语，仅保留石碑名言
# 样式特点：白底、黑字、粗黑框、硬阴影(box-shadow)、直角
st.markdown(f"""
<div style="text-align: center; padding: 40px;">
<div style="display: inline-block;">
<div style="
background-color: #ffffff; 
color: #000000;
padding: 20px 40px; 
border: 3px solid #000000; 
box-shadow: 6px 6px 0px #000000; 
border-radius: 0px; 
max-width: 800px;
">
<span style="
font-size: 1.3rem; 
font-weight: 600; 
letter-spacing: 2px; 
line-height: 1.8; 
font-family: {quote_font};
">
“ 前方没有胜利，挺住意味一切。”
</span>
</div>
</div>
</div>
""", unsafe_allow_html=True)
