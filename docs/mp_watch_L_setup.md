# 公众号监控：L 机部署（扩写）

> **主文档已合并到独立项目说明，请优先阅读：**  
> - [docs/mp_watch/README.md](mp_watch/README.md)（完整项目：目标 / 已完成 / 未完成）  
> - [docs/mp_watch/L_接手清单.md](mp_watch/L_接手清单.md)（打勾清单）  
>
> 下文保留为操作扩写，内容与主文档 L 章节一致。

---

## 一、两台机器怎么分工（推荐）

| 角色 | 放哪 | 用什么 |
|---|---|---|
| **发现源** | **L** | Docker 跑 We-MP-RSS（或同类），输出三个公众号的 RSS |
| **归档机器人** | **L** | 本仓库 `mp_watch` + `wechat_core`（Python，Edge 抓正文） |
| **代码同步** | GitHub | D 开发推送 → L `git pull` |
| **正文落盘** | L 本机盘 + 若有云盘同步 | `target_dirs.raw` 指到 L 上真实 Obsidian/GoogleDrive 路径 |

```
[Docker 发现源 :8001]  →  三个 RSS
        ↓ 每 1～2 小时
[L 上 python -m mp_watch]  →  去重 + Playwright 抓正文
        ↓
[L 上 Obsidian/raw 目录]
```

---

## 二、迁移清单（在 L 上做）

### 1. 代码

```powershell
cd <L上 yao_1>
git pull
# 或首次：git clone https://github.com/yaoy2/yao_1.git
```

### 2. Python 依赖

```powershell
python -m pip install -r requirements.txt
python -m mp_watch --dry-run
```

### 3. Docker 发现源

数据卷放数据盘，例如 `D:\docker-data\we-mp-rss`：

```powershell
docker run -d --name we-mp-rss --restart unless-stopped `
  -p 8001:8001 `
  -v D:\docker-data\we-mp-rss:/app/data `
  ghcr.io/rachelos/we-mp-rss:latest
```

打开 `http://127.0.0.1:8001/` → 扫码 → 订三号 → 抄 RSS。

### 4. 配置

编辑 `config/mp_watch_sources.json`：`feed_url`、`enabled: true`、`target_dirs.raw`（L 真实路径）。

### 5. 试跑与任务计划

```powershell
python -m mp_watch --dry-run
python -m mp_watch
```

任务计划：每 2 小时执行 `公众号监控.bat`，起始于仓库根目录。

---

更完整的「已完成 / 未完成 / 验收标准 / 决策记录」见主文档。
