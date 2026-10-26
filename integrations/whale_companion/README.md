# 小鲸：可扩展的 QQ / B站陪伴实例

独立 AstrBot 实例，使用 DeepSeek 作为聊天及图片理解模型；陪伴、长期记忆、B站浏览是独立插件。运行数据保存在仓库忽略的 `.local/whale_companion/`，不与 M31 工作群归档共用账号、模型配置或记忆。

## 当前状态

- 已安装 AstrBot 4.29.3、陪伴 6.7.0、记忆 2.3.2、BiliBot 1.7.2，以及独立的 NapCat 4.18.41 和 FFmpeg 9.0.2。
- 已准备“小鲸”人格、私聊白名单、低频主动策略、夜间免打扰、字幕/画面证据区分和只读视频工具。
- 管理页与三个插件的加载已验证；依赖一致性、初始化保留配置、停止/重启和本地备份已验证。
- QQ、B站和模型账号未绑定；真实聊天、视频观看、主动推送和评论区 @ 尚未验收。主动任务与 QQ 接口在账号就绪前关闭，尚未设置开机自启。

## 日常使用

在本目录双击 `启动鲸鱼娘.bat`，随后打开 <http://127.0.0.1:6188>。管理页只允许本机访问。首次随机登录信息在 `.local/whale_companion/local-access.json`，不要提交或发给别人。停止使用 `停止鲸鱼娘.bat`。

```powershell
./integrations/whale_companion/manage.ps1 -Action status
./integrations/whale_companion/manage.ps1 -Action start
./integrations/whale_companion/manage.ps1 -Action stop
./integrations/whale_companion/manage.ps1 -Action qq-start
./integrations/whale_companion/manage.ps1 -Action qq-stop
./integrations/whale_companion/manage.ps1 -Action backup
```

`qq-start` 只启动本实例附带的 NapCat；登录页为 <http://127.0.0.1:6099>，令牌也在本机登录信息文件中。选择机器人 QQ 小号扫码，不把工作用账号接入。QQ 桥需要单独停止。备份前必须停止两者，避免数据库和文件处于不同时间点。

备份包含 AstrBot 的配置、人格、插件、聊天/长期记忆及 NapCat 配置，存入运行目录的 `backups/`。它不包含 Python 环境、FFmpeg 或 QQ 客户端自己的登录缓存；恢复后可能需要重新扫码。备份也含凭据，只保留在私人位置。恢复应解压到独立目录核对，不能覆盖正在运行的实例。

## 账号绑定顺序

1. **模型提供商 → deepseek**：在本机页面填写自己的 API Key，保存，再启用 `deepseek-whale` 模型。默认模型 `deepseek-flash`，支持图片和工具；单次输出上限 4096，先用非思考模式。密钥无需发送到聊天。
2. **配置文件 → 访问控制**：用 `whale-qq:FriendMessage:主人的QQ号` 替换预置的阻断占位白名单，并把主人的 QQ 号设为管理员。不要清空白名单：本版 AstrBot 的空白名单表示不限制。
3. **NapCat**：扫码登录专用 QQ 小号，在网络配置创建 WebSocket 客户端，地址 `ws://127.0.0.1:6198/ws`、消息格式 `array`、Token 使用本机 `local-access.json` 中的 `onebot_token`。随后在 AstrBot 的“机器人”页启用 `whale-qq`。
4. **陪伴面板**：把主人 QQ 号设为私聊目标，选“小鲸”为主人格；收到真实私聊后检查用户身份。确认唯一目标后再打开目标预热、主动消息和日程。默认目标每天最多 4 次、至少间隔 120 分钟、23:00–08:30 安静；不回应会降频。
5. **BiliBot 控制中心**：扫码登录角色的 B站账号，填写主人的 B站 UID 和 QQ 私聊 UMO。QQ UMO 可在私聊执行 `/biliUMO` 获取。检查模型、FFmpeg、字幕/截帧能力后，再开启“主动看视频”，每天最多 2 个视频、给主人 QQ 分享最多 2 次且至少间隔 180 分钟。
6. 初始不自动点赞、投币、收藏、关注、评论或发布动态。需要评论区 @ 主人时，补齐主人 B站名字/UID，把推荐通道切到相应选项并实测；其他写操作和动态单独开启。
7. 用真实账号验收聊天、重启后记忆、一个有字幕视频和一个无字幕视频、主人接收分享，再启用 L 上的登录后自动启动。电脑关机、休眠或账号掉线时无法持续响应。

日限额是各插件各自的动作/调用限制；陪伴插件的 60K 软限额、100K 硬限额不包含 AstrBot 普通聊天和 BiliBot 的全部模型消耗，不是整个账户的费用上限。

## 后续调整与扩展

| 需要改什么 | 入口 |
|---|---|
| 名字、说话方式、性格、兴趣 | 人格设定 → 小鲸；陪伴面板 → 配置 / 提示词 |
| 主动频率、安静时段、日程、日记 | 陪伴面板 → 主动 / 配置 |
| 记忆查看、修正、删除 | 我会牢牢记住你 |
| 浏览兴趣、画面模型、分享方式、次数 | BiliBot 控制中心 |
| 更换模型、API 地址、单次输出 | 模型提供商 |
| 新增或移除能力 | 插件管理；先停机备份，单次更新一个插件并验证 |

`profiles.json` 和 `persona.txt` 只用于首次初始化。重新运行安装脚本不会用它们覆盖你在页面里改过的设置。新增功能优先用插件和设置，不直接改第三方源码。没有安装生图、现实设备、QQ空间等额外扩展。

## 重建环境

需要已有的 Windows Python 3.12 与 uv。运行以下命令时填入本机真实路径；不安装全局工具、不修改系统 PATH。

```powershell
./integrations/whale_companion/install.ps1 -PythonPath '现有Python3.12的完整路径' -UvPath '现有uv.exe的完整路径'
```

`versions.lock.json` 固定下载地址、版本、提交与 SHA-256；`requirements.lock.txt` 固定本次验证的 160 个 Python 包。安装器保留已存在的程序目录及配置，拒绝在实例运行时同步依赖。更新版本应另做验证，不能把重新安装当作升级操作。

本实例的运行日志在 `.local/whale_companion/logs/`，账号与记忆均不进入公开仓库。上游项目及其许可证保留在各自的安装目录：

- [AstrBot](https://github.com/AstrBotDevs/AstrBot)
- [陪伴插件](https://github.com/menglimi/astrbot_plugin_private_companion)
- [长期记忆插件](https://github.com/menglimi/astrbot_plugin_memory_companion)
- [BiliBot](https://github.com/chenluQwQ/astrbot_plugin_bilibili_ai_bot)
- [NapCat](https://github.com/NapNeko/NapCatQQ)
- [FFmpeg Windows builds](https://www.gyan.dev/ffmpeg/builds/)

DeepSeek 模型能力依据 [官方文档](https://api-docs.deepseek.com/quick_start/pricing/) 核对于 2026-10-26；实际账号可用性和消费以服务端为准。
