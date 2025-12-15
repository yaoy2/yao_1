import streamlit as st
import datetime
import os

# --- 配置页面 ---
st.set_page_config(
    page_title="Yao's 手术刀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 文件常量 ---
ARCHIVE_FILE = "yao_archive.md"

# --- 核心归档函数 ---
def append_to_archive(user_text, ai_text):
    """
    将对话内容以 Obsidian 友好的、带有空行的 Markdown 格式追加写入文件。
    内容必须是 Markdown 格式。
    """
    
    # 确保内容非空
    if not user_text.strip() and not ai_text.strip():
        return False
    
    # 获取当前时间
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 构造 Obsidian 友好的 Markdown 块
    # 严格遵循：二级标题 + 空行 + **标签** + 空行 + 内容 + 水平分隔线 规范
    markdown_block = f"""

## [{timestamp}]

**User:**

{user_text.strip()}

---

**AI:**

{ai_text.strip()}

"""
    
    try:
        # 使用 'a' 模式追加写入文件
        with open(ARCHIVE_FILE, 'a', encoding='utf-8') as f:
            f.write(markdown_block)
        return True
    except Exception as e:
        st.error(f"归档失败: {e}")
        return False

# --- 侧边栏输入区 ---
with st.sidebar:
    st.title("✂️ 对话内容输入")
    st.markdown("---")
    
    st.caption("请确保粘贴的内容为**Markdown格式**，以保证排版美观。")
    
    # 输入框
    user_input = st.text_area(
        "用户提问 (User Markdown)",
        height=150,
        placeholder="粘贴您的 Markdown 格式提问内容..."
    )
    
    ai_response = st.text_area(
        "AI 回复 (Gemini Markdown)",
        height=300,
        placeholder="粘贴 Gemini 的 Markdown 格式回复内容..."
    )
    
    archive_button = st.button("🔪 归档并渲染预览")

# --- 主展示区 ---
st.header("Yao's 手术刀 (Markdown 归档工具)")
st.caption(f"归档文件：{ARCHIVE_FILE}")
st.markdown("---")

# 按钮点击后的操作
if archive_button:
    if append_to_archive(user_input, ai_response):
        st.success(f"✅ 归档成功！请在 Obsidian 中查看 {ARCHIVE_FILE} 文件。")
        
        st.subheader("最新对话预览 (Streamlit Render)")
        st.markdown("---")
        
        # 渲染用户提问 - 使用 st.chat_message("user")
        with st.chat_message("user"):
            # 使用 st.markdown 渲染用户侧的 Markdown
            st.markdown(user_input.strip())
            
        # 渲染 AI 回答 - 使用 st.chat_message("assistant")
        with st.chat_message("assistant"):
            # 关键：使用 st.markdown 完美渲染 AI 的结构
            st.markdown(ai_response.strip(), unsafe_allow_html=True)
            
        st.markdown("---")
    else:
        st.warning("请输入对话内容后，再点击归档。")

# 初始提示
else:

    st.info("💡 提示：这是一个高精度 Markdown 归档工具。请将**格式已整理好的 Markdown 文本**粘贴到左侧输入框，点击归档即可完美保存排版和结构。")
