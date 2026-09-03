# YaoYao 工具箱库结构

本文件是仓库层级的当前答案。页面注册以 `hello.py` 为准，代码行为以测试和运行代码为准；历史设计稿只说明当时决策，不覆盖当前状态。

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
├── concept_fables\                 # M19 已收录寓言数据
├── data\                            # 主应用动态数据和恢复备份，修改前先同步远端
├── config\                          # 主应用配置
├── tests\                           # 页面、导航、数据合同和文档回归检查
├── scripts\                         # 本地维护与自动化脚本
├── docs\                            # 当前说明和历史设计/实施记录
├── codex-grok-builder\             # 独立子项目
├── gpt-planner-luna-executor\      # 独立子项目
├── Deepself\                       # 独立子项目
├── 115-ai-organizer\               # 115 网盘只读整理系统，第一版不改 115 文件
└── zhongshengshi\                  # 已暂停的独立子项目
```

## M19—M23 边界

- **M19**：页面读取 `concept_fables/`；新增寓言由对应 Skill 写入，页面本身不提供写入操作。
- **M20**：页面只读取 `assets/ding2026_m20_snapshot.json`。真实扫描、分发、归档、撤销、配置和数据库继续只在独立本地项目 `E:\github\ding2026-system` 中运行，主库没有运行时依赖。
- **M21**：页面只读 `assets/awesome-design-md/design-md/`。来源 URL 和固定提交记录在 `assets/awesome-design-md/SOURCE.md`；源仓库的 `.git` 元数据不嵌入主库，避免线上部署遗漏资产。
- **M22**：页面只介绍 `gpt-planner-luna-executor/` 的角色、Packet 和审查流程，不创建代理、不调用模型、不控制浏览器，也不修改项目。
- **M23**：页面只展示 docker-monitor 的三个 Docker 任务（GLM 促销雷达、AIHOT 增量、德亚显卡报价），并说明德亚欧元标价如何按 ×1.13×7.79+150 折合人民币。不访问网络、不启容器、不读取本机状态、不发钉钉。真实监控在独立私有仓库 [yaoy2/docker-monitor](https://github.com/yaoy2/docker-monitor)，主库没有运行时依赖。侧栏不加新入口。

## 本机状态与清理规则

- `.venv/`、`.pytest_cache/`、`__pycache__/` 是本机依赖或可再生缓存，不是产品源码。
- `.tmp/`、`logs/`、`exports/`、`previews/` 可能包含运行用途或人工产物，不能因为名称像临时文件就直接删除。
- `.streamlit/`、`.agents/`、`.codex/`、`.claude/` 可能影响本机运行或代理行为，整理时先核对规则和用途。
- 清理遵循“先报告、再确认、后删除”；动态 `data/`、密钥、外部目录和独立项目不做顺手清理。

## 验证入口

- 本机双击 `运行测试.bat`，或在项目虚拟环境运行 `python -m pytest -q`。
- 页面代码用 Streamlit `AppTest` 验证；按项目规则不为截图启动本地 Streamlit 服务。
- `README.md` 必须与 `README_EN.md` 相同，`CHANGELOG.md` 必须与 `CHANGELOG_EN.md` 相同。
