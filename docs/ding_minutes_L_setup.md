# Recorder_笔记：L 电脑运行配置指南

这份指南用于把板块 11 从当前电脑迁移到 L 电脑，并让 L 电脑每天 19:00 自动扫描 Downloads 文件夹中符合命名规则的 Word 文件。

## 一、在 L 电脑拉取最新代码

进入项目目录后运行：

```powershell
git pull
```

如果 L 电脑还没有这个项目，先从 GitHub 克隆仓库。

## 二、安装依赖

在项目目录运行：

```powershell
python -m pip install -r requirements.txt
```

这里会安装读取 Word 文件需要的 `python-docx`，以及调用 DeepSeek 需要的 `requests`。

## 三、检查扫描路径

打开：

```text
config/ding_minutes.ini
```

确认这一行是 L 电脑真实存在的路径：

```ini
watch_dir = C:\Users\Yao\Downloads
```

如果 L 电脑路径不同，只改这一行即可。不要把 API key 写进这个文件。

## 四、配置 DeepSeek API Key

API key 只放在 L 电脑本机环境变量里，不写进代码，不写进 GitHub。

在 PowerShell 里运行下面命令，把 `你的真实key` 替换成 DeepSeek 控制台里的 key：

```powershell
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "你的真实key", "User")
```

设置后，重新打开 PowerShell 或重启电脑，让环境变量生效。

检查是否配置成功：

```powershell
[Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
```

如果能看到一串 key，说明 L 电脑本机已经配置好。不要截图发到公开位置，也不要提交到 GitHub。

## 五、手动试运行一次

在项目目录运行：

```powershell
python scripts\scan_ding_minutes.py
```

正常情况下会看到类似：

```text
Ding minutes scan finished: found=1, processed=1, skipped=0, failed=0
```

如果显示文件夹不存在，检查 `config/ding_minutes.ini` 里的 `watch_dir`。

如果显示未配置 `DEEPSEEK_API_KEY`，说明环境变量没有生效，重新打开 PowerShell 后再试。

## 六、设置每天 19:00 自动运行

打开 Windows“任务计划程序”，新建基本任务：

- 名称：`Ding Minutes Scan`
- 触发器：每天
- 时间：19:00
- 操作：启动程序
- 程序或脚本：填写 L 电脑上的 Python 路径，例如 `python`
- 添加参数：

```text
scripts\scan_ding_minutes.py
```

- 起始于：填写项目目录，例如：

```text
E:\github\yao_1
```

如果 L 电脑项目目录不同，就填 L 电脑实际目录。

## 七、打开板块 11 查看结果

启动 Streamlit 项目后，进入：

```text
Recorder_笔记
```

页面可以查看：

- 原始转写
- AI 整理稿
- 处理状态
- 错误信息
- 备注

备注可以手动填写，用来标记“已写新闻稿”“待核实”“后续做汇报素材”等。

## 八、安全提醒

- 不要把 DeepSeek API key 写进 `config/ding_minutes.ini`。
- 不要把 API key 写进 `.py` 文件。
- 不要把带 key 的截图发到公开位置。
- 如果怀疑 key 泄露，立即到 DeepSeek 控制台停用旧 key，重新生成新 key。
