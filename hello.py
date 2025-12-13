import streamlit as st

# 1. 页面配置 (Page Config)
st.set_page_config(
    page_title="YaoYao's Toolbox",
    page_icon="🎒",
    layout="wide"
)

# 2. 样式优化 (CSS Hack)
# 这里虽然是方案一，但我们稍微加一点魔法，让标题不要顶着天花板
st.write("") 
st.write("") 
st.write("") 

# 3. 核心内容区 (居中排版)
# 使用 HTML 标签来实现 Streamlit 原生做不到的“居中”和“字号控制”
st.markdown("""
    <h1 style='text-align: center; font-size: 4rem; margin-bottom: 0;'>
        🎒 行政狗的百宝箱
    </h1>
    <p style='text-align: center; font-size: 1.2rem; color: #808080; font-style: italic; margin-top: 10px;'>
        —— Don't worry. Be happy. ——
    </p>
""", unsafe_allow_html=True)

# 4. 分割线
st.divider()

# 5. 底部引导文字 (居中)
st.markdown("""
    <div style='text-align: center; padding: 20px; font-size: 1.1rem;'>
        👋 <b>欢迎回来！</b><br>
        请点击左侧侧边栏 👈 选择你需要使用的工具。<br><br>
        <span style='background-color: #f0f2f6; padding: 5px 10px; border-radius: 5px; font-size: 0.9rem; color: #555;'>
            🚀 我们的目标：解放双手，拒绝无意义的加班。
        </span>
    </div>
""", unsafe_allow_html=True)