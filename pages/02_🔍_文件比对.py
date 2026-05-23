import streamlit as st
import pandas as pd
import io

# 页面配置
st.set_page_config(page_title="材料核查神器v3.0", page_icon="🧾")
st.title("🧾 材料收集核查小工具 v3.0")
st.markdown("### ✅ 专治：表头乱跑、列名乱写、文件名乱起")

# ==========================================
# 第一步：配置花名册 (核心升级！)
# ==========================================
st.header("① 上传花名册 Excel")

# 1. 先让用户选表头在哪一行 (解决报错的根源)
header_row_index = st.number_input(
    "🧐 请问：真正的列名（姓名、工号）在 Excel 的第几行？", 
    min_value=1, value=2, step=1, 
    help="如果在第2行，这里就填2。如果不确定，可以改这个数字试试，看下面的预览变没变。"
)

excel_file = st.file_uploader("拖入花名册.xlsx", type=["xlsx"])

name_list = [] # 初始化空名单

if excel_file:
    try:
        # 核心修正：根据用户指定的行数读取表头 (header = 行数 - 1)
        # 这里的 header 动态变化，绝对不会再报 list index out of range 了
        df = pd.read_excel(excel_file, header=header_row_index - 1, dtype=str)
        
        st.info("👀 数据预览（请确认表头是否正确）：")
        st.dataframe(df.head(3), use_container_width=True)
        
        # 2. 让用户自己选哪一列是名字 (不再自动瞎猜)
        compare_col = st.selectbox("👇 请选择包含‘人员姓名’的那一列：", df.columns)
        
        if compare_col:
            # 清洗数据
            name_list = df[compare_col].dropna().astype(str).str.strip().tolist()
            # 过滤掉 'nan' 和 'nan' 字符串
            name_list = [n for n in name_list if n.lower() != 'nan' and n != '']
            st.success(f"✅ 成功提取名单：共 {len(name_list)} 人")
            
    except Exception as e:
        st.error(f"读取 Excel 出错，请检查表头行数是否填对。错误信息：{e}")

# ==========================================
# 第二步：上传材料 (批量)
# ==========================================
st.divider()
st.header("② 批量上传收上来的文件")
upload_files = st.file_uploader(
    "把收到的几十个文件全选，拖进来！", 
    type=None, accept_multiple_files=True
)

file_name_list = [f.name for f in upload_files] if upload_files else []

# ==========================================
# 第三步：自动核对 & 下载
# ==========================================
if name_list and file_name_list:
    st.divider()
    st.subheader("📊 核对结果")
    
    submitted = []
    not_submitted = []
    duplicate = [] # 重复交的人

    # 核心比对逻辑
    for name in name_list:
        # 统计这个名字在所有文件名里出现了几次
        count = sum(name in fname for fname in file_name_list)
        
        if count == 0:
            not_submitted.append(name)
        elif count == 1:
            submitted.append(name)
        else:
            submitted.append(name)
            duplicate.append(name)
    
    # 展示结果
    col1, col2, col3 = st.columns(3)
    col1.metric("🟢 已交人数", len(submitted))
    col2.metric("🔴 未交人数", len(not_submitted))
    col3.metric("🟡 疑似重复", len(duplicate))

    # 详细名单展示
    tab1, tab2 = st.tabs(["🔴 抓未交人员", "🟡 抓重复提交"])
    with tab1:
        if not_submitted:
            st.error(f"以下 {len(not_submitted)} 人没交：")
            st.dataframe(pd.DataFrame({"姓名": not_submitted}), use_container_width=True)
        else:
            st.balloons()
            st.success("太棒了！所有人都交齐了！")
            
    with tab2:
        if duplicate:
            st.warning(f"以下 {len(duplicate)} 人可能交了多份文件：")
            st.write(duplicate)
        else:
            st.info("没有重复提交的情况。")

    # 生成下载报告
    out = io.BytesIO()
    pd.DataFrame({
        "未交名单": pd.Series(not_submitted),
        "已交名单": pd.Series(submitted),
        "重复名单": pd.Series(duplicate)
    }).to_excel(out, index=False)
    
    st.download_button(
        "📥 下载核对结果表格.xlsx", 
        data=out.getvalue(), 
        file_name="核对结果.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

elif not name_list and excel_file:
    st.info("👈 请先在上方选择正确的列名")