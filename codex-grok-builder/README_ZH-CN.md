# Codex → Grok Builder

[English](README_EN.md)

这是一个面向 Windows 的个人 Codex 技能，用于运行受控的双智能体编码闭环：

`Codex 规划 → 用户确认 → Grok Build 实施 → Codex 验收 → 必要时退回 Grok 修复`

## 触发方式

只要用户的直接指令表达“用 Grok 去做”的意思，就应自动考虑调用本技能，例如：

- `用grok去做`
- `用 Grok 去做`
- `让 Grok 做`
- `交给 Grok 实现`
- `让 Grok 写代码`
- `让 Grok 完成操作，你来验收`

大小写、空格和自然语言变体不需要完全一致。仅为修改、说明或测试技能而引用这些句子时，不会启动实施流程。

## 角色分工

- **Codex：**检查仓库、制定唯一实施方案、界定范围和验收标准、审查实际差异，并独立重跑测试。
- **Grok Build：**通过本机无界面命令行，只修改批准范围并只运行批准命令。
- **用户：**确认方案；如果后来需要扩大范围、增加权限、部署、使用密钥或执行破坏性操作，再单独授权。

## 环境要求

- Windows PowerShell。
- 本机可执行 `grok`，并已经通过 `grok login` 登录。
- 如果要求固定规划配置，应在 Codex 任务中选择 GPT-5.6 Sol 和 `xhigh` 推理强度。
- Python 3 仅用于运行 Codex 自带的技能校验器；运行包装脚本本身只需要 PowerShell。

本项目不保存 API Key。包装脚本使用 Grok Build 已有的本机登录状态，或由 Grok Build 自己解析环境变量认证。

## 文件结构

```text
codex-grok-builder/
├── SKILL.md                    技能触发和工作流约束
├── README.md                   GitHub 默认英文说明
├── README_EN.md                英文说明镜像
├── README_ZH-CN.md             中文说明
├── CHANGELOG.md                GitHub 默认英文更新日志
├── CHANGELOG_EN.md             英文更新日志镜像
├── CHANGELOG_ZH-CN.md          中文更新日志
├── agents/openai.yaml          Codex 界面元数据和自动触发设置
└── scripts/invoke-grok.ps1     确定性的 Grok Build 调用脚本
```

## 运行流程

1. Codex 记录工作区原有状态并读取仓库规则。
2. Codex 给出文件范围、禁止范围、测试命令、风险和验收标准。
3. 用户确认后，Codex 在仓库外创建临时任务包。
4. 包装脚本用命名会话和明确权限规则启动 Grok Build 无界面模式。
5. Grok 完成后，Codex 检查真实差异并独立重跑测试，不直接相信 Grok 的完成声明。
6. 验收失败时，可在同一个 Grok 会话中进行最多两轮针对性修复。

## 直接调用包装脚本

一般由 Codex 自动调用。排查问题或手工使用时：

```powershell
& "$env:USERPROFILE\.codex\skills\codex-grok-builder\scripts\invoke-grok.ps1" `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\approved-task.md' `
  -AllowRule @('Bash(npm.cmd test*)', 'Bash(npm.cmd run build*)')
```

增加 `-DryRun` 可以只查看最终 Grok 参数，不真正启动 Grok。

## 权限设计

- 默认使用 `dontAsk`：没有明确批准的工具会被静默拒绝。
- 默认允许读取、搜索、编辑、`git status` 和 `git diff`。
- 测试和构建命令必须通过 `-AllowRule` 单独放行。
- 默认拒绝推送、硬重置、仓库清理和常见递归删除命令。
- 只有用户针对本次运行明确授权后才能使用 `-AlwaysApprove`；即使有拒绝规则，该模式仍然风险更高。
- 工作指令禁止 Grok 自行提交、推送、部署、读取密钥或扩大范围，除非批准的任务包明确授权。

## 安装位置

项目真身位于：

```text
E:\github\yao_1\codex-grok-builder
```

个人技能发现路径使用 Windows Junction 指向项目真身：

```text
E:\codex\.codex\skills\codex-grok-builder
```

这样既能随 `yao_1` 进行版本管理，又能继续被 Codex 自动发现。修改后如果当前任务没有立即刷新技能，可新开一个 Codex 任务或重启 Codex。

## 验证

在项目目录运行：

```powershell
py -3 -X utf8 'E:\codex\.codex\skills\.system\skill-creator\scripts\quick_validate.py' .
```

发布前还应检查 PowerShell 脚本能否正常解析：

```powershell
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  '.\scripts\invoke-grok.ps1',
  [ref]$tokens,
  [ref]$errors
) | Out-Null
$errors
```
