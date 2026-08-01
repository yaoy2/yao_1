# 公众号监控归档（mp_watch）

免费、全自动、数据只落在 **E 盘本仓库**（`E:\github\yao_1`），不写 C 盘用户目录。

## 解决什么问题

关注的公众号可能删帖/隐藏。本工具按你设的间隔（默认 2 小时）自动：

1. 从免费发现源（RSS / JSON）拉最新链接  
2. 本地去重  
3. 调用现有 `wechat_core` 抓正文+图片，存到 Obsidian（默认 `raw`）

**不依赖你刷手机。** 电脑任务计划在跑、发现源可用即可。

## 目录约定（全部在 E 盘项目内）

| 路径 | 作用 |
|---|---|
| `config/mp_watch_sources.json` | 两个公众号 + RSS 地址 |
| `config/mp_watch_sources.example.json` | 配置样例 |
| `data/mp_watch_state.json` | 已见 URL / 归档结果 |
| `logs/mp_watch_YYYY-MM-DD.log` | 运行日志 |
| `mp_watch/` | 监控代码包 |
| `公众号监控.bat` | 一键跑一轮 |

发现源服务（如自建 We-MP-RSS）的数据目录也请放在 **E 盘**（例如 `E:\github\yao_1\tools\we-mp-rss-data`），不要装到 C 盘用户目录。

## 使用步骤

### 1. 准备发现源（免费）

任选其一，目标只有一个：给每个公众号一个能列出最新文章链接的 RSS 或 JSON。

- 自建 We-MP-RSS / 同类开源（扫码授权后订阅 2 个号）  
- 其他仍可用的免费 RSS 源  

把每个号的 feed 地址填进配置。

### 2. 编辑配置

打开：

`E:\github\yao_1\config\mp_watch_sources.json`

- 改 `name` 为真实公众号名  
- 填 `feed_url`  
- 把对应源的 `enabled` 设为 `true`  
- `poll_hours` 默认 `2`（任务计划间隔与此一致即可；脚本本身每调用跑一轮）  
- `archive_type` 默认 `raw`（与 `wechat_core` 的 raw 目录一致）

### 3. 试跑（不真抓正文）

在仓库根目录：

```bat
公众号监控.bat --dry-run
```

或：

```bat
python -m mp_watch --dry-run
```

应能看到发现的标题与链接；状态写入 `data/mp_watch_state.json`。

### 4. 正式归档一轮

```bat
公众号监控.bat
```

### 5. 任务计划（全自动）

1. 打开「任务计划程序」  
2. 创建基本任务 → 每 2 小时（或 1 小时）  
3. 操作：启动程序  

- 程序：`E:\github\yao_1\公众号监控.bat`  
- 起始于：`E:\github\yao_1`  

建议勾选：插电时运行、唤醒计算机运行（按你机器情况）。

## 失败怎么看

| 现象 | 原因分层 |
|---|---|
| 日志说没有启用的 sources | 配置里 `enabled` 仍是 false，或没填 feed |
| 源拉取失败 | 发现源挂了 / 要重新扫码 / 地址错 |
| 有链接归档失败 | 文已删、验证码、微信风控；看 `logs/mp_watch_*.log` 与 wechat 的 failed 日志 |
| 任务没跑 | 电脑休眠、未登录、任务计划未启用 |

## 你已定下的产品约束

- 全自动，不靠刷手机  
- 轮询 1～2 小时即可（默认 2）  
- 免费优先  
- 项目清晰，数据在 E 盘仓库内  

## 尚未由你填写的两项

1. 两个公众号的真实名称与对应 `feed_url`  
2. 是否把任务计划间隔定为 1 小时还是 2 小时（默认按 2）  
