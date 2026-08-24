# 更新日志

**语言**：简体中文 | [English](CHANGELOG_EN.md)
**README**：[中文](README_ZH-CN.md) | [English](README_EN.md)

本中文更新日志记录 Grok Builder 子项目。GitHub 默认入口 `CHANGELOG.md` 与英文版保持一致。

## 2026-08-24

- **首次发布受控 Codex-to-Grok 工作流**：新增面向 Windows 的个人 Codex 技能，运行 `Codex 规划 → 用户确认 → Grok Build 实施 → Codex 验收 → 必要时退回 Grok 修复`。
- **技能约束**：`SKILL.md` 定义触发语句、批准任务包结构、权限模型和验收规则。Codex 负责规划和验收，Grok Build 只作为实施工人。
- **确定性包装脚本**：`scripts/invoke-grok.ps1` 以命名会话启动 Grok Build 无界面模式，默认 `dontAsk`，已批准命令需显式放行，并默认拒绝推送、硬重置、仓库清理和常见递归删除。
- **Codex 元数据**：`agents/openai.yaml` 设置显示名称、短描述、默认提示词和隐式调用。
- **项目内不保存密钥**：包装脚本使用本机已有的 `grok login` 会话，或由 Grok Build 自行解析环境变量认证。
