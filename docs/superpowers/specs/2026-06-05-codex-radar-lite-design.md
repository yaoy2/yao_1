# Codex Radar Lite Design

## 目标

在 `yao_1` 仓库内新增一个和 `pages/` 同级的轻量监控模块，用 GitHub Actions 每小时采集公开信号，判断 Codex 额度重置窗口概率，并在高概率、窗口开启或窗口关闭时通过钉钉机器人主动提醒。

## 边界

- 不做 Docker，不做常驻服务。
- 不做个人微信，不做邮件兜底。
- 不把钉钉 webhook、签名密钥写进代码；只从 GitHub Secrets 读取。
- 第一版不复制 Codex Radar 原站 UI，也不做 IQ 测试。

## 架构

`codex_radar_lite/` 是独立 Python 包，包含采集、规则判断、输出、推送和命令行入口。`config/` 存放公开源和规则阈值，`data/` 存放当前状态、历史记录和证据，`codex_radar_lite/site/` 提供 GitHub Pages 可展示的静态页面。

GitHub Actions 每小时运行 `python -m codex_radar_lite.cli`，脚本读取公开来源，生成静态 JSON 和 RSS 文件。状态变化达到推送条件时，脚本读取 `DINGTALK_WEBHOOK` 和可选 `DINGTALK_SECRET` 发送钉钉 Markdown 消息。

## 判断规则

第一版采用规则引擎：

- 官方来源出现 Codex 与 usage limit、rate limit、quota、credit 等词，增加关注分。
- 出现 will reset、resetting limits、reset usage limits 等词，判定为疑似窗口开启。
- 出现 limits have been reset、restored to 100%、fully recovered 等词，判定为疑似窗口关闭或额度恢复。
- 刚记录过 closed 的 24 小时内降低分数，避免重复提醒。

## 验证

使用 `unittest` 验证规则判断、信号提取、钉钉推送触发条件和 JSON/RSS 输出。项目规则要求不启动 Streamlit，因此本次只做代码级和纯静态文件验证。

