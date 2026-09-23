# YaoYao 工具箱库结构

本文件是仓库层级的当前答案。页面注册以 `hello.py` 为准，代码行为以测试和运行代码为准；历史设计稿只说明当时决策，不覆盖当前状态。

## 目录约定（2026-09-23）

- 根目录保留主应用入口、双击启动器、依赖清单、中英文 README 和 CHANGELOG；主应用和五个独立子项目保持既有运行路径。
- `docs/guides/` 放当前使用、安装和迁移指南；普通指南使用描述用途的文件名，已有电脑迁移指南保留原文件名。
- `docs/assets/` 放文档专用的静态示意图；项目概览图不是应用截图。贡献入口位于根目录 `CONTRIBUTING.md`，问题和 PR 模板位于 `.github/`；模板不构成 CI 配置。
- `docs/history/` 平铺已结束的设计、实施计划和事件记录；带日期的原文件名保留，正文标记历史属性，不覆盖当年的事实。
- `docs/previews/` 放供回顾的视觉草稿，说明稿与 HTML 同目录，并标明是否已实施。它们是保留成果，不是可随手清理的缓存。
- `docs/README.md` 是文档导航，本文件是目录与数据边界的权威说明；新增文件先归类，再更新相应索引。
- `personal-skills/` 保存可跨电脑安装的 PPT、小红书评论真人图片、存储分析技能源码；它是集合目录，不增加独立运行项目计数。两项协作技能仍在根目录，各技能复制或安装到当前机器实际的 `CODEX_HOME/skills/` 后使用，不假定固定盘符或 Junction。
- `scripts/` 只放仍可使用的维护脚本。一次性助手完成用途后清理；历史版本由 Git 保留，不另建重复脚本归档。
- `outputs/` 放用户交付成果，`logs/` 放本机运行日志，`data/` 放应用数据；三者不能仅凭目录名称判定可删除。
- 只有核实为可再生的 `__pycache__/`、`.pytest_cache/` 和已确认的临时残留可清理；保留 `.venv/` 依赖主体及所有真实数据。
- 新的目录规范先记录在本文件，再执行对应整理。涉及删除、搬迁或路径配置时核对根 `AGENTS.md` 的具体授权边界，复用已有授权。

## 主结构

```text
E:\github\yao_1\
├── hello.py                         # 首页、模块元数据与分区导航唯一来源
├── pages\                           # Streamlit 页面；文件名前缀只控制原生侧栏顺序
│   ├── 18_19_concept_fables.py     # M19 概念寓言馆
│   ├── 19_20_ding2026.py           # M20 已停用，仅保留说明
│   ├── 20_21_awesome_design_md.py  # M21 Awesome Design MD 只读展示
│   ├── 21_22_gpt_planner_luna_executor.py # M22 AI 协作流程只读展示
│   ├── 22_23_docker_monitor.py     # M23 docker-monitor 只读展示
│   ├── 23_24_mail_workbench.py     # M24 邮件工作台，实际收信在本机
│   └── 24_25_phone_transfer.py     # M25 随手传，依赖配对收件端
├── utils\                           # 主应用可复用逻辑、数据校验和主题辅助
├── assets\                          # 可随主库部署的静态资产
│   ├── ding2026_m20_snapshot.json  # M20 脱敏聚合快照
│   └── awesome-design-md\           # M21 固定来源快照及许可证
├── concept_fables\                 # M19 目录逻辑与只读页面；条目在 data/concept_fables.json
├── data\                            # 主应用动态数据和恢复备份，修改前先同步远端
├── config\                          # 主应用配置
├── tests\                           # 页面、导航、数据合同和文档回归检查
├── scripts\                         # 本地维护、自动化及虚构评分演示
├── docs\                            # 文档导航与目录规则
│   ├── guides\                     # 当前使用、配置和迁移指南
│   ├── assets\                     # 文档专用静态示意图
│   ├── history\                    # 历史设计、实施计划和事件记录（平铺）
│   └── previews\                   # 保留的视觉预演稿
├── codex-grok-builder\             # 独立子项目
├── gpt-planner-luna-executor\      # 独立子项目
├── personal-skills\                # 三项可安装个人技能的集合，不是独立运行项目
│   ├── create-premium-ppt\          # PPT 制作与增量修订
│   ├── save-xhs-comment-human-images\ # 小红书评论真人图片筛选
│   └── storage-analyzer\            # 只读磁盘分析与目录读取缓存
├── Deepself\                       # 个人表达研究与回复工具，私密素材仅留本机
├── 115-ai-organizer\               # 默认只读盘点；审核和确认码后可执行整理
└── zhongshengshi\                  # 已暂停的独立子项目
```

## M19—M25 边界

- **M19**：`concept_fables/` 提供目录逻辑和只读页面，实际条目存于 `data/concept_fables.json`；新增寓言由对应 Skill 写入，页面本身不提供写入操作。
- **M20**：已停用并归入 archived，页面只显示停用说明；原有功能和统计不再生效。旧聚合快照保留历史用途，不代表当前页面仍在读取。
- **M21**：页面只读 `assets/awesome-design-md/design-md/`。来源 URL 和固定提交记录在 `assets/awesome-design-md/SOURCE.md`；源仓库的 `.git` 元数据不嵌入主库，避免线上部署遗漏资产。
- **M22**：页面介绍 `gpt-planner-luna-executor/` 与 `codex-grok-builder/` 两条路线的任务路由、交接边界、优化前后对照和实测记录，不创建代理、不调用模型、不控制浏览器，也不修改项目。公开脱敏记录位于 [docs/history/2026-09-05-skill-cost-optimization.md](history/2026-09-05-skill-cost-optimization.md)，区分独立通道验证与成本结论。
- **M23**：只读展示三个任务（TrendRadar、AIHOT 增量、德亚显卡报价），GLM 已移除。不访问网络、不启容器、不读取本机状态、不发钉钉。真实监控在独立私有仓库 [yaoy2/docker-monitor](https://github.com/yaoy2/docker-monitor) 和本机 TrendRadar 容器，主库没有运行时依赖。
- **M24**：展示已收取邮件、待办和归档结果；收信由明确请求触发，由单独配置的本机工作进程执行。可选 Jev 复核有独立的外部服务与数据传输边界，见 [邮件说明](guides/mail-jev.md)。
- **M25**：手机向已配对的桌面收件端传文件，桌面收件页面须保持打开；克隆仓库不会自动配置接收服务。以校验后的接收状态确认送达。

完整的 24 个入口（行政 7、教学 2、个人 7、archived 8）见[模块目录](guides/module-catalog.md)。测试从 `hello.py` 提取注册信息，核对目录中的编号、分区、状态和页面路径。

## 演示与贡献

- `scripts/demo_grade_workbench.py` 使用代码内虚构样例导出审核工作簿，并重新读取结果核验；输出到单独指定的演示目录，拒绝覆盖已有文件或写入仓库 `data/`。
- [快速开始](guides/getting-started.md)连接演示、环境安装和首次验证；[贡献指南](../CONTRIBUTING.md)说明改动落点和证据要求。
- [路线图](guides/roadmap.md)记录后续工作，[项目状态](guides/project-status.md)明确尚未完成的兼容性与许可事项。

## 本机状态与清理规则

- `.venv/`、`.pytest_cache/`、`__pycache__/` 是本机依赖或可再生缓存，不是产品源码。
- `outputs/`、`logs/` 和 `docs/previews/` 可能包含运行记录或人工成果，不能因为名称像临时文件就直接删除。已退役的 `mp_watch/` 和一次性色卡助手 `exports/` 不再作为当前目录使用，源码历史仍可从 Git 查回。
- `.streamlit/`、`.agents/`、`.codex/`、`.claude/` 可能影响本机运行或代理行为，整理时先核对规则和用途。
- 清理核对具体对象、恢复能力和现有授权；仅在授权缺失时先报告并询问；动态 `data/`、密钥、外部目录和独立项目不做顺手清理。

## 验证入口

- 本机双击 `运行测试.bat`，或在项目虚拟环境运行 `python -m pytest -q tests`，只收集主工具箱测试。
- 115 项目从 `115-ai-organizer/` 内使用 `..\.venv\Scripts\python.exe -m unittest discover -s tests`；Deepself 从仓库根目录使用 `.venv\Scripts\python.exe -m unittest discover -s Deepself/tests`。独立项目不混入主应用的测试收集。
- 页面代码用 Streamlit `AppTest` 验证；按项目规则不为截图启动本地 Streamlit 服务。
- `README.md` 必须与 `README_EN.md` 相同，`CHANGELOG.md` 必须与 `CHANGELOG_EN.md` 相同。
