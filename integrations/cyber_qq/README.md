# 赛博QQ

赛博QQ统一管理两个 QQ AI 实例：呆小鲸与 GPT 小号。两者共享项目入口，各自保留账号、模型配置、人格、聊天记录、记忆、登录数据和启动任务。M31 工作群归档不属于本项目。

| 实例 | 用途 | 模型 | 源码与使用说明 | 本地运行目录 |
|---|---|---|---|---|
| `whale` · 呆小鲸 | 陪伴、长期记忆、B站工具 | DeepSeek | [whale_companion](whale_companion/README.md) | `.local/whale_companion/` |
| `gpt` · GPT 小号 | 文字、图片和持续对话 | OpenAI GPT | [gpt_qq](gpt_qq/README.md) | `.local/gpt_qq/` |

## 统一管理

双击本目录的 `查看赛博QQ状态.bat` 可查看两个实例。以下命令在仓库根目录执行。默认只查看状态；分别启动时必须明确指定实例。

```powershell
# 查看两个实例
& integrations/cyber_qq/manage.ps1

# 只查看其中一个
& integrations/cyber_qq/manage.ps1 -Instance gpt -Action status

# 按需启动一个实例的后台与 QQ 接口
& integrations/cyber_qq/manage.ps1 -Instance gpt -Action start-all
& integrations/cyber_qq/manage.ps1 -Instance whale -Action start-all

# 停止一个实例，或停止两者
& integrations/cyber_qq/manage.ps1 -Instance gpt -Action stop-all
& integrations/cyber_qq/manage.ps1 -Action stop-all
```

`start` / `stop` 只操作模型后台，`qq-start` / `qq-stop` 只操作所选实例的 QQ 接口，`start-all` / `stop-all` 操作该实例的两个组件。`-DryRun` 仅输出目标和动作，不启动或停止程序。不支持同时启动两个实例，避免一次操作意外恢复另一个已暂停的小号。

登录自启按实例单独控制。`autostart-disable` 不停止当前进程；完整暂停应先 `stop-all`，再 `autostart-disable`。呆小鲸另有 `backup` 和 `open` 动作。尚未安装的实例在状态查询中显示未安装；拉取代码不会自动安装、登录或启用任何任务。

## 本机入口与隔离

| 实例 | 管理页面 | QQ 登录页面 | 本机消息接口 |
|---|---|---|---|
| 呆小鲸 | <http://127.0.0.1:6188> | <http://127.0.0.1:6099> | `ws://127.0.0.1:6198/ws` |
| GPT 小号 | <http://127.0.0.1:6189> | <http://127.0.0.1:6100> | `ws://127.0.0.1:6199/ws` |

页面需要对应组件运行才能访问。凭据、真实 QQ 号码、登录缓存、聊天与记忆数据只保存在本机忽略目录，不上传公开 GitHub 仓库。项目归并只调整源码和管理入口，不搬移或混合这两套运行数据。

原 `integrations/whale_companion/`、`integrations/gpt_qq/` 中的安装与启动入口保留为转发脚本；原呆小鲸批处理文件和计划任务路径继续有效。后续修改应在本目录完成，不在兼容目录复制第二套实现。

## 接入与验收

两个实例分别安装、配置和验收。API 能返回、管理页能打开、进程正在运行，都不能代替真实 QQ 收发验证。先核对实际登录的小号，再用白名单主人账号私聊，验证入站、模型处理和回复送达；成功后才启用对应实例的登录自启。

QQ 需要账号验证或限制恢复时，保留配置并暂停该号的登录，按手机 QQ 官方提示处理后再继续；不因此恢复另一个实例。单纯归并项目或更新源码，也不恢复已经暂停的实例。

## 检查

```powershell
py -3 -B -m unittest integrations.cyber_qq.test_management integrations.cyber_qq.gpt_qq.test_prepare
py -3 -B -m unittest discover -s integrations/cyber_qq/whale_companion -p test_*.py
```

这些检查覆盖管理目标、旧目录兼容、账号隔离配置和现有视频记忆辅助逻辑；实际登录、收发与插件能力仍需在各自实例中验证。
