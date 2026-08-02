# 公众号监控：从家里台式机 D 迁到办公笔记本 L

目标：在 **L（办公笔记本）** 上 7× 工作时段自动盯三个号，数据与代码路径清晰；**D（家里台式机）** 可只做开发，不必长期跑监控。

三个号：

- 雷立刚本人  
- 财经作家雷立刚  
- 数字生命卡兹克  

---

## 一、两台机器怎么分工（推荐）

| 角色 | 放哪 | 用什么 |
|---|---|---|
| **发现源** | **L** | Docker 跑 We-MP-RSS（或同类），输出三个公众号的 RSS |
| **归档机器人** | **L** | 本仓库 `mp_watch` + `wechat_core`（Python，Edge 抓正文） |
| **代码同步** | GitHub | D 开发推送 → L `git pull` |
| **正文落盘** | L 本机盘 + 若有云盘同步 | `target_dirs.raw` 指到 L 上真实 Obsidian/GoogleDrive 路径 |

为什么不放 D：你已说明 L 上 Docker 每天在跑新闻抓取，机器更适合「常开 + 定时任务」；监控也放 L，一套环境管完。

```
[Docker 发现源 :8001]  →  三个 RSS
        ↓ 每 1～2 小时
[L 上 python -m mp_watch]  →  去重 + Playwright 抓正文
        ↓
[L 上 Obsidian/raw 目录]
```

---

## 二、迁移清单（在 L 上做）

### 1. 代码：从 GitHub 拉到 L

L 上若还没有仓库：

```powershell
cd <你打算放项目的盘，建议非系统盘，例如 D:\github 或 E:\github>
git clone https://github.com/yaoy2/yao_1.git
cd yao_1
```

若已有仓库：

```powershell
cd <yao_1 目录>
git pull
```

说明：

- 代码以 **GitHub 为账本**，不要 U 盘拷半成品。  
- 项目目录尽量放在 **L 的数据盘**（不要塞满 C 盘用户目录里一堆零散文件）；Docker 数据卷也建议绑到数据盘。

### 2. Python 依赖（归档用，不是 Docker 里跑）

在 L 的 `yao_1` 目录：

```powershell
python -m pip install -r requirements.txt
```

归档用本机 **Microsoft Edge**（`wechat_core` 已按 Edge 写）。L 上应已装 Edge，一般不用再 `playwright install chromium`。

试一下模块能起来：

```powershell
python -m mp_watch --dry-run
```

此时若 sources 仍是 `enabled: false`，会提示没有启用源——正常。

### 3. Docker：起免费发现源（推荐 We-MP-RSS）

在 L 上选一个**数据目录**（示例，请改成你 L 的真实路径）：

```text
D:\docker-data\we-mp-rss
```

示例（镜像名以项目文档为准，可换成你验证过的 tag）：

```powershell
docker run -d --name we-mp-rss --restart unless-stopped `
  -p 8001:8001 `
  -v D:\docker-data\we-mp-rss:/app/data `
  ghcr.io/rachelos/we-mp-rss:latest
```

然后浏览器打开：

```text
http://127.0.0.1:8001/
```

按界面：

1. 微信扫码授权（登录态会过期，过期后要再扫，属免费方案常态）  
2. 添加订阅：`雷立刚本人`、`财经作家雷立刚`、`数字生命卡兹克`  
3. 记下每个号的 **RSS 链接**（形如 `http://127.0.0.1:8001/...`）

若镜像拉取失败或界面与文档不一致：先 `docker logs we-mp-rss`，或换你 L 上已经在用的同类「公众号→RSS」镜像；**只要最终能给出含 `mp.weixin.qq.com` 链接的 RSS/JSON，就能接 `mp_watch`。**

### 4. 填写 L 本机配置

编辑 L 上的：

```text
config\mp_watch_sources.json
```

要点：

1. 三个 `name` 已是目标号名。  
2. 把 Docker 给出的 RSS 填进各自 `feed_url`。  
3. 三个都设 `"enabled": true`。  
4. **按 L 真实路径写 `target_dirs`**（不要照抄 D 的 `E:\GoogleDrive\...`，除非 L 也是同一路径）：

```json
{
  "poll_hours": 2,
  "archive_type": "raw",
  "target_dirs": {
    "raw": "D:\\GoogleDrive\\Obsidian Vault\\00\\LLM_WIKI\\raw"
  },
  "sources": [
    {
      "name": "雷立刚本人",
      "kind": "rss",
      "enabled": true,
      "feed_url": "http://127.0.0.1:8001/rss/你的实际路径1",
      "archive_type": "raw"
    },
    {
      "name": "财经作家雷立刚",
      "kind": "rss",
      "enabled": true,
      "feed_url": "http://127.0.0.1:8001/rss/你的实际路径2",
      "archive_type": "raw"
    },
    {
      "name": "数字生命卡兹克",
      "kind": "rss",
      "enabled": true,
      "feed_url": "http://127.0.0.1:8001/rss/你的实际路径3",
      "archive_type": "raw"
    }
  ]
}
```

`target_dirs` 会覆盖 `wechat_core` 默认归档目录，专为 D/L 路径不同设计。

### 5. 先 dry-run，再正式抓

```powershell
python -m mp_watch --dry-run
```

应能看到三个源拉到的标题/链接。再：

```powershell
python -m mp_watch
```

或双击 / 调用：

```text
公众号监控.bat
```

成功后看：

- `data\mp_watch_state.json`：是否出现 `archived`  
- `logs\mp_watch_YYYY-MM-DD.log`  
- `target_dirs.raw` 目录里是否有 Markdown  

### 6. 任务计划（全自动，不靠刷手机）

在 L 上「任务计划程序」：

| 项 | 建议 |
|---|---|
| 程序 | `...\yao_1\公众号监控.bat` |
| 起始于 | `...\yao_1` |
| 触发 | 每 2 小时（或 1 小时） |
| 条件 | 插电时运行（可选）；唤醒计算机（按你习惯） |

与现有「新闻抓取」任务并列即可，互不替代：一个是 Docker 里的新闻任务，一个是本仓库 bat。

---

## 三、D 和 L 各自以后干什么

| 机器 | 建议 |
|---|---|
| **D（家里，当前对话操作的机器）** | 改代码、测逻辑、`git push`；不必常驻 Docker 监控 |
| **L（办公）** | `git pull` → 跑 Docker 发现源 + 任务计划 `mp_watch` |

状态文件 `data/mp_watch_state.json`：

- **以 L 为准**（真正在跑的那台）。  
- 不要两边同时跑又同时 push 状态，避免互相覆盖。  
- 若状态也要进 Git：只在 L 归档成功后偶尔提交；日常可 gitignore 状态（当前仓库仍跟踪空状态模板，你可按习惯调整）。

---

## 四、常见问题

| 现象 | 处理 |
|---|---|
| dry-run 拉源失败 | Docker 没起 / 端口不是 8001 / 要重新扫码 |
| 有链接归档失败 | L 上 Edge/风控；把 `headless` 临时改 `false` 看浏览器 |
| 文件写到奇怪盘符 | `target_dirs.raw` 没改成 L 路径 |
| C 盘又变满 | Docker 卷和 yao_1 都放到数据盘，别默认堆在 `C:\Users\...` |
| 授权过期 | 打开 We-MP-RSS 网页再扫一次；日志里会像「源拉取失败」 |

---

## 五、你在 L 上的最短路径（抄作业）

1. `git clone` 或 `git pull`  
2. `pip install -r requirements.txt`  
3. Docker 起发现源，订三个号，抄 RSS  
4. 改 `config/mp_watch_sources.json`（feed + enabled + `target_dirs`）  
5. `python -m mp_watch --dry-run` → `python -m mp_watch`  
6. 任务计划每 2 小时跑 `公众号监控.bat`  

家里 D 上这次对话写好的代码，**通过 GitHub 到 L**，不要指望我直接操作 L；你在 L 打开终端按上面做即可。若 L 上 Docker 命令报错，把 `docker ps` 和报错原文发我，我按 L 的环境改命令。
