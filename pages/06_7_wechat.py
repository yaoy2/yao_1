import streamlit as st
from utils.ui_theme import render_home_link

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
    .route-header {
        font-size: 1.3rem !important;
        font-weight: 700 !important;
        color: #667eea !important;
        margin-bottom: 0.5rem !important;
    }
    .tag {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 4px;
    }
    .tag-link { background: #e8f0fe; color: #1a73e8; }
    .tag-file { background: #fef3e0; color: #e67e22; }
    </style>
    """, unsafe_allow_html=True)

apply_custom_styling()
render_home_link()

# --- 页面标题 ---
st.markdown('<p class="main-title">📥 微信公众号文章归档工具</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">统一归档技能 — 覆盖公众号链接抓取归档（raw / 课题 / 竞赛）和本地文件上传 IMA 知识库</p>', unsafe_allow_html=True)

# --- 工具简介 ---
st.markdown("### 🌟 工具简介")
st.info("""
这是一个专为高校教师和科研人员设计的**本地化归档工具**。
它能将微信公众号文章一键转换为 Markdown 存入 Obsidian，也能将本地文件上传到 IMA 知识库，按 **raw / 学院 / 课题 / 竞赛** 四个类别智能归档。
""")

# --- 触发词与路由总表 ---
st.markdown("### 📋 触发词与路由总表")

route_data = [
    {"触发词": "归档raw", "输入类型": "公众号链接", "处理方式": "Playwright 抓取", "存储目标": "Obsidian raw 目录"},
    {"触发词": "归档课题", "输入类型": "公众号链接", "处理方式": "Playwright + IMA 上传", "存储目标": "GoogleDrive 课题目录 + IMA 竞赛&课题"},
    {"触发词": "归档竞赛", "输入类型": "公众号链接", "处理方式": "Playwright + IMA 上传", "存储目标": "GoogleDrive 竞赛目录 + IMA 竞赛&课题"},
    {"触发词": "归档学院", "输入类型": "本地文件", "处理方式": "IMA 上传", "存储目标": "IMA 健康学院-2026 根目录"},
    {"触发词": "归档课题", "输入类型": "本地文件", "处理方式": "复制 + IMA 上传", "存储目标": "GoogleDrive 课题目录 + IMA 竞赛&课题"},
    {"触发词": "归档竞赛", "输入类型": "本地文件", "处理方式": "复制 + IMA 上传", "存储目标": "GoogleDrive 竞赛目录 + IMA 竞赛&课题"},
]

st.dataframe(route_data, use_container_width=True, hide_index=True)

st.divider()

# --- 四条路线分区介绍 ---
st.markdown("### 🛤️ 四条归档路线")

col_a, col_b = st.columns(2)

with col_a:
    # 路线 A
    st.markdown("#### 路线 A：归档 raw（公众号链接）")
    st.markdown('<span class="tag tag-link">公众号链接</span>', unsafe_allow_html=True)
    st.write("""
    **触发词：** `归档raw`
    **流程：** Playwright 动态渲染 → 提取正文 → 转 Markdown → 保存到 Obsidian raw 目录
    **存储目标：**
    `E:\\GoogleDrive\\Obsidian Vault\\00\\LLM_WIKI\\raw\\`
    """)

    st.info("raw 归档不做分类，直接存入 raw 目录，适合需要原始留存的通用文章。")

    # 路线 B
    st.markdown("#### 路线 B：归档课题 / 竞赛（公众号链接）")
    st.markdown('<span class="tag tag-link">公众号链接</span>', unsafe_allow_html=True)
    st.write("""
    **触发词：** `归档课题` / `归档竞赛`
    **流程：** Playwright 抓取 → 存入 GoogleDrive → 上传 IMA 竞赛&课题知识库
    **存储目标：**
    - 课题 → `E:\\GoogleDrive\\Obsidian Vault (1)\\ChatGPT\\50_教学_课题\\`
    - 竞赛 → `E:\\GoogleDrive\\Obsidian Vault (1)\\ChatGPT\\40_学生_竞赛\\`
    - IMA「竞赛&课题」知识库对应文件夹
    """)

with col_b:
    # 路线 C
    st.markdown("#### 路线 C：归档学院（本地文件）")
    st.markdown('<span class="tag tag-file">本地文件</span>', unsafe_allow_html=True)
    st.write("""
    **触发词：** `归档学院`
    **输入：** 本地文件路径（截图、PDF、Word、Excel 等）
    **流程：** IMA 上传 → 健康学院-2026 知识库根目录
    **存储目标：**
    IMA「健康学院-2026」知识库根目录
    """)

    st.info("学院归档只上传到 IMA，不做 GoogleDrive 备份。")

    # 路线 D
    st.markdown("#### 路线 D：归档课题 / 竞赛（本地文件）")
    st.markdown('<span class="tag tag-file">本地文件</span>', unsafe_allow_html=True)
    st.write("""
    **触发词：** `归档课题` / `归档竞赛`
    **输入：** 本地文件路径
    **流程：** 复制到 GoogleDrive 对应目录 → 上传 IMA 竞赛&课题知识库
    **存储目标：**
    - 课题 → `E:\\GoogleDrive\\Obsidian Vault (1)\\ChatGPT\\50_教学_课题\\`
    - 竞赛 → `E:\\GoogleDrive\\Obsidian Vault (1)\\ChatGPT\\40_学生_竞赛\\`
    - IMA「竞赛&课题」知识库对应文件夹
    """)

st.divider()

# --- ⚠️ Streamlit 线上版能做到哪些 ---
st.markdown("### ⚠️ Streamlit 版 vs. WorkBuddy 版能做到哪些")

st.warning("""
**为什么有些路线 Streamlit 做不了？**

IMA 知识库的上传功能依赖 `preflight-check.cjs`、`cos-upload.cjs` 等 **Node.js 脚本**，
本项目是纯 Python 仓库，没有这些脚本，所以涉及 IMA 上传的路线（B/C/D 的 IMA 部分）无法在 Streamlit 中执行。

| 路线 | Streamlit 能做 | 需要 WorkBuddy |
|------|:---:|:---:|
| A: 归档 raw（链接） | ✅ Playwright 抓取 | — |
| B: 归档课题/竞赛（链接） | ✅ Playwright 抓取 | ✅ IMA 上传部分 |
| C: 归档学院（本地文件） | ❌ 无 Playwright 意义 | ✅ IMA 上传 |
| D: 归档课题/竞赛（本地文件） | ✅ 文件复制到 GoogleDrive | ✅ IMA 上传部分 |

**结论：** Streamlit 版负责 Playwright 抓取 + 本地存储，IMA 上传统一走 WorkBuddy 的 AI 助手执行。
""")

st.divider()

# --- IMA 知识库信息 ---
st.markdown("### 🗄️ IMA 知识库信息")

ima_col1, ima_col2 = st.columns(2)

with ima_col1:
    st.markdown("#### 「健康学院-2026」（归档学院用）")
    st.code("kb_id: odi6DH7ugdn-dRgcBkGDhogEgRykbRDxNH46UCYsdRc=")
    st.code("根目录 folder_id: 7442846495830267")
    st.caption("不传 folder_id 即为根目录")

with ima_col2:
    st.markdown("#### 「竞赛&课题」（归档课题/竞赛用）")
    st.code("kb_id: -ZgVWGtAdFEZQCtt_P04OHZgfDdUIDptPtUCdEpyBsY=")
    st.code("课题 folder_id: folder_7457623423078090")
    st.code("竞赛 folder_id: folder_7457623402114290")

st.divider()

# --- 输入识别规则 ---
st.markdown("### 🔍 输入识别规则")

st.write("""
- 包含 `https://mp.weixin.qq.com/` → 走**路线 A 或 B**（公众号链接）
- 包含本地文件路径（如 `C:\\` `D:\\` `E:\\` 或文件扩展名）→ 走**路线 C 或 D**（本地文件）
- 触发词优先级：说了"归档学院" → 路线 C；说了"归档课题/竞赛" → 路线 B 或 D
- 链接和归档类型都没说清楚 → 直接询问：归档到哪里（raw / 学院 / 课题 / 竞赛）？
""")

st.divider()

# --- 本地运行流程 ---
st.markdown("### 💻 本地运行流程")
steps = [
    "**环境激活**: 使用项目内置的虚拟环境 `.venv`。",
    "**启动工具**: 双击 `start_wechat_archiver.bat` 启动本地归档窗口。",
    "**输入指令**: 在输入框中输入触发词（如“归档课题”）+ 链接或文件路径。",
    "**自动归档**: 工具自动完成抓取、转换、存档，部分路线会同步上传 IMA。",
]
for i, step in enumerate(steps):
    st.write(f"{i+1}. {step}")

st.divider()

# --- 项目价值 ---
st.markdown("### 💎 项目价值")
st.success("""
- **多路线覆盖**: 公众号链接归档（raw / 课题 / 竞赛）+ 本地文件归档（学院 / 课题 / 竞赛）
- **双通道存储**: Obsidian 本地知识库 + IMA 云知识库，重要资料双重保障
- **智能识别**: 根据触发词和输入内容自动判断走哪条路线
- **本地化安全**: 数据资产完全由自己掌控，不依赖第三方云服务
""")

# --- 页脚 ---
st.caption("注：本页面仅用于展示归档工具的功能与逻辑。如需使用，请在本地环境下运行相关脚本。")
