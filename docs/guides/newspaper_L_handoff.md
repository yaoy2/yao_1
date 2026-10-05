# L 电脑接管 M28 每日新闻

本文件是 2026-10-05 用户要求随仓库交付的接管任务。用户的目标是：在长期运行的电脑 L 拉取项目后，由 L 上的 Codex 继续完成安装和验证，不再要求用户复制聊天记录、编写命令或手动配置任务计划。

代码仓库：`yaoy2/yao_1`。线上入口：<https://whatsup.streamlit.app/28_newspaper>。

## 先明确实际状态

- 本仓库包含独立采集程序、私有新闻快照读取、Windows 任务安装器和测试。
- 本文件随代码发布不代表 L 已安装。安装与试跑回执仅保存在目标机器的 `.local/newspaper/`，不把某台机器的成功状态提交为全局事实。
- 普通 `git pull` 只更新文件，不会启动 Codex 或自动注册系统任务。L 上负责拉取的 Codex 应在更新后重新读取项目根目录 `AGENTS.md` 和本文件，并完成下列接管事项；已有聊天没有自动重读时，应主动读取这两个文件。
- 不要在 D 注册任务，也不要把“不是 D”作为“就是 L”的证据。L 是用户的设备称呼，不一定是 Windows 的 `COMPUTERNAME`。先根据当前用户提供的机器上下文核实，再读取实际主机名。

## 本次范围与数据流

每天北京时间 **09:00 开始**采集，完成后发布结果。实际完成时间以日志和页面显示为准，不承诺网络抓取在 09:00:00 已完成。

`L 的 Windows 任务 → scripts/newspaper_daily.py → yaoy2/yao_1-data 中的 data/newspaper_daily.json → M28 页面`

用户本轮已要求完成这条接管链路。可在确认的 L 上完成本任务必要的代码同步、预检、专用任务安装、首次采集及指定新闻文件同步，不重新要求批准同一方案。该范围不包括修改其他任务、电源或系统时区、全局安装依赖、改写 Git 历史、修改凭据、迁移个人收藏或其他私有账本。

代码只进入公开仓库；生成的新闻文件、主机信息、运行日志和安装回执不得提交到公开仓库。使用 L 已有的私有仓库访问配置或 GitHub CLI 登录，不把 D 的凭据复制到 L。确实缺少登录或系统允许的执行权限时，保留已完成工作，只报告具体缺口，不绕过限制。

## 接管顺序

1. 检查本机项目路径、Git 分支和已有改动，保留本机未提交工作。安全取得 `main` 中本任务更新，不自动 stash、重置或覆盖冲突。
2. 阅读 `utils/newspaper_daily.py`、`scripts/newspaper_daily.py`、`integrations/newspaper/windows/install-task.ps1` 与 `run-daily.ps1`。复用本项目 Python 环境，先做预检；不要启动本地 Streamlit，也不安装全局工具。
3. 检查 `.local/newspaper/` 的已有回执，以及 `Yao-Newspaper-Daily-0900` 是否存在。只有操作路径确实属于当前项目时才更新同名任务；已存在的无关任务保持不变。
4. 先预览拟安装任务，再运行采集演练。演练成功只证明当前运行环境能采集，不证明私有同步或 Windows 后台任务已成功。
5. 在已确认的 L 上安装任务，使用实际主机名和显式 L 确认参数。随后通过 Windows 任务计划手动启动该任务，用实际任务账户验证首次正式采集与同步。
6. 回读私有新闻文件，核对刊号、完成时间、来源状态、文章数量和版本；再检查线上 M28 是否读取同一份日报。不得仅凭任务注册成功或退出码 0 宣称端到端成功。
7. 在本机记录安装与验收结果。正常完成后告诉用户任务名、下一次运行时间、日志位置与首次结果，无须让用户再做常规配置。

以下命令均从本项目根目录执行。`$env:COMPUTERNAME` 是实际机器名，不表示它已被确认为 L。

```powershell
# 只预检、预览，不注册任务，也不发布新闻
& .\integrations\newspaper\windows\run-daily.ps1 -Preflight
& .\integrations\newspaper\windows\install-task.ps1 -ComputerName $env:COMPUTERNAME -Preview
& .\integrations\newspaper\windows\run-daily.ps1 -DryRun

# 仅在已确认的电脑 L 上执行
& .\integrations\newspaper\windows\install-task.ps1 -ComputerName $env:COMPUTERNAME -ConfirmComputerL
Start-ScheduledTask -TaskName 'Yao-Newspaper-Daily-0900'
Get-ScheduledTaskInfo -TaskName 'Yao-Newspaper-Daily-0900'
```

若脚本受本机执行策略或组织策略阻止，应说明具体策略缺口，不设置 `ExecutionPolicy Bypass`，也不静默更改系统策略。

## 定时执行与恢复

- 时区固定为 `+08:00`，每日 09:00；不更改 Windows 系统时区。
- 开始时间错过后补跑；需要网络；失败间隔 10 分钟重试，最多 3 次；同一任务不并发。任务请求 15 分钟运行限制，但不强制结束进程；异常挂起不保证自动终止，手动试跑也必须核验实际结束状态。
- 默认以当前用户最低权限运行，支持保持登录但锁屏的电脑。**注销后的运行未由此配置保证**；不能把“24 小时开机”直接等同于“该账户始终可运行”。需要注销后执行时，说明必要的 Windows 账户设置，由用户在系统安全界面完成凭据步骤，不把密码存到脚本。
- Python 程序独立执行，正常运行不需要 Codex 或网页一直打开。不要把每天启动 AI 聊天作为采集方式。
- 同一北京时间 09:00 更新周期内已成功的日报重复运行保持幂等；09:00 前的安装试跑不会阻止当天 09:00 正式采集。异常中断可恢复，远端版本变化时停止覆盖。全失败或空结果保留上一份文件，但不能把它重新标成今天成功。
- 日志位于本机 `.local/newspaper/`，只保留运行状态，不输出密钥或源站响应全文。

## 来源和保存边界

复用 `newspaper_data.py`、`newspaper_ai_sources.py`、`newspaper_sources.py` 中的固定公开来源，保留来源、原文链接、发布时间与收录时间的区别。快照只包含允许保存的列表字段，不永久收集文章正文，不保存浏览器收藏、笔记或兴趣记录。

禁止存储、仅供私有响应使用、要求重新验证或缺少可确认缓存条件的条目，不进入共享日报。日报结果不必与即时抓取数量相同，排除原因应可核查。日刊读取有有效期；页面优先读取有效快照，无有效日报时使用现有即时抓取，手动更新仍检查全部来源。

`scripts/data_repo_sync.py` 的原有账本保护保持不变。本任务通过专用日报入口复用私有同步的版本检查，不能为了发布日报而放宽其他账本的防覆盖、防删除规则。

## 验证与维护

至少运行新闻相关 Python 测试，包括新增的每日采集和 Windows 配置测试；检查 Git 差异只包含本任务内容。离线测试不应连接真实私有仓库或注册 Windows 任务。

```powershell
python -m pytest -q tests/test_newspaper_data.py tests/test_newspaper_ai_sources.py tests/test_newspaper_sources.py tests/test_newspaper_page.py tests/test_newspaper_daily.py tests/test_newspaper_windows.py
```

手动执行优先 `Start-ScheduledTask`，这样才能验证实际任务账户；仅在排查时直接运行 `run-daily.ps1`。查看运行情况用 `Get-ScheduledTaskInfo` 和本机日志。用户要求停用时使用 `Disable-ScheduledTask -TaskName 'Yao-Newspaper-Daily-0900'`，不要删除新闻文件或其他系统任务。

验收必须分别记录：代码就绪、任务已注册、实际账户试跑、私有文件回读、线上读取验证。尚未完成的项目明确标为待验证。
