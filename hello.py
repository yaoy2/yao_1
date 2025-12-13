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
# 注意：HTML 属性全部使用双引号 style="..." 防止冲突
st.markdown(f"""
    <h1 style="text-align: center; font-size: 5rem; margin-bottom: 0; letter-spacing: 5px; font-weight: 900;">
        🐾 行政狗
    </h1>
    <p style="text-align: center; font-size: 1.5rem; color: #b2b2b2; margin-top: 10px; font-family: {sub_font};">
        ~ Don't worry. Be happy. ~
    </p>
""", unsafe_allow_html=True) 

st.divider()

# 4. 底部文案 (方案 3：电影字幕/黑客风格)
# 包含：欢迎提示语 + 黑色胶囊名言框
st.markdown(f"""
<div style="text-align: center; padding: 40px;">
    <p style="font-size: 1rem; color: #999; margin-bottom: 30px;">
        👋 欢迎回来，请在左侧选择工具
    </p>

    <div style="display: inline-block;">
        <div style="
            background-color: #2d2d2d; /* 深灰色胶囊背景 */
            padding: 15px 35px; 
            border-radius: 50px; /* 圆角胶囊形状 */
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); /* 微微的悬浮阴影 */
        ">
            <span style="
                font-size: 1.1rem; 
                color: #e0e0e0; /* 浅灰白色文字 */
                font-weight: 300;
                letter-spacing: 2px; /* 字间距拉开，更有电影感 */
                font-family: {quote_font};
            ">
                前方没有胜利，挺住意味一切。
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)
