import streamlit as st

# --- 页面配置 ---
st.set_page_config(
    page_title="微信公众号文章归档工具",
    page_icon="📥",
    layout="wide"
)

# --- 样式美化 (保持与项目一致) ---
def apply_custom_styling():
    st.markdown("""
    <style>
    .main-title {
        font-size: 2.8rem !important;
        font-weight: 800 !important;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem !important;
        text-align: center;
    }
    .sub-title {
        font-size: 1.2rem !important;
        color: #6c757d !important;
        text-align: center;
        margin-bottom: 2rem !important;
        font-weight: 300;
    }
    .custom-card {
        border-radius: 12px;
        padding: 1.5rem;
        background: white;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border: 1px solid #e9ecef;
        margin-bottom: 1.5rem;
    }
    .highlight {
        color: #667eea;
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)

apply_custom_styling()

# --- 页面标题 ---
st.markdown('<p class="main-title">📥 微信公众号文章归档工具</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">解决高校教师资料归档难题的本地化方案</p>', unsafe_allow_html=True)

# --- 核心内容 ---
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 🌟 工具简介")
    st.info("""
    这是一个专门为高校教师和科研人员设计的**本地化微信文章抓取与归档工具**。
    它能够将分散在微信公众号中的优质教学案例、竞赛信息和科研动态，一键转换为标准的 **Markdown** 格式，并自动整理到 **Obsidian** 等知识管理库中。
    """)

    st.markdown("### 🎯 解决什么问题？")
    st.write("""
    在日常工作中，高校教师经常会遇到以下痛点：
    - **资料易失联**：微信文章可能随时被删除或公众号迁移。
    - **碎片化严重**：好的教学案例分散在各个订阅号，难以统一检索。
    - **整理效率低**：手动复制文字、下载图片并排版极其耗时。
    - **图片防盗链**：直接复制的微信图片在其他软件中往往无法正常显示。
    """)

    st.markdown("### 🚀 核心能力")
    st.markdown("""
    - **深度解析**：基于 Playwright 动态渲染技术，精准提取微信文章正文内容。
    - **图片本地化**：自动下载所有图片到本地，绕过微信防盗链，确保永久可见。
    - **结构化转换**：将 HTML 转换为适合 Obsidian 保存的 Markdown，尽量保留标题、段落、链接和图片位置
    - **智能归档**：支持按“教学课题”和“学生竞赛”等类别自动归档到指定 Obsidian Vault 目录。
    - **合规安全**：全程本地运行，不消耗 AI token，不上传任何隐私数据。
    """)

with col2:
    st.markdown("### 🛠️ 技术方案")
    with st.container():
        st.markdown("""
        <div class="custom-card">
            <b>编程语言:</b> Python 3.x<br>
            <b>动态渲染:</b> Playwright (Edge)<br>
            <b>内容解析:</b> BeautifulSoup4 + LXML<br>
            <b>归档目标:</b> Obsidian / Markdown
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### 🔒 为什么 Streamlit 线上版不能执行？")
    st.warning("""
    出于**安全和技术限制**，本页面仅作为项目展示。
    
    1. **沙箱限制**: Streamlit Cloud 运行在云端服务器，无法调用用户本机 Edge，也无法写入用户本机 Obsidian Vault。。
    2. **文件系统**: 线上版无法访问您电脑上的 E 盘或本地 Obsidian 库。
    3. **反爬机制**: 微信对公有云 IP 极其敏感，必须在本地网络环境下运行以降低封禁风险。
    """)

st.divider()

# --- 运行逻辑与价值 ---
st.markdown("### 💻 本地运行流程")
steps = [
    "**环境激活**: 使用项目内置的虚拟环境 `.venv`。",
    "**配置路径**: 在脚本中设置您的 Obsidian Vault 存储位置。",
    "**一键启动**: 双击 install_first.bat 完成首次安装,双击 start_wechat_archiver.bat 启动本地归档窗口,在窗口中输入“归档课题”或“归档竞赛”加微信文章链接",
    "**自动归档**: 工具将自动完成文章下载、图片本地化、Markdown 生成并存入指定目录。"
]
for i, step in enumerate(steps):
    st.write(f"{i+1}. {step}")

st.markdown("### 💎 项目价值")
st.success("""
- **建立个人知识库**: 真正实现“所见即所得，所得即所有”。
- **提升教学科研效率**: 资料整理时间从分钟级缩短至秒级。
- **本地化安全保障**: 数据资产完全由自己掌控，不依赖第三方云服务。
""")

# --- 页脚 ---
st.caption("注：本页面仅用于展示项目功能与逻辑。如需使用，请在本地环境下运行相关脚本。")
