# YaoYao 工具箱库结构

本文件是仓库层级的当前答案。页面注册以 `hello.py` 为准，代码行为以测试和运行代码为准；历史设计稿只说明当时决策，不覆盖当前状态。

## 目录约定（2026-09-06）

- 根目录保留主应用入口、双击启动器、依赖清单、中英文 README 和 CHANGELOG；主应用和五个独立子项目保持既有运行路径。
- `docs/guides/` 放当前使用、安装和迁移指南；普通指南使用描述用途的文件名，已有电脑迁移指南保留原文件名。
- `docs/history/` 平铺已结束的设计、实施计划和事件记录；带日期的原文件名保留，正文标记历史属性，不覆盖当年的事实。
- `docs/previews/` 放供回顾的视觉草稿，说明稿与 HTML 同目录，并标明是否已实施。它们是保留成果，不是可随手清理的缓存。
- `docs/README.md` 是文档导航，本文件是目录与数据边界的权威说明；新增文件先归类，再更新相应索引。
- `personal-skills/` 保存可跨电脑安装的 PPT、小红书评论真人图片、存储分析技能源码；它是集合目录，不增加独立运行项目计数。两项协作技能仍在根目录，各技能复制或安装到当前机器实际的 `CODEX_HOME/skills/` 后使用，不假定固定盘符或 Junction。
- `scripts/` 只放仍可使用的维护脚本。一次性助手完成用途后清理；历史版本由 Git 保留，不另建重复脚本归档。
- `outputs/` 放用户交付成果，`logs/` 放本机运行日志，`data/` 放应用数据；三者不能仅凭目录名称判定可删除。
- 只有核实为可再生的 `__pycache__/`、`.pytest_cache/` 和已确认的临时残留可清理；保留 `.venv/` 依赖主体及所有真实数据。
- 新的目录规范先记录在本文件，再执行对应整理。涉及删除、搬迁或路径配置时仍遵守根 `AGENTS.md` 的确认要求。

## 主结构

```text
E:\github\yao_1\
├── hello.py                         # 首页、模块元数据与分区导航唯一来源
├── pages\                           # Streamlit 页面；文件名前缀只控制原生侧栏顺序
│   ├── 18_19_concept_fables.py     # M19 概念寓言馆
│   ├── 19_20_ding2026.py           # M20 文件中转发放系统只读展示
│   ├── 20_21_awesome_design_md.py  # M21 Awesome Design MD 只读展示
│   ├── 21_22_gpt_planner_luna_executor.py # M22 AI 协作流程只读展示
│   └── 22_23_docker_monitor.py     # M23 docker-monitor 只读展示
├── utils\                           # 主应用可复用逻辑、数据校验和主题辅助
├── assets\                          # 可随主库部署的静态资产
│   ├── ding2026_m20_snapshot.json  # M20 脱敏聚合快照
│   └── awesome-design-md\           # M21 固定来源快照及许可证
├── concept_fables\                 # M19 目录逻辑与只读页面；条目在 data/concept_fables.json
├── data\                            # 主应用动态数据和恢复备份，修改前先同步远端
├── config\                          # 主应用配置
├── tests\                           # 页面、导航、数据合同和文档回归检查
├── scripts\                         # 本地维护与自动化脚本
├── docs\                            # 文档导航与目录规则
│   ├── guides\                     # 当前使用、配置和迁移指南
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

## M19—M23 边界

- **M19**：`concept_fables/` 提供目录逻辑和只读页面，实际条目存于 `data/concept_fables.json`；新增寓言由对应 Skill 写入，页面本身不提供写入操作。
- **M20**：页面只读取 `assets/ding2026_m20_snapshot.json`。真实扫描、分发、归档、撤销、配置和数据库继续只在独立本地项目 `E:\github\ding2026-system` 中运行，主库没有运行时依赖。
- **M21**：页面只读 `assets/awesome-design-md/design-md/`。来源 URL 和固定提交记录在 `assets/awesome-design-md/SOURCE.md`；源仓库的 `.git` 元数据不嵌入主库，避免线上部署遗漏资产。
- **M22**：页面介绍 `gpt-planner-luna-executor/` 与 `codex-grok-builder/` 两条路线的任务路由、交接边界、优化前后对照和实测记录，不创建代理、不调用模型、不控制浏览器，也不修改项目。公开脱敏记录位于 [docs/history/2026-09-05-skill-cost-optimization.md](history/2026-09-05-skill-cost-optimization.md)，区分独立通道验证与成本结论。
- **M23**：页面 2×2 平铺四个 Docker 任务（TrendRadar、GLM 促销雷达、AIHOT 增量、德亚显卡报价），并说明德亚欧元标价如何按 ×1.13×7.79+150 折合人民币。不访问网络、不启容器、不读取本机状态、不发钉钉。真实监控在独立私有仓库 [yaoy2/docker-monitor](https://github.com/yaoy2/docker-monitor) 和本机 TrendRadar 容器，主库没有运行时依赖。侧栏不加新入口。

## 本机状态与清理规则

- `.venv/`、`.pytest_cache/`、`__pycache__/` 是本机依赖或可再生缓存，不是产品源码。
- `outputs/`、`logs/` 和 `docs/previews/` 可能包含运行记录或人工成果，不能因为名称像临时文件就直接删除。已退役的 `mp_watch/` 和一次性色卡助手 `exports/` 不再作为当前目录使用，源码历史仍可从 Git 查回。
- `.streamlit/`、`.agents/`、`.codex/`、`.claude/` 可能影响本机运行或代理行为，整理时先核对规则和用途。
- 清理遵循“先报告、再确认、后删除”；动态 `data/`、密钥、外部目录和独立项目不做顺手清理。

## 验证入口

- 本机双击 `运行测试.bat`，或在项目虚拟环境运行 `python -m pytest -q tests`，只收集主工具箱测试。
- 115 项目从 `115-ai-organizer/` 内使用 `..\.venv\Scripts\python.exe -m unittest discover -s tests`；Deepself 从仓库根目录使用 `.venv\Scripts\python.exe -m unittest discover -s Deepself/tests`。独立项目不混入主应用的测试收集。
- 页面代码用 Streamlit `AppTest` 验证；按项目规则不为截图启动本地 Streamlit 服务。
- `README.md` 必须与 `README_EN.md` 相同，`CHANGELOG.md` 必须与 `CHANGELOG_EN.md` 相同。
