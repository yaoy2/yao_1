import streamlit as st
import pandas as pd
from utils.ui_theme import render_home_link

# 🎨 1. 设置网页标题和布局
st.set_page_config(page_title="行政核对神器", page_icon="📝")
render_home_link()
st.title("📝 学院行政核对神器")
st.markdown("### 专治各种漏交、重交、名单不一致")

# --- 核心工具函数 (复用昨天的逻辑) ---
def read_excel_range(uploaded_file, cell_range):
    """
    读取上传的Excel文件中的指定范围
    """
    try:
        # 解析 "C2:C15" 这种格式
        col_letter = cell_range.split(':')[0][0].upper() # 确保大写
        start_row = int(cell_range.split(':')[0][1:])
        end_row = int(cell_range.split(':')[1][1:])
        
        row_count = end_row - start_row + 1
        
        # 读取数据 (Streamlit上传的文件可以直接读)
        df = pd.read_excel(uploaded_file, usecols=col_letter, skiprows=start_row-1, nrows=row_count, header=None)
        
        # 清洗数据
        clean_list = df.iloc[:, 0].dropna().astype(str).str.strip().tolist()
        clean_list = [x for x in clean_list if x.lower() != 'nan' and x != '']
        
        return set(clean_list)
    except Exception as e:
        st.error(f"❌ 读取出错：{e}")
        return None

# --- 🎨 2. 界面布局：左右两栏 ---
col1, col2 = st.columns(2)

with col1:
    st.info("📂 **文件 A (标准名单)**")
    file_a = st.file_uploader("拖入花名册 Excel", type=['xlsx'], key="a")
    range_a = st.text_input("数据范围 (如 C2:C52)", value="C2:C52", key="ra")

with col2:
    st.warning("📂 **文件 B (待核对文件)**")
    file_b = st.file_uploader("拖入汇总表 Excel", type=['xlsx'], key="b")
    range_b = st.text_input("数据范围 (如 D2:D72)", value="D2:D72", key="rb")

# --- 🚀 3. 核心触发逻辑 ---
if st.button("🚀 开始一键核对", type="primary"):
    # 检查用户有没有偷懒 (没传文件)
    if not file_a or not file_b:
        st.error("请先把两个文件都拖进来！")
    else:
        # 读取数据
        names_a = read_excel_range(file_a, range_a)
        names_b = read_excel_range(file_b, range_b)

        if names_a is not None and names_b is not None:
            # 开始集合运算
            missing = names_a - names_b # A有B没有
            extra = names_b - names_a   # B有A没有
            common = names_a & names_b  # 都有

            st.divider() # 画一条分割线

            # --- 📊 4. 展示结果 ---
            # 统计数据
            m1, m2, m3 = st.columns(3)
            m1.metric("标准名单人数", len(names_a))
            m2.metric("实际匹配人数", len(common))
            m3.metric("未匹配人数", len(missing) + len(extra))

            # 详细名单 (用 Tabs 标签页展示，更高级)
            tab1, tab2, tab3 = st.tabs(["🔴 漏交/缺失名单", "🟡 多余/新增名单", "🟢 匹配成功名单"])

            with tab1:
                if missing:
                    st.error(f"发现 {len(missing)} 人未在表B中找到：")
                    st.dataframe(pd.DataFrame({"姓名": list(missing)}), use_container_width=True)
                else:
                    st.success("完美！所有人都交了！")

            with tab2:
                if extra:
                    st.warning(f"发现 {len(extra)} 人是新增的 (不在花名册里)：")
                    st.dataframe(pd.DataFrame({"姓名": list(extra)}), use_container_width=True)
                else:
                    st.success("没有多余人员。")
            
            with tab3:
                st.write(f"共有 {len(common)} 人匹配成功。")
                with st.expander("查看详情"):
                    st.write(list(common))
