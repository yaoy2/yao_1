# yao_1 | 学院行政智能中枢

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_svg.svg)](https://yao-1.streamlit.app/)

**语言**：简体中文 | [English](README_EN.md)
**更新日志**：[中文](CHANGELOG_ZH-CN.md) | [English](CHANGELOG_EN.md)

> **“前方没有胜利，挺住意味一切。”**

这是一个面向高校二级学院日常工作的 Streamlit 工具箱，覆盖待办管理、材料处理、数据核对、课表查询、预算台账、微信归档、配色参考、灵感便签和录音转写整理等场景。项目优先服务真实行政、教学协调和知识管理流程，能本地处理的优先本地处理，能沉淀成稳定入口的尽量沉淀成按钮。

---

## 仓库结构

本仓库包含一个主应用和五个独立子项目。

- **主应用**：根目录的 Streamlit / YaoYao 工具箱，入口是 `hello.py` 和 `启动YaoYao工具箱.bat`。`pages/`、`utils/`、`scripts/`、`config/`、`assets/`、`tests/` 是这个主应用的组成部分，不是独立子项目。
- **Deepself**（[`Deepself/`](Deepself/README.md)）：已初始化、尚未实现的独立子项目。目标、功能范围和技术栈仍待确认。
- **众声室**（[`zhongshengshi/`](zhongshengshi/README.md)）：已暂停的独立 Next.js 多模型圆桌概念验证。2026-08-11 起不再主动开发或部署。
- **Grok Builder**（[`codex-grok-builder/`](codex-grok-builder/README.md)）：正在使用的独立 Codex 技能子项目，用于受控的 Codex 规划 / Grok 实施闭环。
- **GPT Planner · Luna Executor**（[`gpt-planner-luna-executor/`](gpt-planner-luna-executor/SKILL.md)）：独立 Codex 技能子项目，用于受控的 Sol / Luna / ChatGPT Web 协作流程。
- **115 AI Organizer**（[`115-ai-organizer/`](115-ai-organizer/README.md)）：独立的 115 网盘只读整理项目，拥有自己的应用包和测试入口。

---

## 当前入口

- **线上入口**：[yao-1.streamlit.app](https://yao-1.streamlit.app/)
- **仓库地址**：[github.com/yaoy2/yao_1](https://github.com/yaoy2/yao_1)
- **docker-monitor（M23）**：只读展示本机 Docker 常驻任务（GLM 促销雷达、AIHOT 增量、德亚显卡报价），均走同一条钉钉；线上页面不执行监控。
- **GPT Planner · Luna Executor（M22）**：只读说明 Sol 定向编排、Luna 本地执行与 ChatGPT 网页版规划/审查的受控协作方式。
- **Awesome Design MD（M21）**：只读浏览主库内置的 74 组品牌 `DESIGN.md` 设计规范；来源版本固定，线上与本地读取同一份资产。
- **Ding2026 文件中转发放系统（M20）**：以脱敏静态快照展示文件识别、人工分发、中转裁决、五条时间轴归档和撤销边界，不连接真实材料目录。
- **概念寓言馆（M19）**：把抽象概念改写为可检索、可重读的中文寓言，并保存概念定义与故事映射。
- **评分工作台使用说明（M18）**：说明M17操作流程、分数口径、文件位置、跨电脑状态和常见问题；忘记怎么操作时先看M18。
- **教学评分工作台（M17）**：持久化管理花名册、小组路演与报告原始分、个人贡献系数、各层调整、校验和审核工作簿导出。
- **旧版评分联动（M16）**：已由M17替代，保留红叉作为历史对照；首页仍按模块编号放在M17与M15之间，不再用于新任务。
- **待办清单**：第 14 个上锁工具板块。支持新增在上、从文本自动识别常见中文日期和时间、关键字搜索、完成后软归档，并用 `data/todo_items_backup.md` 做可同步恢复的硬备份。
- **LLM 余额管理**：第 13 个工具板块，集中查看各家 LLM 余额，并把每家登录账号和到期日标签保存到 `data/llm_budget_accounts.json`，当前包含 Gemini。
- **首页风格**：按“行政 / 教学 / 个人 / archived”切换的紧凑首页；模块入口和精选区均由 `hello.py` 的元数据生成。
- **导航排序**：模块编号与分区以 `hello.py` 为唯一来源，不依赖 `pages/` 文件名前缀或特殊插入规则。
- **库结构说明**：见 [`docs/repository-structure.md`](docs/repository-structure.md)，其中记录主应用、独立子项目、只读资产和本机生成目录的边界。

---

## 众声室 MVP

`zhongshengshi/` 是“众声室”的本地 Web MVP，用来先验证圆桌工具的核心链路，再决定是否适配进现有 Streamlit 工具箱。

当前已完成：

- 创建独立 Next.js + TypeScript + Tailwind CSS 子项目。
- 搭建单页页面结构：话题输入、席位池粘贴、席位选择、模型配置状态、席位分配、圆桌控制台占位。
- 支持粘贴 GPT 生成的席位池 JSON，并兼容常见中文/英文字段。
- 支持从候选席位中选择 4 到 6 个席位。
- 支持 DeepSeek、MiMo、Kimi 的 provider 配置读取；API Key 只从 `.env.local` / 服务端环境变量读取，不返回前端。
- 提供 OpenAI-compatible Chat Completions adapter 基础封装，后续可替换不兼容 provider。
- 实现自动席位分配：每个模型最多 2 个席位，并按 DeepSeek / MiMo / Kimi 的偏好关键词做初步匹配。
- 新增 `/api/roundtable/run`，支持原有结构化 opening / debate 流程，也支持页面当前默认使用的 `freechat` 自由讨论模式。
- 新增 prompt builder，根据席位名称、类型、核心关切、典型问题、应做/不应做、反驳对象、盲点、风格、例子偏好和自定义提示词生成模型提示。
- 新增 mock provider，用于本地验证和测试，不消耗真实 API；真实 provider 仍走服务端环境变量和 OpenAI-compatible Chat Completions 调用。
- 前端可按消息流展示运行状态、provider 调用状态、错误日志和完整 transcript；单个 provider 或席位失败不会中断整场圆桌。
- 页面顶部新增“项目说明书 / 使用指南”板块，集中说明最快跑通方式、真实模型配置、席位池格式、结果解读和当前边界。
- 支持 compact seat pool：只需要 `seats` 数组，每个席位至少包含 `seat_name`、`type`、`core_concern`、`typical_questions`、`must_do`、`must_not_do`、`speaking_style`。
- 新增“载入示例席位池”按钮，内置 `low_relevance_competition` 示例，载入后自动填入主题和 6 个短席位；解析后页面只展示席位卡片，长 JSON 默认收起。
- 新增浏览器本地草稿恢复：自动暂存话题、席位池、已解析席位、已选席位、席位分配、mock 模式和 JSON 编辑区状态，页面刷新或开发服务 Fast Refresh 后不需要从头重填。
- 重写 mock provider 输出和真实模型 prompt 质量约束：mock 模式只作为流程测试，不再输出“链路连通”类废话；真实模型 prompt 明确禁止复述题目、泛泛“综合看待”和无对象表态。
- 新增 `freechat` 圆桌模式：页面现在默认让席位用更短的聊天式发言接话、打断、反驳或补充，而不是按席位顺序写一组可预见的小作文。
- 将 transcript 改为“圆桌聊天室”：每条发言按时间顺序以社交聊天气泡展示，带角色头像和 `席位名 - 模型名` 发言人标签。

本地运行：

```powershell
cd zhongshengshi
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

页面默认勾选 “使用 mock provider 本地验证”。mock 只用于检查流程是否连通，不代表真实讨论质量。如果要调用真实模型并观察圆桌发言质量，请取消该选项，并在 `.env.local` 中至少配置 2 个 provider。

`.env.local` 示例字段：

```text
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=
DEEPSEEK_MODEL=

MIMO_API_KEY=
MIMO_BASE_URL=
MIMO_MODEL=

KIMI_API_KEY=
KIMI_BASE_URL=
KIMI_MODEL=
```

兼容说明：旧的 `MINIMAX_API_KEY` / `MINIMAX_BASE_URL` / `MINIMAX_MODEL` 仍会被当作 Kimi fallback 读取，但建议改成 `KIMI_*`。

当前限制：

- 页面当前默认是轻量 `freechat` 消息流；原 opening / debate 结构化流程仍保留在 engine 中，方便测试和后续对照。
- 说话人选择目前仍是规则驱动，还不是真正由模型主持人自主控场；真正的自主接话、发言价值评估、缺席视角检测、总结和持久化仍待后续实现。
- 真实 provider 默认按 OpenAI-compatible Chat Completions 调用；如果某家 API 不兼容，需要继续扩展 adapter。

项目已于 2026-08-11 暂停开发。源码、测试和概念验证结果继续保留；除非以后出现明确的新需求，否则不再增加主持模型、数据库、总结器或部署功能。完整项目说明见 [`zhongshengshi/README.md`](zhongshengshi/README.md)。

---

## 二十二个现存工具模块

模块编号记录上线顺序，因此当前编号不再连续。首页入口以 `hello.py` 的元数据和分区为准。带红色叉号的模块仅保留历史对照，不再用于新任务。

### 1. 📝 报告评分系统 (Grading System)
- **场景**：期末大作业、实验报告批量打分。
- **功能**：自动提取 Word/PDF 文字及图片数量，配合 AI 实现人机协同评分与成绩合成。

### 2. 🔍 文件比对神器 (File Comparator)
- **场景**：核对学生提交的文件名是否符合规范，查找谁没交作业。
- **功能**：通过花名册与文件夹实时比对，一键找出漏交、错交和命名异常，支持动态表头识别。

### 3. ✅ 名单核对小工具 (Roster Checker)
- **场景**：行政汇总表与标准花名册的精准对齐。
- **功能**：支持自定义 Excel 数据范围（如 C2:C52），快速找出两份名单中的重合与差异项。

### 4. 🌾 Word 收割机 (Word Reaper)
- **场景**：毕业生登记表、政审表等复杂表格数据提取。
- **功能**：工业级批量处理，自动拆分本科/硕博数据，智能识别合并单元格，一键转为 Excel 汇总表。

### 5. 🧰 万能合并机 (Universal Merger)
- **场景**：多文档文字汇总或多表格归档。
- **功能**：
    - **文档类**：将几十个 Word/PDF 文字合并为 1 个 Word（含”破甲”逻辑，解除 PDF 复制限制）。
    - **表格类**：将多个 Excel 文件合并为 1 个文件中的多个 Sheet。

### 6. 📚 课表查询系统 (Schedule Browser)
- **场景**：学院内部课表快速检索。
- **功能**：基于 JSON 缓存的课表数据，支持按教师姓名、系部、星期等多维度查询，自动解析复杂的周次与节次信息。
- **数据更新**：将新 Excel 放入 `data/` 目录后刷新页面，自动重新解析并更新缓存。

### 7. 📥 微信归档工具 (WeChat Archiver)
- **场景**：优质公众号教学案例、竞赛信息本地永久保存。
- **功能**：
    - **四路线归档**：支持 `归档raw`、`归档学院`、`归档课题`、`归档竞赛` 四类入口。
    - **Playwright 驱动**：模拟真实浏览器，抓取动态渲染的微信公众号正文。
    - **图片本地化**：绕过防盗链，图片自动下载至本地 `assets` 目录。
    - **本地文件归档**：课题/竞赛文件可复制到对应 GoogleDrive 目录，IMA 上传部分交给 WorkBuddy 执行。
    - **固定端口**：本地归档窗口固定使用 `http://localhost:8502`，避免和主工具箱 `8501` 混用。
    - *注：该模块为本地脚本，线上版仅作功能展示。*

### 8. 💰 预算速记台账 (Budget Tracker)
- **场景**：学院年度预算支出的快速记录与动态监控。
- **功能**：
    - **快速录入**：选类别、选单位、填写支出人、写明细、填金额，一键保存。
    - **动态看板**：实时展示分类预算余额、分类别单位支出统计。
    - **状态管理**：每笔费用支持”未报销/已报销/作废”状态切换，看板自动更新。
    - **交叉分析**：类别 × 单位交叉透视表，一目了然各部门在各类预算下的支出分布。
    - **数据导出**：支持导出全部流水或筛选结果为 Excel。
    - **硬备份**：保存、修改、恢复后自动同步 `data/budget_ledger_backup.md` 和 `data/budget_ledger_backup.xlsx`。
    - **特殊类别**：支持 `年终奖留存`，按实际发生支出累计，不参与固定预算余额计算。

### 9. 🎨 配色方案预览 (Color Palette Preview)
- **场景**：PPT、海报、品牌视觉的配色参考。
- **功能**：从本地 Markdown 数据文件读取配色方案，以“氛围展示 + 色彩角色 + PPT 应用预览”的方式呈现，直观展示主色、辅助色、背景色、色号、颜色名和推荐用途。支持多方案切换浏览。
- **数据**：内置多组商务风、多巴胺和传统/品牌视觉配色方案，可通过编辑 `data/color_palettes.md` 自由扩展；配色库是灵感便签卡片配色的实时来源。

### 10. 🧾 灵感便签盒 (Web Memo)
- **场景**：临时灵感、摘录、待办、写作素材、工具想法的快速收集。
- **功能**：
    - **快速记录**：输入内容后自动关联当天日期。
    - **标签管理**：支持选择已有标签，也支持新增标签。
    - **自动分类**：按内容规则初步归为摘录、观点、待办、写作素材、工作记录、工具想法、金句等类别。
    - **瀑布式列表**：备忘卡片按三列展示，最新记录在前；卡片正面采用海报式短摘录，全文收进展开区，避免长文本破坏配色效果。
    - **卡片操作**：每张便签支持上移、下移、编辑和隐藏；操作区采用紧凑符号按钮，悬停显示完整含义，移动只调整显示顺序，页面仍按三列瀑布流展示。
    - **安全删除**：隐藏不会从备份中物理删除记录，默认列表不显示，但 GitHub 备份仍保留，避免误删后彻底丢失。
    - **动态配色**：卡片展示时从当前 `data/color_palettes.md` 中取色，不再依赖新增便签时写入的旧色卡快照；底色始终取色卡中饱和度最低的颜色，避免高饱和色铺满背景；标题和点缀使用其余两个颜色，正文颜色根据底色明度自适应。便签展示池会跳过「樱桃苏打」「橘子派对」这类大面积显示容易刺眼的方案，但配色方案库本身仍保留原始色号。
    - **GitHub 备份**：保存后通过 `GITHUB_BACKUP_TOKEN` 同步 `data/web_memos_backup.md`；页面启动时会从 GitHub 备份合并补回记录，并阻止空备份覆盖远端已有内容。
    - **导出**：支持 Markdown 和 PDF 导出。

### 11. 🎙️ Recorder_笔记 (Recorder Notes)
- **场景**：钉钉录音转写、座谈记录、会议讨论、培训讲座等碎片化口语材料整理。
- **功能**：
    - **每日扫描**：配合 Windows 任务计划，每天 19:00 扫描 `C:\Users\Yao\Downloads` 文件夹中前一天 19:00 到当天 19:00 新建的 `export_*.docx`、`dt*.docx` 和文件名包含“原文”的 `.docx`。
    - **原文保留**：自动提取 Word 原文，保存文件名、路径、创建时间、修改时间和处理状态。
    - **AI 整理**：调用 DeepSeek 将口语化转写整理为可归档、可复盘、可继续写材料的整理稿，不套固定纪要模板。
    - **备注标记**：支持手动填写备注，用于记录用途、处理意见和后续动作。
    - **访问上锁**：复用预算速记台账同一套密码，读取 `budget_password` / `[budget].password` 或本机 `BUDGET_PASSWORD`。
    - **迁移说明**：L 电脑运行配置见 `docs/ding_minutes_L_setup.md`。

### 13. 💰 LLM 余额管理 (LLM Budget Tracker)
- **场景**：集中查看 DeepSeek、Kimi、MiMo、ChatGPT、Gemini 等 LLM API / 订阅余额，避免忘记是哪一个账号在扣费。
- **功能**：
    - **自动余额**：从 Streamlit Secrets 读取 API Key，查询支持自动查询的厂商余额。
    - **手动余额**：对暂未接入余额 API 的厂商保留手动录入入口。
    - **登录账号标签**：每个厂商卡片下方可填写邮箱或手机号，账号输入框和保存按钮在同一行，减少纵向空间浪费。
    - **到期日标签**：账号下方可手动填写 `expiration date: yy_mm_dd`，和账号一起保存到 `data/llm_budget_accounts.json`。
    - **GitHub 备份**：配置 `GITHUB_BACKUP_TOKEN` 后，保存账号会同步到 GitHub，避免刷新仓库或重新部署后丢失。

### 14. ✓ 待办清单 (Todo List)
- **场景**：记录日常待办、截止日期、完成状态和归档记录。
- **功能**：支持中文日期时间识别、搜索、软归档、本地SQLite存储及Markdown恢复备份。

### 15. ✉️ 邮件通知编辑器 (Email Notice Editor)
- **场景**：把通知原文整理成结构清楚、可预览和可导出的邮件页面。
- **功能**：识别标题、编号、正文、落款和日期，支持在线预览及HTML导出。

### 16. 🧮 旧版报告评分与成绩联动（已替代）
- **状态**：已由M17替代，仅保留历史对照；首页显示红叉并固定在第二页。
- **说明**：不要再在M16建立正式成绩任务。

### 17. 📘 教学评分工作台 (Teaching Grade Workbench)
- **场景**：处理花名册、小组路演、三级项目报告、个人贡献系数和最终成绩调整。
- **原则**：小组原始分、个人折算分和统一/小组/个人调整分开保存，调整不会改写原始路演分和报告分。
- **数据状态**：当前任务保存在本机 `data/grade_workbench/`；跨电脑评分数据同步尚未启用。

### 18. 📖 评分工作台使用说明 (Grade Workbench Guide)
- **场景**：长期未使用后快速确认M18、M17、M16分别是什么，以及完整操作顺序。
- **功能**：集中展示六步流程、分数定义、文件位置、跨电脑注意事项和常见问题。

### 19. 📚 概念寓言馆 (Concept Fable Gallery)
- **场景**：把难记的抽象概念转成可检索、可重读的中文寓言。
- **功能**：保存领域定义、寓言正文和概念到故事元素的对应关系。

### 20. 🗂️ Ding2026 文件中转发放系统 (Ding2026 File Governance)
- **场景**：展示学院行政材料如何经过识别、人工分发、中转裁决并进入不同时间口径的档案。
- **边界**：页面只读取仓库内的脱敏聚合快照，不访问真实文件、数据库、Google Drive 或独立 Ding2026 运行库，也不提供操作按钮。

### 21. 🧩 Awesome Design MD
- **场景**：为页面设计和 AI 界面生成查找品牌设计系统参考。
- **功能**：只读筛选和浏览 74 组本地 `DESIGN.md`；资产固定在主库中，部署与本地使用同一来源。

### 22. 🤝 GPT Planner · Luna Executor
- **场景**：说明复杂本地任务如何在受控边界内分配给 Sol、Luna 与 ChatGPT 网页版。
- **边界**：页面只展示角色、Packet 和审查流程，不创建代理、不调用模型、不控制浏览器，也不修改项目。

### 23. 📡 docker-monitor
- **场景**：在个人类目下一页平铺三个 Docker 任务：GLM 促销雷达、AIHOT 增量、德亚显卡报价。
- **边界**：页面不联网、不启容器、不读取本机状态、不发钉钉；真实监控保留在独立仓库 docker-monitor。侧栏不加新入口。

---

## 🚀 快速开始

### 线上体验
直接访问 [Streamlit Cloud 演示地址](https://yao-1.streamlit.app/) 即可使用大部分工具（无需安装）。

### 本地部署 (推荐)
如需使用 **微信归档** 或处理**大批量私密数据**，建议本地运行：

1. **克隆仓库**
   ```bash
   git clone https://github.com/yaoy2/yao_1.git
   cd yao_1
   ```

2. **首次安装**

   双击根目录的 `首次安装.bat`。脚本会创建项目自己的 `.venv` 环境，并安装运行依赖和测试依赖。

3. **启动工具箱**

   双击 `启动YaoYao工具箱.bat`。

4. **检查项目是否正常**

   双击 `运行测试.bat`。显示“全部测试通过”即可；如果失败，保留窗口中的错误信息交给Codex排查。

### Recorder_笔记本地配置
`Recorder_笔记` 是第 11 个板块，适合放在固定电脑上本地运行。继续配置时按下面顺序处理：

线上 Streamlit App 不读取本机 PowerShell 环境变量；线上使用时，需要在 Streamlit Cloud 的 Secrets 中配置 `DEEPSEEK_API_KEY`。

1. **确认项目位置**
   ```text
   E:\github\yao_1
   ```

2. **安装依赖**
   ```powershell
   python -m pip install -r requirements.txt
   ```

3. **配置本机环境变量**

   - `DEEPSEEK_API_KEY`：用于调用 DeepSeek 生成整理稿，不能写入代码、配置文件或 GitHub。
   - `BUDGET_PASSWORD`：仅本机没有 Streamlit secrets 时才需要配置，值应与预算速记台账密码相同；线上 Streamlit App 会直接复用 secrets 中的统一密码。

   示例命令：
   ```powershell
   [Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "你的真实key", "User")
   # 仅本机运行且没有 Streamlit secrets 时才需要：
   [Environment]::SetEnvironmentVariable("BUDGET_PASSWORD", "你的预算台账密码", "User")
   ```

   设置后重新打开 PowerShell 或重启电脑，让环境变量生效。

   线上 Streamlit Cloud 的 Secrets 示例：
   ```toml
   DEEPSEEK_API_KEY = "你的真实key"
   ```

4. **确认扫描路径**

   扫描路径在 `config/ding_minutes.ini` 中配置。默认示例为：

   ```ini
   watch_dir = C:\Users\Yao\Downloads
   daily_run_time = 19:00
   model = deepseek-v4-pro
   ```

   如果钉钉转写导出的 Word 文件不在这个目录，只改 `watch_dir`，不要把 API key 写进 ini 文件。

5. **手动试运行一次**
   ```powershell
   python scripts\scan_ding_minutes.py
   ```

   如果提示文件夹不存在，检查 `watch_dir`。如果提示缺少 `DEEPSEEK_API_KEY`，重新打开 PowerShell 后再试。

6. **设置每天 19:00 自动扫描**

   Windows 任务计划程序里新建基本任务：

   - 名称：`Ding Minutes Scan`
   - 触发器：每天 19:00
   - 操作：启动程序
   - 程序或脚本：`python`
   - 添加参数：
     ```text
     scripts\scan_ding_minutes.py
     ```
   - 起始于：
     ```text
     E:\github\yao_1
     ```

L 电脑迁移和更详细的任务计划设置见 [docs/ding_minutes_L_setup.md](docs/ding_minutes_L_setup.md)。

---

## 🛡️ 安全与隐私
- **隐私第一**：文件处理类工具优先在内存中完成；预算台账和灵感便签盒会按功能需要写入本地数据与备份文件。
- **本地优先**：敏感工具（如微信归档）强制要求本地运行，确保数据不出本地网络。
- **密钥不入库**：DeepSeek API key 只从本机 `DEEPSEEK_API_KEY` 环境变量读取，不写入 GitHub、日志、数据库或配置文件。
- **上锁板块**：预算速记台账和 `Recorder_笔记` 共用同一套访问密码，建议只配置在 Streamlit secrets 或本机 `BUDGET_PASSWORD`。
- **备份说明**：预算台账和灵感便签盒都会在当前运行环境内同步本地备份文件，并可通过 `GITHUB_BACKUP_TOKEN` 写回 GitHub 备份账本；灵感便签会先合并远端备份再写回，避免空环境把远端已有便签覆盖掉。重要数据仍建议定期导出，作为 GitHub 备份之外的人工兜底。

## 📄 使用许可
仓库当前尚未添加独立的 `LICENSE` 文件。若后续需要正式对外分发或允许他人复用，再单独确定并补充开源协议。

## 📅 更新日志
详情请参阅 [CHANGELOG_ZH-CN.md](CHANGELOG_ZH-CN.md)；英文版见 [CHANGELOG_EN.md](CHANGELOG_EN.md)。

---
**由 [姚遥] 倾力打造，欢迎提出宝贵意见**
*如果你觉得这个项目有用，欢迎点击右上角的 ⭐ Star！*
