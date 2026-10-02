# 钉钉当天聊天整理（Windows / 电脑 L）

独立于 Streamlit 的本机工具。每天北京时间 **22:00** 从已打开、已登录的钉钉桌面界面读取当天记录，输出中文 Markdown 和可核对的 JSON。

**当前交付边界：** 已实现采集适配器、当天过滤、原文整理、私有结果保存及 Windows 定时脚本。钉钉版本之间的控件结构可能不同，首次必须在电脑 L 完成界面适配和一次真实试跑。本次开发环境的桌面工具返回窗口归属错误，未完成真实钉钉聊天采集验证；单元测试通过不能替代这一步。本版使用 Windows UI Automation，不含 OCR；若钉钉不向 UIA 暴露会话、日期或正文，程序会停止或报告缺口，需要继续适配。

## 整理范围

在 `setup.ps1` 中填写两个完整会话名称和本人显示姓名，信息只写入本机 `config.local.json`。

1. **指定联系人**：当天双方的消息。
2. **指定群**：当天明确由本人发出的消息；同事的群消息不进入结果。
3. **其他单聊**：当天有消息的其他联系人，保留双方当天的消息，不包含其他群。指定联系人不会重复计入本部分。

“当天”固定为北京时间 00:00 至本次运行开始时刻。每晚 22:00 启动，之后新产生的消息不属于本次结果。程序不把上次成功到这次成功之间当作“当天”，不会在第二天自动补抓昨天。当天任一方有消息即属于当天单聊，不要求双方都发过消息。

日期不明、本人身份冲突、重名会话、翻页未完成、未知会话类型均明确报告，不能把“没有采集到”当作“当天没有消息”。置顶会话不会成为提前停止扫描的理由。图片、语音和附件仅记录界面可读信息，不下载附件，也不宣称已理解其中内容。

整理采用本地规则：对象分组、消息数量、按原文提示词定位需跟进线索、保留发送人／时间／正文依据。线索不是已确认的待办，不自动推断事项完成状态。没有模型密钥，也不会把聊天发送到外部模型服务。

## 在 L 上准备

先在电脑 L 的现有仓库同步代码。保留原有修改；若 Git 提示冲突，先处理冲突，不使用强制覆盖。

```powershell
git status --short
git pull --ff-only
cd integrations\dingtalk_daily
.\setup.ps1
```

需要已有 **Python 3.11 或更高版本**。安装脚本仅在本项目 `.venv` 安装依赖，不安装全局工具，不创建定时任务。找不到 Python 时，可以指定已有解释器：

```powershell
.\setup.ps1 -PythonExecutable 'C:\你的Python目录\python.exe'
```

按提示填写指定联系人、指定群、本人在钉钉里的准确显示姓名；本人在群中有其他显示名时，用逗号一起填写。目标姓名不使用模糊匹配。默认结果目录是：

```text
%LOCALAPPDATA%\YaoTools\DingTalkDaily
```

完整会话名称、本人姓名和界面适配保存在 `config.local.json`，被 Git 忽略，**不会随 git pull 迁移**。输出目录必须在公开代码仓库之外。此项目不读写原 Recorder 数据，也不接入工具箱的云数据备份。

## 首次界面适配和试跑

保持 L 桌面解锁、钉钉已登录，进入完整会话列表。用下列命令按当前实际控件完成首次适配：

```powershell
.\.venv\Scripts\python.exe -X utf8 main.py calibrate
.\.venv\Scripts\python.exe -X utf8 main.py doctor
.\.venv\Scripts\python.exe -X utf8 main.py run
```

`calibrate` 不预置未经验证的钉钉控件 ID，按当前界面生成本机配置。它不会登录账号、发送消息或操作输入框。请阅读校准提示，保持所需列表与示例会话可见。`doctor` 通过仅说明控件可读；首次真实试跑后应打开 `整理.md`，核对两个指定会话、本人归属、日期边界、其他单聊和缺口说明。

如果校准无法找到可读结构，运行下列诊断，供在 L 上继续适配：

```powershell
.\.venv\Scripts\python.exe -X utf8 main.py inspect
```

诊断文件保存在本机结果目录的 `diagnostics` 下，可能包含当前可见聊天文字。不要提交到公开仓库，也不要整份公开分享。日期或正文未暴露时，不应仅把 `calibration_ok` 手动改成 `true`。

## 安装每天 22:00 任务

完成适配与试跑后，在 **L** 上运行：

```powershell
.\register_task.ps1
```

脚本先检查本机配置和钉钉可读性，再为当前 Windows 用户注册 `YaoTools.DingTalkDaily`，回读核验任务设置及下一次运行时间。同名但不属于本项目的任务不会被覆盖。更新本项目已注册任务时可再次运行同一命令。

运行条件：电脑开机，当前 Windows 用户已登录并保持桌面解锁，钉钉已登录且完整会话列表可访问。读取时会切换钉钉中的会话并滚动消息，可能改变界面位置或未读状态；请避免同时操作钉钉。工具不发送、编辑、撤回或删除消息，不读取客户端私有数据库，不操作认证窗口。

任务使用交互式普通用户权限，无管理员提权、无密码保存。电脑需为中国标准时间（UTC+08:00）；脚本只检查，不改系统时区。不会唤醒电脑、跨日补跑或无限重试；最长运行 45 分钟，并阻止同一任务并行启动。操作系统脚本策略如阻止运行，需采用所在单位允许的方式处理，本项目不会自动绕过或改写策略。

查看和暂停已安装任务可在 Windows“任务计划程序”中找到上述名称。仅拉取代码或运行 `setup.ps1` 不代表任务已启用。

## 查看结果和失败原因

```text
DingTalkDaily/
  2026-10-02/
    220000-xxxxxxxx/
      整理.md           中文整理与原文依据
      records.json      仅已通过范围过滤的记录
      status.json       本次运行状态、起止时间
    latest.json         最近一次执行
    latest_success.json 最近一次完整执行（失败不会覆盖）
  diagnostics/          手动生成的私人界面诊断
  logs/                 定时入口日志
```

每次运行使用新的目录，不覆盖历史成果。`complete` 表示当前适配器的扫描和证据检查通过；`partial` 表示存在缺口，`failed` 表示未完成。`running` 长时间不结束通常表示进程中断或任务超时，不能当作成功。JSON 和 Markdown 写入后会回读核验。

命令退出码：`0` 本次检查通过；`1` 失败；`2` 部分完成；`3` 已有运行。若无日报，先看 `logs/runner-YYYYMMDD.log` 和本次 `status.json`。登录、解锁和账号选择由本人完成。

## 开发验证

在本项目目录运行，不访问真实钉钉：

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -File .\scripts\test_windows_scripts.ps1
```

核心函数 `build_report(capture, config, run_at)` 不访问网络和文件。采集器只返回结构化记录；只有严格按当日和对象过滤后的报告会保存，未过滤的采集内容不落盘。离线重放用于排查采集格式，不可证明桌面读取成功：

```powershell
.\.venv\Scripts\python.exe -X utf8 main.py replay --input 'C:\私人目录\capture.json'
```

重放输出标记为 `replay`，不更新真实采集的 `latest_success.json`。

技术参考：[pywinauto UIA 支持](https://pywinauto.readthedocs.io/en/latest/getting_started.html)、[Windows 每日任务触发器](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasktrigger)。
