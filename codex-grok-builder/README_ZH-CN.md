# Codex → Grok Builder

**语言**：简体中文 | [English](README_EN.md)

**更新日志**：[中文](CHANGELOG_ZH-CN.md) | [English](CHANGELOG_EN.md)

面向 Windows 的个人 Codex 技能：Codex 整理目标、范围和验收要求，用户批准具体方案后，由已登录的 Grok Build CLI 实施，Codex 根据实际差异和测试证据验收。

## 何时值得使用

用户明确说“用 Grok 去做”“让 Grok 写代码”“交给 Grok 实现”时启用。引用这些话来讨论或修改技能，不会启动 Grok；只要求操作 Grok 网页时应使用浏览器工具。

模型尚未指定时，小改动通常由当前 Agent 直接完成。范围清楚、执行量较大的任务才更值得委派；强模型处理关键不确定性、重大取舍和必要验收，不固定为 Sol，也不要求每项任务附加 Luna 审查。选择依据是完成合格任务的总成本，包括准备、交接、等待、修复和验收。

## 工作流程与边界

1. Codex 读取项目规则、已有修改和最少定位信息，给出具体方案、文件范围、禁止范围、测试命令和验收标准。目标、范围、验收明确后停止预读，不先写完整实现再交接。
2. 用户批准 Grok 的方案、修改范围和测试命令；同一任务中仍有效的具体授权可复用，扩大范围或改变条件时再确认。
3. 将相关工作合并成一个任务包，让 Grok 完成范围内探索、实现、测试和普通修复，主控不逐次盯工具调用。
4. Grok 返回变更文件、检查结果和必要日志位置。Codex 聚焦实际差异、关键风险和少量可核对证据；有缺陷或未解决疑点才追加检查或修复。

任务包不是权限沙箱。Grok 不得擅自扩大范围、提交、推送、部署、使用凭据或执行破坏性操作。具体方案与命令审批保留，包装脚本不修改全局权限配置。

## 安装与环境

需要 Windows PowerShell、本机可用的 `grok` 命令及用户亲自完成的 Grok 登录。技能不保存密钥，包装脚本使用 CLI 已有认证。Python 3 仅在使用技能校验器时需要。

取得仓库后，把完整的 `codex-grok-builder/` 复制或安装到各台机器实际使用的 `CODEX_HOME/skills/codex-grok-builder/`。未设置 `CODEX_HOME` 时，通常是用户目录下的 `.codex/skills/`。更新前核对同名技能并保留本机改动；拉取仓库不会自动更新安装副本，不依赖固定盘符或 Junction。必要时新建 Codex 任务刷新技能发现。

入口是 [SKILL.md](SKILL.md)，界面元数据在 [agents/openai.yaml](agents/openai.yaml)，包装脚本是 [scripts/invoke-grok.ps1](scripts/invoke-grok.ps1)。

## 包装脚本示例

下面是已批准的虚构合并函数任务示例；路径和精确测试命令须换成本次批准的值。从技能目录运行：

```powershell
& '.\scripts\invoke-grok.ps1' `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\approved-task.md' `
  -AllowRule @('Bash(python -B -m pytest -q tests/test_merge_rows.py -p no:cacheprovider)') `
  -Quiet `
  -MaxTurns 12
```

- `-AllowRule` 只列本次批准的精确命令，避免宽泛通配符。
- `-Quiet` 保留完整日志，只减少传回主控的输出流；不会减少 Grok 自己的推理或工具 token。
- `-MaxTurns 12` 是本例预算，不保证 12 轮内完成；达到限制仍须核对实际结果。
- `-DryRun` 仅展示最终参数，不启动 Grok，也不创建输出目录或日志。
- 修复可用 `-ResumeSessionId` 继续已有会话；每次调用使用独立日志，stderr 单独保存，并返回 Grok 的真实退出码。

默认 `dontAsk` 会与已有配置共同决定实际权限，不能当成硬文件沙箱。脚本默认允许读取、搜索、编辑、`git status` 和 `git diff`，并包含推送、硬重置和常见递归删除的拒绝规则。`-AlwaysApprove` 需要针对本次工具模式切换的单独授权；不要因此启用全局自动批准。

## 验证与成本记录

先检查 PowerShell 能否解析脚本，再用 `-DryRun` 核对项目、任务包、命令与输出位置。脚本修复使用模拟 CLI 检查失败退出码、日志隔离、恢复会话名和无副作用的预演；实际编码仍需检查真实差异与相称测试。

包装脚本从 CLI 终态报告读取实际 usage/cost，`run.json` 提供 `TokenUsage`、`NumTurns`、`ResolvedModels`、`CliReportedCostUsd` 和 `UsageStatus`。未提供的字段保留 `null`，`ActualSubscriptionCharge` 为 `unknown`。总 token、高价模型用量、订阅额度和费用是不同指标；CLI 报价不是订阅账单。2026-09-05 的虚构 `merge_rows` 任务首轮通过同一组 12 项检查、零修复；没有全程强模型对照，不能据此宣布省 token 或成本排名。完整口径见[公开验证记录](../docs/history/2026-09-05-skill-cost-optimization.md)。
