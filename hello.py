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
# 🎨 字体配置：书信版 (Letter Style)
# ==============================================================

# 英文副标题：可爱手写风 (轻松、随意)
sub_font = "'Comic Sans MS', 'Chalkboard SE', 'NoteWorthy', sans-serif"

# 中文名言：楷体/手写风 (像亲笔写下的座右铭，见字如面)
quote_font = "'KaiTi', 'STKaiti', 'BiauKai', cursive"

# ==============================================================

# 3. 核心内容区
# 注意：这里的 st.markdown 也需要 unsafe_allow_html=True
st.markdown(f"""
    <h1 style='text-align: center; font-size: 5rem; margin-bottom: 0; letter-spacing: 5px; font-weight: 900;'>
        🐾 行政狗
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
""", unsafe_allow_html=True) # <--- 这里也必须有！

# 4. 分割线
st.divider()

# 5. 底部文案 (里尔克时刻)
# 注意：这里是关键修复点！
st.markdown(f"""
    <div style='text-align: center; padding: 40px;'>
        <p style='font-size: 1rem; color: #999; margin-bottom: 30px;'>
            👋 欢迎回来，请在左侧选择工具
        </p>

        <div style='
            display: inline-block;
            padding: 20px 40px;
            background-color: #fcfcfc;
            border-radius: 4px;
            border: 1px dashed #ccc;
        '>
            <span style='
                font-size: 1.5rem;
                color: #555;
                line-height: 1.6;
                font-family: {quote_font};
            '>
                “ 前方没有胜利，挺住意味一切。”
            </span>
        </div>
    </div>
""", unsafe_allow_html=True) # <--- 关键修复：加上了这个参数！