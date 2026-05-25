"""
SOVO 课程作业评分与成绩合成系统 - 高级美化版
作者: Python 全栈开发专家
版本: 2.0.0 - 高级界面
"""

# --- 导入所有依赖库 ---
import streamlit as st
import pandas as pd
import numpy as np
import io
import re
from io import BytesIO
import time
from datetime import datetime
import warnings
from utils.ui_theme import render_home_link
warnings.filterwarnings('ignore')

# 检查并导入可选依赖
try:
    import docx
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.document import Document as _Document
    from docx.table import Table as _Table
    from docx.table import _Cell
    from docx.text.paragraph import Paragraph as _Paragraph
    from docx.oxml.text.paragraph import CT_P
    from docx.oxml.table import CT_Tbl
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    import pypdf
    PDF_AVAILABLE = True
except ImportError:
    try:
        import PyPDF2 as pypdf
        PDF_AVAILABLE = True
    except ImportError:
        PDF_AVAILABLE = False

# --- 高级样式配置 ---
def apply_custom_styling():
    """应用自定义样式（使用纯Streamlit方法）"""
    st.markdown("""
    <style>
    /* 主标题样式 */
    .main-title {
        font-size: 2.8rem !important;
        font-weight: 800 !important;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem !important;
        text-align: center;
    }
    
    /* 副标题样式 */
    .sub-title {
        font-size: 1.2rem !important;
        color: #6c757d !important;
        text-align: center;
        margin-bottom: 2rem !important;
        font-weight: 300;
    }
    
    /* 卡片样式 */
    .custom-card {
        border-radius: 12px;
        padding: 1.5rem;
        background: white;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border: 1px solid #e9ecef;
        margin-bottom: 1.5rem;
        transition: all 0.3s ease;
    }
    
    .custom-card:hover {
        box-shadow: 0 8px 30px rgba(0,0,0,0.12);
        transform: translateY(-2px);
    }
    
    /* 指标卡片 */
    .metric-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        border-left: 4px solid #667eea;
    }
    
    /* 步骤指示器 */
    .step-indicator {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        margin-right: 10px;
    }
    
    /* 进度条样式 */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
    
    /* 选项卡样式 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 12px 24px;
        font-weight: 500;
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        transition: all 0.3s ease;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: #e9ecef;
    }
    
    .stTabs [aria-selected="true"] {
        background: white !important;
        border-bottom: 2px solid #667eea !important;
        color: #667eea !important;
    }
    
    /* 按钮美化 */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.3s ease !important;
        border: none !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
    }
    
    /* 上传区域美化 */
    .uploadedFile {
        border: 2px dashed #dee2e6 !important;
        border-radius: 10px !important;
        padding: 15px !important;
        background: #f8f9fa !important;
    }
    
    /* 成功/错误消息 */
    .stAlert {
        border-radius: 10px !important;
        border-left: 4px solid !important;
    }
    
    .stAlert [data-testid="stMarkdownContainer"] {
        font-weight: 500;
    }
    
    /* 数据表格美化 */
    .dataframe {
        border-radius: 10px !important;
        overflow: hidden !important;
    }
    
    /* 状态指示器 */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
    }
    
    .status-success {
        background: #d4edda;
        color: #155724;
    }
    
    .status-warning {
        background: #fff3cd;
        color: #856404;
    }
    
    .status-error {
        background: #f8d7da;
        color: #721c24;
    }
    
    </style>
    """, unsafe_allow_html=True)

# --- 高级UI组件 ---
def create_metric_card(title, value, delta=None, icon="📊"):
    """创建美观的指标卡片"""
    col1, col2 = st.columns([1, 4])
    with col1:
        st.markdown(f'<div style="font-size: 2rem; color: #667eea;">{icon}</div>', unsafe_allow_html=True)
    with col2:
        st.metric(title, value, delta)
    return None

def create_step_indicator(step_number, title, is_active=True):
    """创建步骤指示器"""
    if is_active:
        st.markdown(f"""
        <div style="display: flex; align-items: center; margin-bottom: 1rem; padding: 12px; background: linear-gradient(135deg, rgba(102,126,234,0.1) 0%, rgba(118,75,162,0.1) 100%); border-radius: 10px; border-left: 4px solid #667eea;">
            <div class="step-indicator">{step_number}</div>
            <div style="font-weight: 600; font-size: 1.1rem; color: #2c3e50;">{title}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="display: flex; align-items: center; margin-bottom: 1rem; padding: 12px; background: #f8f9fa; border-radius: 10px; border-left: 4px solid #dee2e6;">
            <div style="display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 50%; background: #adb5bd; color: white; font-weight: bold; margin-right: 10px;">{step_number}</div>
            <div style="font-weight: 500; font-size: 1.1rem; color: #6c757d;">{title}</div>
        </div>
        """, unsafe_allow_html=True)

def create_file_card(file_name, file_size, status="success"):
    """创建美观的文件卡片"""
    status_colors = {
        "success": "#28a745",
        "warning": "#ffc107",
        "error": "#dc3545"
    }
    
    status_texts = {
        "success": "✓ 就绪",
        "warning": "⚠ 警告",
        "error": "✗ 错误"
    }
    
    st.markdown(f"""
    <div class="custom-card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="flex: 1;">
                <div style="display: flex; align-items: center; margin-bottom: 5px;">
                    <span style="font-size: 1.2rem; margin-right: 10px;">📄</span>
                    <span style="font-weight: 600; font-size: 1rem;">{file_name}</span>
                </div>
                <div style="color: #6c757d; font-size: 0.9rem;">
                    {file_size:.1f} KB
                </div>
            </div>
            <div>
                <span class="status-badge status-{status}" style="border-color: {status_colors[status]}">
                    {status_texts[status]}
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def create_feature_card(icon, title, description):
    """创建功能特性卡片"""
    st.markdown(f"""
    <div class="custom-card" style="text-align: center;">
        <div style="font-size: 2.5rem; margin-bottom: 1rem; color: #667eea;">{icon}</div>
        <h4 style="margin-bottom: 0.5rem; color: #2c3e50; font-weight: 600;">{title}</h4>
        <p style="color: #6c757d; font-size: 0.9rem; margin: 0;">{description}</p>
    </div>
    """, unsafe_allow_html=True)

# --- 核心功能函数 ---
def clean_student_id(val):
    """清洗学号"""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if '.' in s:
        s = s.split('.')[0]
    return s

def extract_text_from_docx(file_content):
    """从DOCX文件提取文本"""
    if not DOCX_AVAILABLE:
        return "❌ 未安装python-docx库，请运行: pip install python-docx", 0
    
    try:
        doc = docx.Document(BytesIO(file_content))
        image_count = 0
        
        try:
            image_count = sum(1 for rel in doc.part.rels.values() 
                            if hasattr(rel, 'reltype') and rel.reltype == RELATIONSHIP_TYPE.IMAGE)
        except:
            pass
        
        items = []
        processed_cells = set()
        
        def iter_block_items(parent):
            if isinstance(parent, _Document):
                parent_elm = parent.element.body
            elif isinstance(parent, _Cell):
                parent_elm = parent._tc
            elif isinstance(parent, _Table):
                parent_elm = parent._tbl
            else:
                parent_elm = getattr(parent, "_element", None) or getattr(parent, "element", None)
            
            if parent_elm is None:
                return
            
            for child in parent_elm.iterchildren():
                if isinstance(child, CT_P):
                    yield _Paragraph(child, parent)
                elif isinstance(child, CT_Tbl):
                    yield _Table(child, parent)
        
        for block in iter_block_items(doc):
            if isinstance(block, _Paragraph):
                text = block.text.strip()
                if text:
                    items.append(text)
            elif isinstance(block, _Table):
                for row_idx, row in enumerate(block.rows):
                    row_items = []
                    for cell in row.cells:
                        cell_id = f"{row_idx}_{id(cell)}"
                        if cell_id in processed_cells:
                            continue
                        processed_cells.add(cell_id)
                        cell_text = cell.text.strip()
                        if cell_text:
                            row_items.append(cell_text)
                    if row_items:
                        items.append(" | ".join(row_items))
        
        text_content = "\n".join(items)
        lines = [line.strip() for line in text_content.splitlines() if line.strip()]
        return "\n".join(lines), image_count
        
    except Exception as e:
        return f"❌ DOCX读取失败: {str(e)}", 0

def extract_text_from_pdf(file_content):
    """从PDF文件提取文本"""
    if not PDF_AVAILABLE:
        return "❌ 未安装PDF处理库，请运行: pip install pypdf", 0
    
    try:
        reader = pypdf.PdfReader(BytesIO(file_content))
        texts = []
        
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
                page_text = re.sub(r'\x00', '', page_text)
                page_text = page_text.strip()
                if page_text:
                    texts.append(page_text)
            except:
                pass
        
        text_content = "\n".join(texts)
        if not text_content.strip():
            return "❌ 未能从PDF中提取到文本内容", 0
        
        return text_content, 0
        
    except Exception as e:
        return f"❌ PDF读取失败: {str(e)}", 0

def process_uploaded_files(uploaded_files):
    """处理上传的文件"""
    results = []
    
    for file in uploaded_files:
        file_content = file.read()
        file_name = file.name
        
        if file_name.lower().endswith('.docx'):
            text, image_count = extract_text_from_docx(file_content)
        elif file_name.lower().endswith('.pdf'):
            text, image_count = extract_text_from_pdf(file_content)
        else:
            text = "❌ 不支持的文件格式"
            image_count = 0
        
        results.append({
            'file_name': file_name,
            'text': text,
            'image_count': image_count,
            'success': not text.startswith('❌')
        })
        
        file.seek(0)
    
    return results

def calculate_final_scores(df_ai, df_roster, bonus_dict):
    """计算最终成绩"""
    if '学号' not in df_roster.columns:
        st.error("花名册中必须包含'学号'列")
        return None
    
    df_roster['_clean_id'] = df_roster['学号'].apply(clean_student_id)
    df_ai['_clean_id'] = df_ai['学号'].apply(clean_student_id)
    
    if '文件名' in df_ai.columns:
        df_ai['特权加分'] = df_ai['文件名'].map(bonus_dict).fillna(0)
    else:
        df_ai['特权加分'] = 0
    
    df_ai['团队总分'] = df_ai['AI基础分'] + df_ai['特权加分']
    df_ai['最终成绩'] = (df_ai['团队总分'] * df_ai['个人权重']).round(1)
    
    merge_cols = ['_clean_id', 'AI基础分', '特权加分', '团队总分', '个人权重', '最终成绩']
    if '文件名' in df_ai.columns:
        merge_cols.append('文件名')
    
    df_final = pd.merge(
        df_roster,
        df_ai[merge_cols],
        on='_clean_id',
        how='left'
    )
    
    score_cols = ['AI基础分', '特权加分', '团队总分', '个人权重', '最终成绩']
    for col in score_cols:
        if col in df_final.columns:
            df_final[col] = df_final[col].fillna(0)
    
    if '文件名' in df_final.columns:
        df_final['文件名'] = df_final['文件名'].fillna('未提交')
    
    df_final['备注'] = df_final.apply(
        lambda row: '缺交' if row['最终成绩'] == 0 else '', 
        axis=1
    )
    
    if '_clean_id' in df_final.columns:
        df_final = df_final.drop('_clean_id', axis=1)
    
    return df_final

def create_download_excel(df_final):
    """创建Excel文件供下载"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False, sheet_name='成绩单')
        workbook = writer.book
        worksheet = writer.sheets['成绩单']
        for i, col in enumerate(df_final.columns):
            column_width = max(df_final[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, min(column_width, 50))
    output.seek(0)
    return output

# --- 默认配置 ---
DEFAULT_PROMPT = """你现在是资深课程评审专家。请阅读我发送的课程报告（含表格数据），严格按以下标准评分并提取信息。

### 一、 评分标准（满分100分）
请仅根据**文本内容质量**，对以下维度打分（不要考虑图片数量或排版，只看内容）：
1. **创意来源 (15分)**
2. **服务人群 (5分)**
3. **解决方案 (20分)**
4. **创意类型 (5分)**
5. **创新方法 (15分)**
6. **竞品分析 (15分)**
7. **可行性 (10分)**
8. **团队分工 (5分)**
9. **AI贡献 (10分)**

### 二、 名单与权重提取
报告中的名单可能以**表格形式**出现（如：`姓名 | 学号 | 权重`）。
1. 请抓取所有成员的 **姓名** 和 **学号**。
2. **提取权重：** 重点寻找 **"权重"** 或 **"Weight"** 列。如果没写，默认记为 **1.0**。

### 三、 输出格式（CSV代码块）
请只输出一个 CSV 代码块，不要废话。表头：`文件名,AI基础分,学生姓名,学号,个人权重`
示例：
```csv
第1组.docx, 88, 张三, 202301, 1.0
第1组.docx, 88, 李四, 202302, 0.95
```"""

# --- 主应用 ---
def main():
    # 页面配置
    st.set_page_config(
        page_title="期末项目报告 智能评分系统",
        layout="wide",
        page_icon="🎓",
        initial_sidebar_state="collapsed"
    )
    render_home_link()
    
    # 应用自定义样式
    apply_custom_styling()
    
    # 豪华标题区域
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<h1 class="main-title">🎓 期末项目报告 智能评分系统</h1>', unsafe_allow_html=True)
        st.markdown('<p class="sub-title">AI驱动的课程报告自动化评分与成绩合成平台</p>', unsafe_allow_html=True)
    
    # 功能特性展示
    with st.container():
        st.markdown("### ✨ 核心功能")
        cols = st.columns(4)
        features = [
            ("📄", "智能文档解析", "支持DOCX/PDF格式，自动提取文本和表格"),
            ("🤖", "AI评分集成", "无缝对接DeepSeek/Kimi等大模型"),
            ("👑", "上帝模式", "可视化特权加分配置界面"),
            ("📊", "数据洞察", "智能统计与可视化分析")
        ]
        for i, (icon, title, desc) in enumerate(features):
            with cols[i]:
                create_feature_card(icon, title, desc)
    
    # 初始化session state
    if 'extraction_results' not in st.session_state:
        st.session_state.extraction_results = []
    if 'bonus_data' not in st.session_state:
        st.session_state.bonus_data = {}
    if 'final_scores' not in st.session_state:
        st.session_state.final_scores = None
    
    # 创建选项卡
    tab1, tab2, tab3 = st.tabs([
        "📁 文档处理", 
        "🧮 成绩计算", 
        "📈 数据分析"
    ])
    
    # --- 选项卡1: 文档处理 ---
    with tab1:
        st.markdown("### 📁 文档上传与处理")
        
        create_step_indicator(1, "上传学生报告文件", True)
        
        # 文件上传区域
        with st.container():
            uploaded_files = st.file_uploader(
                "拖拽或选择文件上传",
                type=["docx", "pdf"],
                accept_multiple_files=True,
                help="支持批量上传DOCX和PDF格式的文件",
                label_visibility="collapsed"
            )
            
            if uploaded_files:
                st.success(f"✅ 成功上传 {len(uploaded_files)} 个文件")
                
                # 文件列表展示
                with st.expander("📋 查看文件详情", expanded=True):
                    cols = st.columns(2)
                    for i, file in enumerate(uploaded_files):
                        with cols[i % 2]:
                            create_file_card(
                                file.name, 
                                file.size/1024,
                                "success"
                            )
                
                # 处理按钮
                col1, col2, col3 = st.columns([2, 1, 2])
                with col2:
                    process_btn = st.button("🚀 开始处理文件", type="primary", use_container_width=True)
                
                if process_btn:
                    with st.spinner("正在智能解析文档内容..."):
                        progress_bar = st.progress(0)
                        
                        results = []
                        for i, file in enumerate(uploaded_files):
                            progress_bar.progress((i + 1) / len(uploaded_files))
                            
                            file_content = file.read()
                            file_name = file.name
                            
                            if file_name.lower().endswith('.docx'):
                                text, image_count = extract_text_from_docx(file_content)
                            elif file_name.lower().endswith('.pdf'):
                                text, image_count = extract_text_from_pdf(file_content)
                            else:
                                text = "❌ 不支持的文件格式"
                                image_count = 0
                            
                            results.append({
                                'file_name': file_name,
                                'text': text,
                                'image_count': image_count,
                                'success': not text.startswith('❌')
                            })
                            
                            file.seek(0)
                        
                        st.session_state.extraction_results = results
                        progress_bar.empty()
                        
                        # 处理结果统计
                        success_count = sum(r['success'] for r in results)
                        total_images = sum(r['image_count'] for r in results)
                        
                        st.success(f"""
                        ✅ **处理完成！**  
                        📊 **统计结果：**  
                        • 成功解析: {success_count}/{len(results)} 个文件  
                        • 总计图片: {total_images} 张  
                        • 总字符数: {sum(len(r['text']) for r in results if r['success']):,}
                        """)
                
                # 显示处理结果
                if st.session_state.extraction_results:
                    create_step_indicator(2, "生成AI评分指令", True)
                    
                    with st.container():
                        st.markdown("#### 🛠️ 评分标准配置")
                        
                        prompt_text = st.text_area(
                            "编辑AI评分指令模板",
                            value=DEFAULT_PROMPT,
                            height=350,
                            label_visibility="collapsed"
                        )
                        
                        if st.button("🔧 生成完整AI指令", type="secondary", use_container_width=True):
                            full_prompt = f"{prompt_text}\n\n"
                            full_prompt += "=== 以下是所有报告内容 ===\n\n"
                            
                            for result in st.session_state.extraction_results:
                                if result['success']:
                                    full_prompt += f"\n\n--- 文件: {result['file_name']} (图片: {result['image_count']}张) ---\n"
                                    full_prompt += result['text']
                            
                            st.markdown("#### 📋 生成的AI指令")
                            st.code(full_prompt, language="text")
                            
                            st.download_button(
                                label="📥 下载指令文件",
                                data=full_prompt,
                                file_name=f"ai_instruction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                mime="text/plain",
                                use_container_width=True,
                                icon="📥"
                            )
    
    # --- 选项卡2: 成绩计算 ---
    with tab2:
        st.markdown("### 🧮 成绩计算与上帝模式")
        
        cols = st.columns(2)
        
        with cols[0]:
            create_step_indicator(1, "导入AI评分结果", True)
            with st.container():
                st.markdown("#### 🤖 AI评分结果")
                ai_csv_input = st.text_area(
                    "粘贴AI返回的CSV格式成绩单",
                    height=150,
                    placeholder="格式示例：\n文件名,AI基础分,学生姓名,学号,个人权重\n第1组.docx,88,张三,202301,1.0",
                    label_visibility="collapsed"
                )
                
                if ai_csv_input:
                    try:
                        df_ai = pd.read_csv(io.StringIO(ai_csv_input))
                        required_cols = ['文件名', 'AI基础分', '学生姓名', '学号', '个人权重']
                        missing_cols = [col for col in required_cols if col not in df_ai.columns]
                        
                        if missing_cols:
                            st.error(f"❌ 缺少列: {', '.join(missing_cols)}")
                        else:
                            st.session_state.df_ai = df_ai
                            st.success(f"✅ 成功解析 {len(df_ai)} 条记录")
                            
                            with st.expander("📊 数据预览"):
                                st.dataframe(df_ai.head(), use_container_width=True)
                    except Exception as e:
                        st.error(f"❌ 解析失败: {str(e)}")
        
        with cols[1]:
            create_step_indicator(2, "导入学生花名册", True)
            with st.container():
                st.markdown("#### 👥 学生花名册")
                roster_file = st.file_uploader(
                    "上传Excel格式花名册",
                    type=["xlsx", "xls"],
                    label_visibility="collapsed"
                )
                
                if roster_file is not None:
                    try:
                        df_roster = pd.read_excel(roster_file, dtype=str)
                        
                        if '姓名' not in df_roster.columns or '学号' not in df_roster.columns:
                            st.error("❌ 花名册必须包含'姓名'和'学号'列")
                        else:
                            st.session_state.df_roster = df_roster
                            st.success(f"✅ 成功导入 {len(df_roster)} 名学生")
                            
                            with st.expander("📋 花名册预览"):
                                st.dataframe(df_roster.head(), use_container_width=True)
                    except Exception as e:
                        st.error(f"❌ 读取失败: {str(e)}")
        
        # 上帝模式
        if 'df_ai' in st.session_state:
            st.markdown("---")
            create_step_indicator(3, "上帝模式 - 特权加分配置", True)
            
            with st.container():
                st.markdown("#### 👑 特权加分配置面板")
                st.markdown("为各个小组配置额外的加分项")
                
                if '文件名' in st.session_state.df_ai.columns:
                    group_names = st.session_state.df_ai['文件名'].unique().tolist()
                    
                    if not st.session_state.bonus_data:
                        st.session_state.bonus_data = {group: 0.0 for group in group_names}
                    
                    bonus_df = pd.DataFrame({
                        '小组名称': group_names,
                        '特权加分': [st.session_state.bonus_data.get(group, 0.0) for group in group_names]
                    })
                    
                    edited_df = st.data_editor(
                        bonus_df,
                        column_config={
                            "小组名称": st.column_config.TextColumn("📁 小组名称", disabled=True),
                            "特权加分": st.column_config.NumberColumn(
                                "⭐ 特权加分",
                                help="为小组配置额外加分",
                                min_value=-20,
                                max_value=20,
                                step=0.5,
                                format="%.1f"
                            )
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    if not edited_df.equals(bonus_df):
                        st.session_state.bonus_data = dict(zip(edited_df['小组名称'], edited_df['特权加分']))
                        st.success("✅ 加分配置已更新")
        
        # 计算按钮
        if 'df_ai' in st.session_state and 'df_roster' in st.session_state:
            st.markdown("---")
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🚀 计算最终成绩", type="primary", use_container_width=True):
                    with st.spinner("正在计算最终成绩..."):
                        try:
                            df_final = calculate_final_scores(
                                st.session_state.df_ai,
                                st.session_state.df_roster,
                                st.session_state.bonus_data
                            )
                            
                            if df_final is not None:
                                st.session_state.final_scores = df_final
                                st.balloons()
                                st.success(f"""
                                🎉 **成绩计算完成！**  
                                📊 **统计摘要：**  
                                • 总人数: {len(df_final)} 人  
                                • 平均分: {df_final['最终成绩'].mean():.1f} 分  
                                • 最高分: {df_final['最终成绩'].max():.1f} 分  
                                • 及格率: {len(df_final[df_final['最终成绩'] >= 60]) / len(df_final) * 100:.1f}%
                                """)
                        except Exception as e:
                            st.error(f"❌ 计算失败: {str(e)}")
    
    # --- 选项卡3: 数据分析 ---
    with tab3:
        st.markdown("### 📈 数据分析与可视化")
        
        if st.session_state.final_scores is not None:
            df_final = st.session_state.final_scores
            
            # 关键指标
            st.markdown("#### 📊 关键指标")
            cols = st.columns(4)
            
            with cols[0]:
                submitted = len(df_final[df_final['最终成绩'] > 0])
                total = len(df_final)
                create_metric_card(
                    "提交率",
                    f"{submitted}/{total}",
                    f"{submitted/total*100:.1f}%",
                    "📝"
                )
            
            with cols[1]:
                avg_score = df_final['最终成绩'].mean()
                create_metric_card(
                    "平均分",
                    f"{avg_score:.1f}",
                    "满分100",
                    "📊"
                )
            
            with cols[2]:
                max_score = df_final['最终成绩'].max()
                create_metric_card(
                    "最高分",
                    f"{max_score:.1f}",
                    None,
                    "🏆"
                )
            
            with cols[3]:
                pass_count = len(df_final[df_final['最终成绩'] >= 60])
                pass_rate = pass_count / len(df_final) * 100
                create_metric_card(
                    "及格率",
                    f"{pass_rate:.1f}%",
                    f"{pass_count}人",
                    "✅"
                )
            
            # 成绩分布
            st.markdown("#### 📈 成绩分布分析")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # 创建成绩分布
                bins = [0, 60, 70, 80, 90, 100]
                labels = ['不及格 (<60)', '及格 (60-69)', '良好 (70-79)', '优秀 (80-89)', '卓越 (90-100)']
                df_final['成绩区间'] = pd.cut(df_final['最终成绩'], bins=bins, labels=labels, right=False)
                distribution = df_final['成绩区间'].value_counts().reindex(labels)
                
                # 使用bar chart
                st.bar_chart(distribution)
            
            with col2:
                # 分数统计表
                stats_df = pd.DataFrame({
                    '统计指标': ['最小值', '25%分位数', '中位数', '75%分位数', '最大值', '标准差'],
                    '数值': [
                        df_final['最终成绩'].min(),
                        df_final['最终成绩'].quantile(0.25),
                        df_final['最终成绩'].median(),
                        df_final['最终成绩'].quantile(0.75),
                        df_final['最终成绩'].max(),
                        df_final['最终成绩'].std()
                    ]
                })
                st.dataframe(stats_df, use_container_width=True, hide_index=True)
            
            # 详细数据
            st.markdown("#### 📋 详细成绩单")
            
            # 搜索和筛选
            col1, col2 = st.columns([2, 1])
            with col1:
                search_term = st.text_input("🔍 搜索学生姓名或学号", placeholder="输入关键词搜索...")
            with col2:
                sort_by = st.selectbox("排序方式", ['学号', '最终成绩', '姓名'], index=0)
            
            # 筛选数据
            if search_term:
                mask = df_final.apply(lambda row: row.astype(str).str.contains(search_term, case=False).any(), axis=1)
                df_display = df_final[mask]
            else:
                df_display = df_final
            
            df_display = df_display.sort_values(by=sort_by)
            
            # 显示数据表格
            st.dataframe(
                df_display,
                use_container_width=True,
                height=400,
                column_config={
                    "姓名": st.column_config.TextColumn("👤 姓名"),
                    "学号": st.column_config.TextColumn("🎓 学号"),
                    "最终成绩": st.column_config.ProgressColumn(
                        "📈 最终成绩",
                        help="学生最终成绩",
                        format="%.1f",
                        min_value=0,
                        max_value=100
                    ),
                    "备注": st.column_config.TextColumn("📝 备注")
                }
            )
            
            # 导出功能
            st.markdown("#### 📥 数据导出")
            
            cols = st.columns(3)
            
            with cols[0]:
                excel_file = create_download_excel(df_final)
                st.download_button(
                    label="📊 下载Excel",
                    data=excel_file,
                    file_name=f"成绩单_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    icon="📊"
                )
            
            with cols[1]:
                csv_data = df_final.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📝 下载CSV",
                    data=csv_data,
                    file_name=f"成绩单_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    icon="📝"
                )
            
            with cols[2]:
                report_content = f"""
                ===== 期末项目报告成绩统计报告 =====
                
                生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                总人数: {len(df_final)}
                提交人数: {len(df_final[df_final['最终成绩'] > 0])}
                缺交人数: {len(df_final[df_final['最终成绩'] == 0])}
                
                📊 成绩统计:
                • 平均分: {df_final['最终成绩'].mean():.1f}
                • 最高分: {df_final['最终成绩'].max():.1f}
                • 最低分: {df_final['最终成绩'].min():.1f}
                • 及格率: {len(df_final[df_final['最终成绩'] >= 60]) / len(df_final) * 100:.1f}%
                
                =================================
                """
                st.download_button(
                    label="📄 下载报告",
                    data=report_content,
                    file_name=f"成绩报告_{datetime.now().strftime('%Y%m%d')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                    icon="📄"
                )
        else:
            # 空状态设计
            st.markdown("""
            <div style="text-align: center; padding: 4rem; background: linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%); border-radius: 12px;">
                <div style="font-size: 4rem; margin-bottom: 1rem;">📊</div>
                <h3 style="color: #2c3e50; margin-bottom: 1rem;">等待数据导入</h3>
                <p style="color: #6c757d;">请先在「成绩计算」页面完成数据处理</p>
            </div>
            """, unsafe_allow_html=True)
    
    # --- 页脚 ---
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align: center; color: #6c757d; font-size: 0.9rem;">
            <p>🎓 <strong>期末项目报告 智能评分系统</strong> v2.0.0</p>
            <p>© 2024 高等教育技术研究中心 | 技术支持: Python全栈开发团队</p>
        </div>
        """, unsafe_allow_html=True)

# --- 运行应用 ---
if __name__ == "__main__":
    main()
