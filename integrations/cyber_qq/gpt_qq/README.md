# 赛博QQ · GPT 小号

[返回赛博QQ项目入口](../README.md)。

使用 OpenAI 官方 API、AstrBot 4.29.3 与 NapCat 4.18.41。默认模型为 `gpt-6.1-sol`，仅响应配置的主人私聊，支持文字、图片和本实例的持久化会话。人格为普通中文 GPT 助手，不导入其他机器人的人格、记忆、账号或插件数据。

运行目录为 `.local/gpt_qq/`，安装时写入本地忽略规则。API Key、账号、管理密码、聊天记录和 QQ 登录缓存均只保存在此目录，不提交到 Git。配置启用 API 的 `store: false`；这不表示或承诺提供商的其他数据保留政策。

## 安装

`install.py` 从已安装且版本匹配的本机实例**只复制程序文件和页面静态资源**，创建独立 Python 环境，不修改源实例。依赖版本复用 `../whale_companion/requirements.lock.txt`；不复制其配置、会话、插件数据、QQ 缓存或虚拟环境。

在当前进程设置 `OPENAI_API_KEY` 后运行（不要把密钥写在脚本、命令参数或聊天里）：

```powershell
py -3 -B integrations/cyber_qq/gpt_qq/install.py --source-runtime <已安装实例目录> --root .local/gpt_qq --python <Python3.12路径> --uv <uv路径> --bot-qq <小号> --owner-qq <主人QQ>
```

安装只接受空目标目录，不覆盖已有账号。新复制的 NapCat 内有两处版本校验的数据目录适配，配合本实例入口将 QQ 登录和账号数据定位到 `.local/gpt_qq/qq-data/`；不改变其他实例或系统 QQ 的目录设置。版本不匹配时拒绝应用适配。

## 运行

```powershell
& integrations/cyber_qq/gpt_qq/manage.ps1 -Action start-all
& integrations/cyber_qq/gpt_qq/manage.ps1 -Action status
& integrations/cyber_qq/gpt_qq/manage.ps1 -Action stop-all
```

- GPT 管理页：<http://127.0.0.1:6189>
- QQ 登录页：<http://127.0.0.1:6100>
- 本机消息接口：`ws://127.0.0.1:6199/ws`
- 本地登录信息：`.local/gpt_qq/local-access.json`
- 登录二维码：`.local/gpt_qq/napcat/napcat/cache/qrcode.png`
- 日志：`.local/gpt_qq/logs/`

仅为目标小号生成消息连接配置；扫码后须回读登录账号，再让主人发送真实私聊，确认 QQ 入站、GPT 请求和 QQ 回复均成功。API 连通或进程运行不能代替此项验收。实际验证目标账号后，更新本地 `installation.json` 的 `qq_account_logged_in`，再按需要运行 `-Action autostart-enable`；任务名为 `GPTQQ-<小号>`。`autostart-disable` 仅关闭自启，停止当前运行另用 `stop-all`。

管理命令只操作此目录的进程和专用任务。管理接口仅监听本机，不启用群聊回复、主动消息、B站账号、电脑操作或额外插件。可在独立管理页调整人格和模型；相关能力需另行配置和验证。

## 检查

```powershell
py -3 -B -m unittest integrations.cyber_qq.gpt_qq.test_prepare
```

配置依据：[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、[AstrBot](https://github.com/AstrBotDevs/AstrBot)、[NapCat](https://github.com/NapNeko/NapCatQQ)。版本升级前应重新核验 QQ 数据目录适配和真实收发。
