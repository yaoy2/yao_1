# 更新日志

**语言**：简体中文 | [English](CHANGELOG_EN.md)
**README**：[中文](README_ZH-CN.md) | [English](README_EN.md)

本中文更新日志记录 Grok Builder 子项目。GitHub 默认入口 `CHANGELOG.md` 与英文版保持一致。

## 2026-09-06

- **按任务决定交接规模**：明确模型与有效授权保持不变；开放选型时小改由当前 Agent 完成，执行量较大时合并任务包委派，主控不先读完整个项目或写完整实现再转交，不逐次盯工具调用，也不固定 Sol 或强制 Luna 复审。
- **保留权限边界**：具体方案、范围和测试命令审批继续有效；说明 dontAsk 与已有配置共同生效，不是硬文件沙箱。安装说明改为各台机器实际的 CODEX_HOME/skills，移除过时的固定 E 盘 Junction 描述。
- **修复包装脚本**：日志按调用隔离、stderr 单独保存、保留真实退出码，日志文件名改用独立 run ID，不再使用会话标题，DryRun 不再创建输出目录；Quiet 保存完整日志但只减少返回主控的流。run.json 从终态读取 TokenUsage、NumTurns、ResolvedModels、CliReportedCostUsd 和 UsageStatus，缺失字段保留 null，实际订阅扣费为 unknown。
- **验证与判断修正**：11 次模拟运行、16 项断言通过；9 月 5 日 Grok 在虚构 merge_rows 任务首轮通过 12/12 检查、零修复，5 轮、native 50.319 秒。CLI 回报总量 96,927 token（含 58,624 缓存）和 $0.01963398，非订阅账单，不含主控、准备和验收；没有全程强模型基线，不能把流程通过写成已省 token 或成本优势。详见[公开记录](../docs/history/2026-09-05-skill-cost-optimization.md)。

## 2026-08-24

- **首次发布受控 Codex-to-Grok 工作流**：新增面向 Windows 的个人 Codex 技能，运行 `Codex 规划 → 用户确认 → Grok Build 实施 → Codex 验收 → 必要时退回 Grok 修复`。
- **技能约束**：`SKILL.md` 定义触发语句、批准任务包结构、权限模型和验收规则。Codex 负责规划和验收，Grok Build 只作为实施工人。
- **确定性包装脚本**：`scripts/invoke-grok.ps1` 以命名会话启动 Grok Build 无界面模式，默认 `dontAsk`，已批准命令需显式放行，并默认拒绝推送、硬重置、仓库清理和常见递归删除。
- **Codex 元数据**：`agents/openai.yaml` 设置显示名称、短描述、默认提示词和隐式调用。
- **项目内不保存密钥**：包装脚本使用本机已有的 `grok login` 会话，或由 Grok Build 自行解析环境变量认证。
