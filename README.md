# thebeginning 🎓 | 学院行政与教学科研效率工具箱

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_svg.svg)](https://your-streamlit-app-link.streamlit.app)
> **“把繁琐交给代码，把时间还给教育。”**

这是一个专为**高校教师、辅导员及行政人员**打造的综合性效率工具箱。它针对高校工作中常见的材料审核、成绩汇总、文档合并、课表查询等痛点，提供了一套基于 Python 和 Streamlit 的自动化解决方案。

---

## 🛠️ 七大核心模块

### 1. 📝 报告评分系统 (Grading System)
- **场景**：期末大作业、实验报告批量打分。
- **功能**：自动提取 Word/PDF 文字及图片数量，配合 AI (DeepSeek/GPT) 实现“人机协同”批量评分与成绩合成。

### 2. 🔍 文件比对神器 (File Comparator)
- **场景**：核对学生提交的文件名是否符合规范，查找谁没交作业。
- **功能**：通过花名册与文件夹实时比对，一键揪出“漏交者”，支持动态表头识别。

### 3. ✅ 名单核对小工具 (Roster Checker)
- **场景**：行政汇总表与标准花名册的精准对齐。
- **功能**：支持自定义 Excel 数据范围（如 C2:C52），快速找出两份名单中的重合与差异项。

### 4. 🌾 Word 收割机 (Word Reaper)
- **场景**：毕业生登记表、政审表等复杂表格数据提取。
- **功能**：工业级批量处理，自动拆分本科/硕博数据，智能识别合并单元格，一键转为 Excel 汇总表。

### 5. 🧰 万能合并机 (Universal Merger)
- **场景**：多文档文字汇总或多表格归档。
- **功能**：
    - **文档类**：将几十个 Word/PDF 文字合并为 1 个 Word（含“破甲”逻辑，解除 PDF 复制限制）。
    - **表格类**：将多个 Excel 文件合并为 1 个文件中的多个 Sheet。

### 6. 📚 课表查询系统 (Schedule Browser)
- **场景**：学院内部课表快速检索。
- **功能**：基于原始 Excel 课表，支持按教师姓名、系部、星期等多维度查询，自动解析复杂的周次与节次信息。

### 7. 📥 微信归档工具 (WeChat Archiver)
- **场景**：优质公众号教学案例、竞赛信息本地永久保存。
- **功能**：
    - **Playwright 驱动**：模拟真实浏览器，抓取动态渲染的正文。
    - **图片本地化**：绕过防盗链，图片自动下载至本地 `assets` 目录。
    - **Obsidian 联动**：自动生成带 Front Matter 的 Markdown，完美接入个人知识库。
    - *注：该模块为本地脚本，线上版仅作功能展示。*

---

## 🚀 快速开始

### 线上体验
直接访问 [Streamlit Cloud 演示地址](https://your-streamlit-app-link.streamlit.app) 即可使用大部分工具（无需安装）。

### 本地部署 (推荐)
如需使用 **微信归档** 或处理**大批量私密数据**，建议本地运行：

1. **克隆仓库**
   ```bash
   git clone https://github.com/your-username/thebeginning.git
   cd thebeginning
   ```

2. **创建虚拟环境**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **启动工具箱**
   ```bash
   streamlit run 🏠_Home.py
   ```

---

## 🛡️ 安全与隐私
- **隐私第一**：所有处理逻辑均在内存中完成，上传的文件不会被持久化存储。
- **本地优先**：敏感工具（如微信归档）强制要求本地运行，确保数据不出本地网络。

## 📄 开源协议
本项目采用 [MIT License](LICENSE) 开源。

---
**由 [您的名字/团队名] 倾力打造**  
*如果你觉得这个项目有用，欢迎点击右上角的 ⭐ Star！*
