# M14 待办聊天入口

手机/网页 ChatGPT 和本机 Work/Codex 共用 `data/todo_items_backup.md`。新增、日期识别、查询、完成归档继续调用 `utils/todo_db.py`，不创建提醒、日历或通知。

## 换电脑使用

`git pull` 能拿到代码，但不会安装依赖、同步私人凭据或安装聊天连接。Windows 首次运行（需要 Python 3.11+ 与 Codex CLI）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_m14.ps1
```

脚本在项目内建立 `.venv-m14`，注册本机 `m14` MCP，使用当前仓库的绝对路径；不改变全局 Python。凭据优先复用本机 `.streamlit/secrets.toml` 中的 `GITHUB_BACKUP_TOKEN`，也可在被 Git 忽略的 `.env.m14` 中设置环境变量；没有配置 token 时，本机入口可复用已登录的 GitHub CLI（`gh`），不会提取或保存登录凭据。不要把密钥提交到仓库。连接后新开 Work/Codex 对话。

其他系统可创建项目虚拟环境，安装 `integrations/m14/requirements.txt`，然后运行：

```text
codex mcp add m14 -- /absolute/path/to/python /absolute/path/to/repo/scripts/m14_mcp.py --transport stdio --env-file /absolute/path/to/private.env
```

后续 pull 后重启 M14 连接即可加载代码；依赖变化时重跑安装脚本。

## 手机、网页 ChatGPT

可用 OpenAI 安全隧道连接本机接口，也可部署远程 HTTPS 服务。仅 push/pull 或已有 Streamlit 页面，不会自动完成 ChatGPT 连接。

### 使用本机安全隧道（无需租服务器）

1. 完成本机 `setup_m14.ps1`，确认 GitHub CLI 已登录或备份 token 已配置。
2. 在 [Platform 隧道设置](https://platform.openai.com/settings/organization/tunnels) 创建私人隧道，关联自己的 Platform 组织及 ChatGPT 工作区。创建仅具有 Tunnels Read、Use 权限的运行密钥，保存在当前 Windows 用户可访问的本机文件中；不要放入仓库或聊天。
3. 从 [OpenAI 官方发布页](https://github.com/openai/tunnel-client/releases/latest) 下载 Windows 客户端，核对发布的 SHA256 校验值。在本机执行（替换示例路径和隧道 ID）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/connect_m14_tunnel.ps1 -TunnelId tunnel_YOUR_ID -ClientPath "C:\path\tunnel-client.exe" -RuntimeKeyFile "C:\private\runtime.key" -RegisterAutoStart
```

脚本使用官方客户端的托管后台进程，并检查 `process_running`、`healthy`、`ready`。`-RegisterAutoStart` 为当前 Windows 用户设置登录后自动启动；不加则只连接。密钥以文件引用传递，不写入命令行。不要在多台电脑上同时运行同一隧道；更换承载电脑时先停止旧实例。

4. ChatGPT 设置 → Security and login → Developer mode；在插件页面创建 `M14 待办清单`，Connection 选 Tunnel，选择所建隧道，Authentication 选 No Auth。这里使用 OpenAI 私人隧道的组织/工作区访问控制，本机 M14 通过 stdio 工作，没有公开匿名 HTTP 接口。
5. 新开 Chat，说“待办：测试事项”，再说“测试事项已完成”。确认 M14 新增并归档后再用于日常记录。首次调用可能仍受 ChatGPT 的插件权限设置影响。

本机须开机、联网且已登录 Windows。关闭电脑或停止隧道后，Chat 不能调用该入口。手机使用同一个 ChatGPT 账号；手机端支持与可见性仍需在实际设备确认。其他电脑仅查看/使用 Chat 无需复制密钥；只有更换承载电脑才需要重新配置本机运行环境。

### 使用远程 HTTPS 服务（不依赖个人电脑开机）

1. 在可运行容器的服务器上，从仓库根目录构建：`docker build -f integrations/m14/Dockerfile -t m14-todos .`。
2. 按 `env.example` 在服务器秘密配置中填写 GitHub 备份访问凭据及 HTTP 配置。备份 token 只需目标仓库的 Contents 读写权限。不要扩大到其他仓库。
3. 创建 GitHub OAuth App，回调地址为 `https://你的域名/auth/callback`。OAuth 仅用于确认登录者身份（`read:user`），服务器只允许 `M14_GITHUB_USER_ID` 指定的数字用户 ID；此 ID 可在 `https://api.github.com/users/你的用户名` 查询。GitHub 登录不会向 ChatGPT 提供仓库备份 token。
4. `M14_JWT_SIGNING_KEY` 使用独立随机密钥（至少 32 字符）；`M14_STORAGE_KEY` 使用 Fernet 密钥。它们由部署平台秘密配置提供，不在聊天里粘贴。`M14_AUTH_STATE_DIR` 使用持久化存储，OAuth 状态在写盘前加密。先按单实例部署；不要让多个实例共享文件目录。
5. 示例运行：`docker run --env-file /secure/m14.env -p 127.0.0.1:8000:8000 -v m14-auth:/var/lib/m14-auth m14-todos`。由反向代理提供 HTTPS，转发完整路径（包括 `.well-known`、`/auth/callback`、`/mcp`）。健康检查为 `/healthz`。
6. 在 ChatGPT 支持的自定义 MCP/插件连接界面添加 `https://你的域名/mcp`，选择 OAuth，使用指定 GitHub 账户登录并授权，然后在新对话中启用 M14。手机是否显示该自定义连接取决于账户及客户端支持，需要实际验收；本仓库的代码测试不等于 ChatGPT 端已连接。

官方资料：[ChatGPT 插件](https://learn.chatgpt.com/docs/plugins)、[MCP 接入](https://learn.chatgpt.com/docs/extend/mcp)、[GitHub OAuth Provider](https://gofastmcp.com/v2/integrations/github)。

## 使用

- “提醒我明天下午三点交材料” → 保存待办及截止时间，不设提醒。
- “todo：联系王老师” → 保存无截止时间的待办。
- “看看还有什么没做” → 查询未完成事项。
- “交材料已经完成了” → 先查找对应事项，再完成归档；重名时询问。
- “把这项截止时间改成周五下午五点” → 查询后修改。

MCP 初始化说明和工具描述已包含上述触发规则。只有该对话已连接并可调用 M14 时才能执行；不能承诺在没有连接的任意聊天中自动触发。

新增传入 request_id（UUID），相同请求重试复用，防止网络超时后重复添加。修改使用查询返回的 uid 与 revision，避免更改陈旧状态。接口每次读取最新 GitHub 版本，临时 SQLite 仅用于复用 M14 逻辑；提交用原始 SHA 检查冲突。遇到冲突不自动覆盖、不强推。页面刷新会合并较新状态，旧数据库会自动补充跨设备唯一标识。旧版页面仍在线运行时应先更新重启后再使用聊天写入。

## 验证

```powershell
.venv-m14\Scripts\python.exe -m unittest tests.test_todo_db tests.test_todo_chat tests.test_m14_mcp
```

测试使用临时数据库及模拟 GitHub，不写真实待办。不启动 Streamlit。服务器上线、OAuth 登录及手机/网页新对话调用需要独立验收。
