# yao_1 | 学院行政智能中枢

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_svg.svg)](https://whatsup.streamlit.app/)

**语言**：简体中文 | [English](README_EN.md)
**更新日志**：[中文](CHANGELOG_ZH-CN.md) | [English](CHANGELOG_EN.md)

> 前方没有胜利，挺住意味一切。

面向高校二级学院日常工作的 Streamlit 工具箱，集中提供行政事务、教学评分、知识记录和项目展示入口。本仓库同时保留五个独立子项目，它们的运行方式与数据边界分别由各自文档说明。

## 从哪里开始

- **使用工具箱**：[线上入口](https://whatsup.streamlit.app/)；首页按“行政 / 教学 / 个人 / archived”切换。
- **第一次处理成绩**：先看 M18 使用说明，再到 M17 建立正式任务。
- **归档微信文章或本地文件**：使用本机的 `启动微信归档窗口.bat`，先读[微信归档指南](docs/guides/wechat-archiver.md)。
- **配置 Recorder 扫描**：先读[本机配置与迁移指南](docs/guides/ding_minutes_L_setup.md)，确认路径后再运行。
- **了解目录与维护边界**：看[文档索引](docs/README.md)和[仓库结构](docs/repository-structure.md)。
- **查看源码**：[GitHub 仓库](https://github.com/yaoy2/yao_1)。

## 本地安装、启动与检查

需要 Windows、可运行的 Python 3，以及首次安装时的网络连接。依赖以 [requirements.txt](requirements.txt) 为准；主应用使用 Streamlit，Excel/Word/PDF 处理库负责材料转换，Playwright 负责本机微信文章抓取。

1. 获取仓库：
   ```powershell
   git clone https://github.com/yaoy2/yao_1.git
   cd yao_1
   ```
2. 双击 `首次安装.bat`，在仓库内创建 `.venv` 并安装运行和测试依赖。
3. 双击 `启动YaoYao工具箱.bat`，启动主应用。
4. 双击 `运行测试.bat`，检查主应用。若失败，保留错误信息，先判断是依赖缺失还是具体功能检查失败。

主应用也可在仓库根目录单独检查：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

主应用检查范围是 `tests/`；独立子项目应按自身文档运行测试，不在根目录用无范围的 pytest 混合收集。开发验证采用测试、语法和纯函数检查，按仓库规则不为预览启动本地 Streamlit 服务。

微信归档窗口固定使用 `http://localhost:8502`，与主工具箱分开。抓取使用本机 Microsoft Edge，不需要额外安装 Playwright Chromium。这个窗口实际执行归档；工具箱中的 M07 是功能说明入口。

## 二十二个现存工具模块

编号记录上线顺序，因此不连续。当前共 **22 个入口：行政 6、教学 2、个人 7、archived 7**；其中 15 个在当前业务分区，7 个仅作历史对照。分区和页面入口以 [hello.py](hello.py) 的元数据为准，没有“固定第二页”或精选区规则。

### 行政

| 编号 | 模块 | 主要用途与边界 |
| --- | --- | --- |
| M20 | Ding2026 文件中转发放系统 | 只读展示脱敏聚合状态、人工分发、中转裁决和五条归档时间轴；不连接真实材料目录。 |
| M15 | 邮件通知编辑器 | 识别通知结构、排版预览和导出；[独立 HTML 编辑器](assets/email_notice_editor.html)可下载后离线使用。 |
| M14 | 待办清单 | 自动识别中文截止日期与时间、搜索、软归档，以及本地备份与 GitHub 同步；需要访问密码。 |
| M11 | Recorder_笔记 | 登记 Word 转写、保留原文、调用 DeepSeek 整理和记录备注；需要访问密码，定时扫描由本机任务负责。 |
| M08 | 预算速记台账 | 记录支出与报销状态、查看分类余额、导出流水和保存恢复备份；需要访问密码。 |
| M06 | 课表查询 | 基于课表 Excel 与 JSON 缓存，按教师、系部、星期等查询教学安排。 |

### 教学

| 编号 | 模块 | 主要用途与边界 |
| --- | --- | --- |
| M18 | 评分工作台使用说明 | 解释操作顺序、评分口径、数据位置、跨电脑状态和常见问题。 |
| M17 | 教学评分工作台 | 管理花名册、小组路演与报告原始分、个人系数和各层调整，校验后导出审核工作簿；调整不会改写原始小组分。 |

### 个人

| 编号 | 模块 | 主要用途与边界 |
| --- | --- | --- |
| M23 | docker-monitor | 以 2×2 布局只读展示四个 Docker 任务：TrendRadar、GLM 促销雷达、AIHOT 增量、德亚显卡报价。 |
| M22 | Planner-Executor | 按任务说明当前 Agent、GPT / Luna 与 Codex / Grok 两条路线的选用、优化前后对照和实测边界；页面只读，不调用模型或执行任务。 |
| M21 | Awesome Design MD | 搜索、选择和浏览 74 组品牌设计规范；本地与线上使用同一份固定来源资产。 |
| M19 | 概念寓言馆 | 检索和重读中文寓言、概念定义与故事映射；条目保存在 `data/concept_fables.json`，页面只读。 |
| M10 | 灵感便签盒 | 保存灵感、摘录与素材，支持标签、色卡、排序、隐藏、Markdown/PDF 导出及 GitHub 备份合并。 |
| M09 | 配色方案预览 | 浏览 `data/color_palettes.md` 中的配色和应用示例；该文件也是便签配色来源。 |
| M07 | 微信归档 | 展示 raw / 学院 / 课题 / 竞赛四类路线；实际抓取和本地复制走专用窗口，IMA 上传由独立流程完成。 |

M20、M22、M23 是说明或展示页，打开页面不会启动对应外部项目。M23 对应的 TrendRadar 仍是独立本机容器，其余三个任务位于独立私有 [docker-monitor 仓库](https://github.com/yaoy2/docker-monitor)，共用同一条钉钉。德亚报价说明采用“欧元标价 + 人民币估算”，公式为 `EUR × 1.13 × 7.79 + 150`；页面不联网、不启容器、不读取本机状态或实时价格，也不发钉钉。

### archived：历史入口

| 编号 | 模块 | 状态 |
| --- | --- | --- |
| M16 | 旧版报告评分与成绩联动 | 已由 M17 替代，不再建立正式评分任务。 |
| M13 | LLM 余额管理 | 已归入历史区，保留余额与账号管理实现供对照。 |
| M05 | 万能合并机 | 已停用，保留旧实现。 |
| M04 | Word 收割机 | 已停用，保留旧实现。 |
| M03 | 名单核对 | 已停用，保留旧实现。 |
| M02 | 文件比对 | 已停用，保留旧实现。 |
| M01 | 报告评分 | 旧提示词评分流程已弃用。 |

历史入口保留源代码和红叉状态，不因代码仍在就视为当前推荐流程。M12 已移除；早期股票功能的 M19 历史日志与现在的“概念寓言馆”不是同一项目。

## 五个独立子项目

| 子项目 | 当前用途与状态 | 详细入口 |
| --- | --- | --- |
| Deepself | 已实现个人表达研究、写作 Skill 和独立回复工具；朋友圈原文、截图与私密报告留在本机。 | [项目说明](Deepself/README.md)；`Deepself/启动Deepself对话框.bat` |
| 众声室 | Next.js 多模型圆桌概念验证，2026-08-11 起暂停开发；保留源码和验证记录。 | [项目说明](zhongshengshi/README.md) |
| Codex → Grok Builder | 按任务规模交接的 Grok Build 实施技能；具体方案、范围和测试审批保留。 | [中文说明](codex-grok-builder/README_ZH-CN.md) |
| GPT Planner · Luna Executor | 按任务需要组织 GPT 规划与 Luna 执行；尊重明确模型、网页和只规划要求。 | [中文说明](gpt-planner-luna-executor/README_ZH-CN.md) |
| 115 AI Organizer | 只读扫描、分类报告、人工审核；批准并核对操作清单与确认码后，才执行建目录、改名和移动。没有删除接口。 | [项目说明与最新交接](115-ai-organizer/README.md) |

这些子项目有自己的启动、依赖和权限要求。克隆本仓库不会自动启动它们，也不会启用监控、归档或网盘整理。

[个人技能集合](personal-skills/README_ZH-CN.md)另保存 PPT 制作、小红书评论真人图片和存储分析技能，不是新增独立运行项目。跨电脑使用时，将所需完整技能复制或安装到各自实际的 `CODEX_HOME/skills/`；仓库拉取不会自动更新安装副本，不依赖固定盘符或 Junction。

技能协作以合格任务总成本为依据：开放选型的小改直接完成，执行量大且边界明确时才委派，强模型聚焦关键不确定性。总 token、高价模型用量、额度和费用分别记录，缺少对照不宣称降本。参见[9 月 5 日评估与 9 月 6 日发布记录](docs/history/2026-09-05-skill-cost-optimization.md)。

## 数据保存、恢复与跨电脑使用

线上 Streamlit 与本机是两个运行环境。线上页面不能读取这台电脑的路径或环境变量；`git pull` 只能取得已提交文件，不会恢复被忽略的数据库、密钥或私密资料。

| 功能 | 主要保存位置 | 恢复与迁移要点 |
| --- | --- | --- |
| M08 预算 | `data/budget.db`；`budget_ledger_backup.md/.xlsx` | 空数据库可从本地 Markdown 备份恢复；配置 GitHub 同步后可把 Markdown 写回远端。 |
| M10 便签 | `data/web_memos.db`；`web_memos_backup.md` | 可从备份恢复；配置同步后会合并远端记录，并保护远端已有内容。 |
| M14 待办 | `data/todos.db`；`todo_items_backup.md` | 可从备份恢复；配置同步后合并远端记录，完成项以软归档保留。 |
| M11 Recorder | `data/ding_minutes.db`；`ding_minutes_cloud.json` | 本机扫描保存原文和整理稿；线上读取云端导出，备注可同步；迁移前看专项指南。 |
| M17 评分 | `data/grade_workbench/tasks/<任务ID>/task.db` 及任务附件 | 不自动同步到 GitHub；迁移需保留完整任务目录，审核工作簿另行导出。 |

`data/` 是业务资料，不是缓存目录。GitHub 远端备份是动态数据的汇合点，本地修改这些备份前须先同步远端；遇到冲突先合并，不以旧文件或空文件覆盖。重要材料仍应定期导出，并另做受控备份。

## 密钥、外部服务与本地边界

- **访问密码**：M08、M11、M14 复用 Streamlit Secrets 中的 `budget_password` / `[budget].password`，本机也支持 `BUDGET_PASSWORD` 环境变量。
- **AI 整理**：Recorder 支持 Secrets 或本机 `DEEPSEEK_API_KEY`；调用时转写内容会交给所配置的 API 服务商处理。没有密钥时可登记原文，不生成 AI 整理稿。
- **GitHub 备份**：通过 Secrets 或本机 `GITHUB_BACKUP_TOKEN` 启用后，相关备份内容会写入所配置的远端仓库。未配置时不能把“本机已保存”当作“已跨电脑备份”。
- **本地归档**：微信抓取会联网访问文章，结果写入已确认的目录；GoogleDrive 等同步目录可能继续由其客户端上传。先核对目标，不自动回填敏感路径。
- **Deepself**：发送的消息与抽象风格画像经过所选模型服务商；应用不读取或上传私密朋友圈原料。
- **凭据保护**：真实密钥只放 Secrets、环境变量或子项目规定的本机凭据位置，不写入源码、提交或日志。

## 文档与维护

- [文档索引](docs/README.md)：当前指南、历史设计与视觉预演。
- [仓库结构](docs/repository-structure.md)：主应用、子项目、资产、动态数据和生成目录的职责。
- [微信归档指南](docs/guides/wechat-archiver.md) / [Recorder 配置与迁移](docs/guides/ding_minutes_L_setup.md)。
- [中文更新日志](CHANGELOG_ZH-CN.md) / [English Change Log](CHANGELOG_EN.md)：保留真实改动、失败与修正记录。

`README.md` 镜像 `README_EN.md`；`CHANGELOG.md` 镜像 `CHANGELOG_EN.md`。修改当前行为说明时同步中英文，历史设计不覆盖当前代码与规则。

## 使用许可

仓库尚未提供独立的根 `LICENSE`；对外复用前需另行明确许可。第三方设计资产保留自己的[来源记录](assets/awesome-design-md/SOURCE.md)与许可证，不受本仓库是否设置根许可证的影响。
