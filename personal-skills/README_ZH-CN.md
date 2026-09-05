# 个人技能集合

**语言**：简体中文 | [English](README_EN.md)

**更新日志**：[中文](CHANGELOG_ZH-CN.md) | [English](CHANGELOG_EN.md)

这里保存可跨电脑安装的个人 Codex 技能源码。它是技能集合，不是新的独立运行项目；主工具箱仍有五个独立子项目，克隆仓库不会启动这些技能。

| 技能 | 用途与触发 | 本轮减少的重复工作 | 保留的边界 |
| --- | --- | --- | --- |
| [create-premium-ppt](create-premium-ppt/SKILL.md) | 根据素材、模板或定向要求制作和修改可编辑 PPT。 | 局部修改复用确认过的结构，增量检查受影响页面及相关全局约束。 | 仍检查缺失、裁切、重叠、乱码、分页和可读性；保留用户要求的页数、模板和验收。 |
| [save-xhs-comment-human-images](save-xhs-comment-human-images/SKILL.md) | 根据笔记链接保存小红书评论区以真人为主体的照片。 | 优先复用已登录且可控制的浏览器，避免重复开浏览器和重复登录检查。 | 先放大判断再下载；不把头像、正文配图、纯文字或插画当成目标，登录与验证交给用户。 |
| [storage-analyzer](storage-analyzer/SKILL.md) | 盘点磁盘占用、生成分类建议和交互报告。 | 单次扫描复用目录读取缓存，避免为多种统计重复读取同一目录。 | 分析保持只读；清理按明确授权执行，不擅自删除数据或扩大扫描范围。 |

两个协作技能仍在仓库根目录：[GPT Planner · Luna Executor](../gpt-planner-luna-executor/README_ZH-CN.md) 和 [Codex → Grok Builder](../codex-grok-builder/README_ZH-CN.md)。

## 安装与更新

选择需要的完整技能目录，复制或安装到当前机器的 `CODEX_HOME/skills/<技能名>/`。未设置 `CODEX_HOME` 时，通常是用户目录下的 `.codex/skills/`。不要把整个 `personal-skills/` 当成一个技能安装。

每台机器独立核对实际路径、已有同名技能、本机修改和运行依赖，再同步仓库版本；不假定某个 E 盘目录或 Junction 已存在。仓库拉取只更新源码，不自动覆盖安装副本，也不迁移登录、密钥或私密素材。

## 验证范围

2026-09-05 的存储缓存验证通过 5 项行为检查，8 组输出保持一致；虚构目录夹具的读取次数从 24 次降到 14 次。结果只描述目录访问，不是模型 token、整盘耗时或费用测量。本轮未执行实际全盘扫描，也未运行真实 PPT 或小红书业务任务。

PPT 和小红书的修改是流程规则优化，实际任务仍按交付物和相称证据验收。详见[公开验证记录](../docs/history/2026-09-05-skill-cost-optimization.md)。
