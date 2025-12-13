import streamlit as st

# 1. 页面配置
st.set_page_config(
    page_title="YaoYao's Space",
    page_icon="🐾",
    layout="wide"
)

# 2. 样式优化
st.write("")
st.write("")
st.write("")

# ==============================================================
# 🎨 字体配置：现代博物馆风格 (Museum Style)
# ==============================================================
sub_font = "'Comic Sans MS', 'Chalkboard SE', 'NoteWorthy', sans-serif"
quote_font = "'Songti SC', 'SimSun', 'Times New Roman', serif"
# ==============================================================

# 3. 核心内容区
st.markdown(f"""
    <h1 style='text-align: center; font-size: 5rem; margin-bottom: 0; letter-spacing: 5px; font-weight: 900;'>
        🐾 行政狗 v3.0
    </h1>
    <p style='
        text-align: center;
        font-size: 1.5rem;
        color: #b2b2b2;
        margin-top: 10px;
        font-family: {sub_font};
    '>
        ~ Don't worry. Be happy. ~
    </p>
""", unsafe_allow_html=True) 

st.divider()

# 4. 底部文案 (博物馆铭牌风格)
st.markdown(f"""
    <div style='text-align: center; padding: 40px;'>
        <p style='font-size: 1rem; color: #999; margin-bottom: 30px;'>
            👋 欢迎回来，请在左侧选择工具
        </p>

        <div style='display: inline-block;'>
            <div style='
                padding: 20px 30px;
                background-color: #f8f9fa; 
                border-left: 5px solid #444; 
                border-radius: 0 4px 4px 0;
                text-align: left; 
            '>
                <span style='
                    font-size: 1.4rem; 
                    color: #333; 
                    font-weight: 600; 
                    letter-spacing: 1px;
                    line-height: 1.6;
                    font-family: {quote_font}; 
                '>
                    “ 前方没有胜利，挺住意味一切。”
                </span>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)