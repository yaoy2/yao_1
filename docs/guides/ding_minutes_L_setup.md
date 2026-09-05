# Recorder_笔记：L 电脑运行配置指南

[返回文档导航](../README.md)

这份指南用于把 M11 Recorder_笔记迁移到另一台 Windows 电脑，核对扫描目录、模型凭据和每日 19:00 的运行安排。文档整理本身没有修改目录配置、设置凭据、创建任务计划或执行真实扫描。

## 一、取得代码与准备环境

已有仓库时，先检查本地改动，再同步代码；新电脑则先克隆仓库。不要丢弃工作区现有修改来完成同步。

```powershell
git status --short
git fetch origin
git pull --rebase origin main
```

在仓库根目录双击 [`首次安装.bat`](../../首次安装.bat)，使用项目 `.venv` 安装运行和测试依赖。已有可用环境不必重装。后续命令中的路径均以仓库根目录为起点。

## 二、先核对迁移数据

| 数据 | 用途与迁移边界 |
|---|---|
| `data/ding_minutes.db` | 本机 SQLite 登记库，被 Git 忽略，不会随 `git pull` 自动迁移。 |
| `data/ding_minutes_cloud.json` | GitHub 同步的展示账本，包含整理稿和备注；拉取后可供页面展示。 |
| 原始 Word 文件 | 留在用户确认的扫描目录，不随本仓库迁移。 |

当前扫描和导出程序会根据本机登记库的最新 1000 条记录重建云 JSON，**不会自动把云 JSON 恢复到 SQLite，也不会自动合并线上新备注**。新电脑若只有云 JSON，或本机登记库落后于线上，先核对并安排数据恢复／合并，再执行扫描或导出；不要用空库、旧库覆盖已拉取的账本。

所有涉及动态账本的正式操作都要先同步远端，再核对本机记录，最后才扫描、检查差异和提交。仅完成 `git pull` 不代表数据库迁移已经完成。

## 三、核对扫描目录和时间窗

当前配置来自 [`config/ding_minutes.ini`](../../config/ding_minutes.ini)：

```ini
[ding_minutes]
watch_dir = C:\Users\Yao\Downloads
daily_run_time = 19:00
```

以上是现有值，不是要求所有电脑照填的路径。迁移前确认真实扫描位置；需要调整路径或任务时间时，先说明影响并取得确认。API key 不放进这个文件。

扫描只检查该目录第一层的 `.docx`，不递归子目录。文件名需满足 `export_*.docx`、`dt*.docx`、包含“原文”，或同时包含“钉钉”和“录音／转文字／转写”；临时锁文件 `~$...` 会跳过。

时间依据文件创建时间，范围是最近一个已结束的每日时间窗。例如每天 19:00 截止：当天 19:00 后扫描前一天 19:00 至当天 19:00；当天 19:00 前则扫描再前一个完整时间窗。`found=0` 可能只是没有匹配该时间窗的文件。

## 四、区分命令行与页面凭据

| 入口 | DeepSeek API key 来源 |
|---|---|
| `scripts/scan_ding_minutes.py` | 运行进程的 `DEEPSEEK_API_KEY` 环境变量；脚本不会主动读取 Streamlit Secrets。 |
| Recorder 页面 | 先读 Streamlit Secrets 的 `DEEPSEEK_API_KEY`、`deepseek_api_key` 或 `[deepseek]` 中的 `api_key`，再回退到进程环境变量。 |
| `每日Recorder扫描.bat` | 先从当前 Windows 用户环境变量读取 `DEEPSEEK_API_KEY`，再传给扫描进程。 |

本机命令行使用时，经确认后可在 Windows“环境变量”窗口添加用户变量 `DEEPSEEK_API_KEY`。保存后重新打开终端；任务计划应使用同一个已配置凭据的 Windows 账号。不要把真实密钥粘贴进命令历史、源码、INI、日志或仓库文件。

以下 PowerShell 检查只显示配置状态，不显示密钥内容：

```powershell
if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User"))) {
    "Windows 用户变量：未配置"
} else {
    "Windows 用户变量：已配置"
}
if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
    "当前终端：未配置，请重新打开终端"
} else {
    "当前终端：已配置"
}
```

状态为“已配置”只说明存在非空值，不能证明密钥有效或接口可用。页面有凭据但命令行缺少凭据时，先检查两者是否用了不同来源。

## 五、确认后执行一次正式扫描

[`scan_ding_minutes.py`](../../scripts/scan_ding_minutes.py) 当前没有 `--dry-run`、目录覆盖或自选日期参数；运行它就会扫描并写入。不要把 `--help` 当作安全探测方式，该脚本没有参数解析。

执行前完成前述远端同步、数据核对和目录确认，然后在根目录运行：

```powershell
.\.venv\Scripts\python.exe scripts\scan_ding_minutes.py
```

这一步会登记原文到本机 SQLite，并重建 `data/ding_minutes_cloud.json`；有密钥时还会把匹配的转写正文发给配置的 DeepSeek 接口生成整理稿。没有密钥仍会登记原文，状态为 `pending`。它不会单独完成 Git 提交或推送。

终端结果示例：

```text
Ding minutes scan finished: found=1, processed=1, skipped=0, failed=0
```

- `processed` 表示已处理登记，也可能是缺少密钥而等待整理；应继续查看记录状态。
- 文件夹不存在：核对 `watch_dir`。
- 未配置密钥：核对当前进程的环境变量，而不是只看网页配置。
- `failed` 大于 0：查看每条记录的错误；当前脚本不会仅因单条失败就返回非零退出码。
- [`sync_recorder_cloud.py`](../../scripts/sync_recorder_cloud.py) 只是从 SQLite 重新导出 JSON，同样有写入副作用；它不负责拉取、合并或上传 GitHub。

## 六、确认后设置每天 19:00 自动运行

先检查任务计划程序是否已有同类任务，避免重复扫描。确认迁移数据、路径和凭据都已就绪，再创建或调整任务；本文不表示任务已经设置完成。

需要扫描并同步 GitHub 时，根目录 [`每日Recorder扫描.bat`](../../每日Recorder扫描.bat) 已包含“检查 main 分支 → 拉取远端 → 扫描 → 导出 → 有变化时提交推送”的流程。它会写日志、调用模型并访问 GitHub。目前脚本仍固定项目路径 `E:\github\yao_1` 和 `C:\Users\Yao\AppData\Local\Programs\Python\Python314\python.exe`，迁移时须另行确认并适配，不能直接假定新电脑可用；该批处理也不会代替第二节的数据合并核对。

当前批处理会在扫描或导出返回非零状态后继续尝试后续导出、提交和推送，末尾才返回扫描或导出的状态。因此“已拉取远端”或任务最终退出状态都不能保证失败时没有写入或推送；启用定时任务前应先核对日志及实际记录。本次只补充说明，未修改该批处理的运行逻辑。

适配完成后的任务设置参考：

| 项目 | 设置 |
|---|---|
| 名称 | `Ding Minutes Scan` |
| 触发器 | 每天 19:00，与 `daily_run_time` 一致 |
| 操作 | 启动程序 |
| 程序或脚本 | Windows 的 `cmd.exe`，通常为 `C:\Windows\System32\cmd.exe` |
| 添加参数 | `/c ""E:\github\yao_1\每日Recorder扫描.bat""`；换成已确认的项目路径 |
| 起始于 | 项目目录，例如 `E:\github\yao_1` |
| 运行账号 | 已配置 DeepSeek 用户变量和 GitHub 访问权限的本人账号 |

如果只需要本地扫描，可把“程序”设为项目 `.venv\Scripts\python.exe` 的绝对路径，参数设为 `scripts\scan_ding_minutes.py`，起始目录仍为项目根目录；这种设置不包含远端同步和提交，不能当作完整线上同步方案。

## 七、打开板块 11 查看结果

日常使用可双击根目录 [`启动YaoYao工具箱.bat`](../../启动YaoYao工具箱.bat)，进入“Recorder_笔记”。页面需要已配置的访问密码：Streamlit Secrets 的 `budget_password` 或本机 `BUDGET_PASSWORD`。

页面显示原始转写、AI 整理稿、处理状态、错误信息和备注。没有本机扫描目录时，页面进入云端展示模式；没有本地记录时，可以显示已同步的云 JSON。备注可用来标记“已写新闻稿”“待核实”等，保存后的 GitHub 同步还依赖已有 `GITHUB_BACKUP_TOKEN` 配置。

本指南的归档位置见 [文档导航](../README.md)；更早的设计和实施计划保留在 `docs/history/`，只用于追溯当时决策。
