# Grok Bot 与 QQ 单次验证桥

复用已登录的 NapCat，在原装 Grok Bot 的 webhook routine 与主人私聊之间验证收发。没有调用 xAI 模型 API，也不修改订阅或自动充值。此目录仅是源码；运行前须完成账号与订阅检查、取得 routine 地址和临时 HTTPS 回调地址。

配置保存于仓库忽略的 `.local/grok_qq_bridge/config.json`，不得提交凭据。字段：

```json
{
  "whale_runtime_root": "E:\\gh\\yao_1\\.local\\whale_companion",
  "grok_webhook_url": "https://实际routine端点",
  "grok_webhook_token": "实际Bearer密钥",
  "public_callback_url": "https://临时隧道域名/callback",
  "listen_port": 6209,
  "request_timeout_seconds": 180,
  "max_text_chars": 1000,
  "max_messages": 3,
  "run_seconds": 900,
  "astrbot_guard_confirmed": false,
  "subscription_preflight_confirmed": true,
  "subscription_preflight_at": "含时区的本次ISO时间"
}
```

每次运行前重新确认 Grok Bot 使用现有订阅、On-Demand 未启用，并更新检查时间。程序只验证这份人工记录在一小时内，**不会据此声称已读取账户计费状态**。

使用现有小鲸 Python 环境运行 `bridge.py --config <配置绝对路径> --preflight` 只读检查 QQ 在线、账号绑定与主人白名单；去掉 `--preflight` 才会开启测试。回调服务仅监听 `127.0.0.1`，隧道由操作者另行建立、核对和关闭。

桥只接收主人私聊的 `/grok-test 文本`。提交给 Grok 的 JSON 仅有 `request_id`、`text`、`callback_url`、`callback_token`；Grok 必须向指定地址 POST `{"request_id":"原值","callback_token":"原值","text":"回复正文"}`。回调不能指定 QQ 接收人。一次只能有一条在途请求，最多三条，最多运行十五分钟；超时、未知请求、错误令牌、重放、超长内容均拒绝，网络失败不自动重试。

NapCat Debug 适配器仅在内存中创建/复用，不改 QQ 配置或重启服务。它会提供全量实时事件，桥在本机立即丢弃非测试事件，不保存、不输出、不发给 Grok。停止时只断开本程序的 WebSocket，避免关闭别人正在使用的调试台；NapCat 会清理闲置适配器。

**重复回复边界：** 旁路监听不能阻止现有小鲸回复。`guard_plugin.py` 是独立插件源码，只有经操作者安装加载后才生效；它以高优先级阻断主人 `/grok-test` 前缀，加载三十分钟后自动失效。普通消息仍走原链路。启动桥前须实际核验 guard 已加载且剩余有效时间覆盖本次运行，再设置 `astrbot_guard_confirmed=true`；程序未收到这项确认会拒绝启动（只读 `--preflight` 不要求）。验证后卸载 guard；本目录不会自动安装它。

离线测试：`python -m unittest integrations.grok_qq_bridge.test_bridge`。这些检查不连接 QQ/Grok，不能替代真实入站、云端回调和主人收到回复的验收。
