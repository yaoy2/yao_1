# 文档导航

[项目中文说明](../README_ZH-CN.md) · [English README](../README_EN.md) · [中文更新日志](../CHANGELOG_ZH-CN.md)

当前用法先看操作指南和库结构；历史记录用于追溯当时的设计、实施和问题处理，不覆盖当前代码、项目规则或用户指令。

## 当前说明

| 文档 | 内容 |
|---|---|
| [库结构与目录边界](repository-structure.md) | 主应用、独立子项目、静态资产、动态数据和本机生成文件分别放在哪里。 |
| [微信与本地文件归档指南](guides/wechat-archiver.md) | 本机 8502 入口、四条归档路线、实际保存位置和 IMA 边界。 |
| [Recorder：L 电脑迁移与运行](guides/ding_minutes_L_setup.md) | 数据迁移、凭据来源、真实扫描副作用和任务计划设置。 |

## 历史设计与实施

以下 8 份 Markdown 平铺保存在 `history/`；日期和文件名保留以便追溯。旧路径、模块数量、模型选择和未勾选步骤只表示当时状态。

| 日期 | 主题 | 记录 |
|---|---|---|
| 2026-05-23 | 网络备忘录 | [设计规格](history/2026-05-23-web-memo-design.md) · [实施计划](history/2026-05-23-web-memo.md) |
| 2026-05-24 | Recorder 文件纪要 | [设计规格](history/2026-05-24-ding-minutes-design.md) · [实施计划](history/2026-05-24-ding-minutes.md) |
| 2026-07-01 | 邮件通知页面 | [实施计划](history/2026-07-01-email-notice-streamlit-page.md) |
| 2026-08-31 | M20 文件中转发放展示 | [设计规格](history/2026-08-31-m20-ding2026-showcase-design.md) · [实施计划](history/2026-08-31-m20-ding2026-showcase.md) |
| 2026-09-05 / 06 | 技能协作与总成本优化 | [实测、修改与证据边界](history/2026-09-05-skill-cost-optimization.md) |

[Grok Build 代码数据上传事件报告（PDF）](history/Grok_Build_代码数据上传事件报告.pdf) 保留事件经过与处理依据，不是当前操作指南。

## 静态设计稿

- [首页预演说明](previews/README.md)：说明历史稿与当前首页的关系。
- [Apple 风格首页预演](previews/apple_hub_preview.html)：浏览器直接打开的历史 HTML，无需启动服务。

## 存放约定

- `guides/`：仍适用的操作和迁移指南；代码行为变化时同步校正。
- `history/`：按日期保留设计、实施计划和事件记录；不把旧计划当作新任务自动执行。
- `previews/`：静态设计稿和对应说明；正式运行资产继续放主库 `assets/`。
- 本目录不放密钥、真实业务备份、运行日志或依赖缓存。独立子项目的专属说明留在各自目录，由主 README 导航。
