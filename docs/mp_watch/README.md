# 微信公众号自动监控归档（mp_watch）

> **给 L（办公笔记本）接手用的完整项目说明。**  
> 在 L 上 `git pull` 后，从本文读到末尾即可无障碍做完剩余工作。  
> 最后更新：2026-08-02（D 机开发侧已推送到 GitHub `main`）

---

## 0. 30 秒看懂

| 项 | 内容 |
|---|---|
| **要解决什么** | 关注的公众号会删帖/隐藏，怕错过；要在发帖后尽快自动抓全文并保存 |
| **盯哪些号** | ① 雷立刚本人 ② 财经作家雷立刚 ③ 数字生命卡兹克 |
| **怎么跑** | Docker 发现「谁发了新文」→ Python `mp_watch` 去重 → `wechat_core` 抓正文+图 → 存 Markdown |
| **放哪台机器** | **推荐全程在 L 跑**（L 已有 Docker 与定时任务习惯）；D 只负责开发推代码 |
| **费用** | 免费优先（自建 RSS 发现源）；不订月费 SaaS |
| **当前进度** | 代码与配置骨架 **已完成并在 GitHub**；L 上 **发现源 + 填 RSS + 任务计划** 未完成 |

**怎样算本项目「做完」：**  
L 上 Docker 发现源能列出三个号的新文 → 配置里三条 `feed_url` 启用 → 任务计划每 1～2 小时自动归档 → 新文出现在 Obsidian raw 目录，**不需要人刷手机**。

---

## 1. 目标与硬约束（产品定案，不要改方向）

### 1.1 目标

1. 三个公众号发文后，在合理时间内（小时级）被自动发现。  
2. 发现后立刻抓取**全文 + 图片**，落盘为 Markdown（防删帖后链接失效）。  
3. 全程后台自动；**「自己刷到微信再手动粘贴」不算达标**。  
4. 只服务个人知识留存，小规模三个号。

### 1.2 已拍板约束

| 约束 | 定案 |
|---|---|
| 自动化 | 全自动，不依赖刷手机 |
| 轮询间隔 | 1～2 小时即可（默认任务计划 **2 小时**） |
| 删帖节奏假设 | 通常几小时到一天，故小时级轮询够用 |
| 成本 | 能免费就免费；不绑月费公众号 RSS 会员 |
| 数据位置 | 配置/状态/日志在**仓库目录内**；Docker 数据卷放 L **数据盘**，少往 C 盘堆 |
| 归档引擎 | 复用仓库已有 `wechat_core.py`（Playwright + 本机 Edge） |
| 机器角色 | **L = 运行环境**；**D = 开发推送**（当前对话曾在 D 上写代码） |

### 1.3 明确不做（第一版）

- 不做微信 PC Hook / 逆向注入（风险高、难维护）  
- 不做「手机推送提醒你再点一下」当主路径  
- 不把密钥、扫码 cookie 提交进 Git  
- 不在 Streamlit 里跑监控（用脚本 + 任务计划）  
- 不在 D、L **同时**长期双跑并互相 push `data/mp_watch_state.json`（易冲突；**以 L 为准**）

---

## 2. 架构（两层）

```
┌─────────────────────────────────────┐
│  发现层（L 上 Docker，免费）           │
│  例：We-MP-RSS :8001                 │
│  输出：每个公众号一条 RSS/JSON         │
└─────────────────┬───────────────────┘
                  │ 每 1～2 小时
                  ▼
┌─────────────────────────────────────┐
│  归档层（L 上 Python，本仓库）         │
│  python -m mp_watch / 公众号监控.bat   │
│  → 拉 RSS → 去重 → wechat_core 抓正文 │
└─────────────────┬───────────────────┘
                  ▼
         Obsidian raw（L 本机路径）
         状态：data/mp_watch_state.json
         日志：logs/mp_watch_YYYY-MM-DD.log
```

**为什么要「发现源」？**  
微信没有给读者「官方订阅别人发文列表」的 API。  
`mp_watch` **不会自己凭空知道**三个号发了什么；必须有一个服务定期给出「标题 + `mp.weixin.qq.com` 链接」。  
这个服务就是发现源。Docker 很适合跑它。

---

## 3. 已经做完的事情（D 开发侧 → 已在 GitHub `main`）

接手前先在 L 执行 `git pull`，确认能看到下列文件。

### 3.1 代码与入口

| 路径 | 作用 | 状态 |
|---|---|---|
| `mp_watch/` | 监控包：配置、RSS 解析、状态、一轮 runner | ✅ 完成 |
| `mp_watch/__main__.py` | `python -m mp_watch` | ✅ |
| `scripts/mp_watch.py` | 备用脚本入口 | ✅ |
| `公众号监控.bat` | Windows 一键跑一轮（给任务计划用） | ✅ |
| `wechat_core.py` | 既有：链接 → Markdown+图（归档引擎） | ✅ 原有，已复用 |
| `tests/test_mp_watch.py` | 单元测试（解析、去重、归档 mock、路径） | ✅ 通过 |

### 3.2 配置与数据模板

| 路径 | 作用 | 状态 |
|---|---|---|
| `config/mp_watch_sources.json` | 三号名称已写入；`enabled=false`；`feed_url` 空 | ✅ 半完成（等 L 填 RSS） |
| `config/mp_watch_sources.example.json` | 样例（含 `target_dirs` 示例） | ✅ |
| `data/mp_watch_state.json` | 已见 URL / 归档状态模板 | ✅ 空模板 |

当前三个源配置意图：

```text
雷立刚本人        enabled=false  feed_url=（空，待填）
财经作家雷立刚    enabled=false  feed_url=（空，待填）
数字生命卡兹克    enabled=false  feed_url=（空，待填）
```

### 3.3 能力细节（已实现）

- RSS / Atom / 简单 JSON 列表解析  
- 微信链接规范化去重（`/s/xxx` 与 query 形式）  
- 失败有限次重试（`retry_failed` + `max_fail_count`）  
- `target_dirs`：覆盖 `wechat_core.TARGET_DIRS`，**D/L 盘符不同时可在配置里改路径**  
- 日志写入仓库 `logs/`，状态写入仓库 `data/`  
- dry-run：`python -m mp_watch --dry-run`（只发现不去抓）

### 3.4 文档

| 路径 | 作用 |
|---|---|
| **`docs/mp_watch/README.md`（本文）** | **项目总说明 + 接手主入口** |
| `docs/mp_watch/L_接手清单.md` | L 上按勾选执行的短清单 |
| `docs/mp_watch.md` | 指向本文的入口说明 |
| `docs/mp_watch_L_setup.md` | 与本文 L 章节一致的操作扩写（可并存） |

### 3.5 尚未在任何机器上完成的事（重点）

| 项 | 说明 |
|---|---|
| ❌ 发现源 Docker 在 L 上部署并订阅三号 | 必须在 L 做 |
| ❌ 三条真实 `feed_url` 写入配置并 `enabled=true` | 必须在 L 做 |
| ❌ L 上 `target_dirs.raw` 改成真实路径 | 必须在 L 做 |
| ❌ L 上手动试跑成功归档一篇 | 验收 |
| ❌ L 上 Windows 任务计划每 2 小时 | 全自动闭环 |
| ❌ （可选）授权过期提醒 | 可后补 |

**结论：代码侧第一版闭环已齐；运行侧闭环必须在 L 完成。**

---

## 4. 文件地图（L 上打开仓库后看这些）

```text
yao_1/
├── docs/mp_watch/
│   ├── README.md              ← 你在读的总说明（主入口）
│   └── L_接手清单.md           ← 按顺序打勾
├── mp_watch/                  ← 监控逻辑包
├── wechat_core.py             ← 抓正文归档
├── config/mp_watch_sources.json
├── data/mp_watch_state.json
├── logs/mp_watch_*.log        ← 跑起来后生成
├── 公众号监控.bat
├── scripts/mp_watch.py
└── tests/test_mp_watch.py
```

常用命令（均在**仓库根目录**执行）：

```powershell
python -m mp_watch --dry-run
python -m mp_watch
python -m unittest tests.test_mp_watch -v
公众号监控.bat
公众号监控.bat --dry-run
```

---

## 5. L 上 `git pull` 之后：继续做完（按顺序）

> 详细勾选版见同目录 [`L_接手清单.md`](L_接手清单.md)。

### 步骤 A — 同步代码与依赖

```powershell
cd <L上的 yao_1 目录>
git pull
python -m pip install -r requirements.txt
python -m mp_watch --dry-run
```

预期：提示「没有启用的 sources」或类似——**正常**（配置里还是 `enabled=false`）。

项目目录建议放在 L 的**数据盘**（如 `D:\github\yao_1`），避免只堆在 C 盘用户目录。

### 步骤 B — Docker 起发现源（免费）

1. 准备数据卷目录（示例，按你 L 真实盘符改）：

```text
D:\docker-data\we-mp-rss
```

2. 启动容器示例：

```powershell
docker run -d --name we-mp-rss --restart unless-stopped `
  -p 8001:8001 `
  -v D:\docker-data\we-mp-rss:/app/data `
  ghcr.io/rachelos/we-mp-rss:latest
```

3. 浏览器打开 `http://127.0.0.1:8001/`  
4. 微信扫码授权  
5. 添加订阅三个号：  
   - 雷立刚本人  
   - 财经作家雷立刚  
   - 数字生命卡兹克  
6. **复制每个号的 RSS 地址**（必须能打开且条目里带 `mp.weixin.qq.com` 链接）

说明：

- 镜像名/端口以你实际可用的为准；L 上若已有同类「公众号→RSS」容器，可直接复用，不必强行同名。  
- 登录态可能过期，过期后要再扫码——免费方案常态，不是归档程序坏了。  
- 若 `ghcr.io` 拉不动，换镜像源或本机已验证过的同类项目，**验收标准只有：稳定 RSS + 微信原文链接**。

### 步骤 C — 填写 `config/mp_watch_sources.json`

在 L 上编辑该文件：

1. 三个源的 `feed_url` 填上步骤 B 的 RSS。  
2. 三个源均 `"enabled": true`。  
3. 增加/修改 `target_dirs`，指向 **L 本机真实** Obsidian raw 路径，例如：

```json
"target_dirs": {
  "raw": "D:\\GoogleDrive\\Obsidian Vault\\00\\LLM_WIKI\\raw"
}
```

**不要照抄 D 机的 `E:\...`，除非 L 上路径完全一致。**

完整示例结构：

```json
{
  "poll_hours": 2,
  "archive_type": "raw",
  "headless": true,
  "max_new_per_run": 15,
  "retry_failed": true,
  "max_fail_count": 5,
  "request_timeout": 30,
  "archive_interval": 2.0,
  "state_path": "data/mp_watch_state.json",
  "log_dir": "logs",
  "target_dirs": {
    "raw": "D:\\改成L上真实路径\\raw"
  },
  "sources": [
    {
      "name": "雷立刚本人",
      "kind": "rss",
      "enabled": true,
      "feed_url": "http://127.0.0.1:8001/rss/实际路径1",
      "archive_type": "raw"
    },
    {
      "name": "财经作家雷立刚",
      "kind": "rss",
      "enabled": true,
      "feed_url": "http://127.0.0.1:8001/rss/实际路径2",
      "archive_type": "raw"
    },
    {
      "name": "数字生命卡兹克",
      "kind": "rss",
      "enabled": true,
      "feed_url": "http://127.0.0.1:8001/rss/实际路径3",
      "archive_type": "raw"
    }
  ]
}
```

### 步骤 D — 验收试跑

```powershell
python -m mp_watch --dry-run
```

应打印发现到的标题与链接。再：

```powershell
python -m mp_watch
```

检查：

1. `logs/mp_watch_YYYY-MM-DD.log` 有成功记录  
2. `data/mp_watch_state.json` 中对应 URL `status` 为 `archived`  
3. `target_dirs.raw` 下出现 `.md` 与图片 assets  

若抓取遇验证码：配置里临时 `"headless": false` 再跑，观察 Edge 窗口。

### 步骤 E — 任务计划（全自动）

Windows「任务计划程序」新建任务：

| 项 | 值 |
|---|---|
| 程序/脚本 | `<yao_1绝对路径>\公众号监控.bat` |
| 起始于 | `<yao_1绝对路径>` |
| 触发器 | 每 **2** 小时（可改为 1 小时） |
| 条件 | 按需：插电、唤醒计算机 |

与 L 上已有「新闻抓取」Docker 任务**并列**，不要互相替换。

### 步骤 F — 日常维护（做完后）

| 情况 | 处理 |
|---|---|
| 连续日志「源拉取失败」 | Docker 挂了或要重新扫码 |
| 有链接归档失败 | 文已删 / 风控；看 failed 日志 |
| 代码有更新 | L 上 `git pull`（注意别盲目覆盖你在 L 改过的 `mp_watch_sources.json` 若未备份） |
| 状态文件 | **以 L 为准**；不要 D、L 双机同时跑再双端 push 状态 |

配置里的 `feed_url`、本机路径含隐私的，可不提交；若提交请确认没有 token。

---

## 6. 两台机器职责（避免搞混）

| 机器 | 角色 | 日常 |
|---|---|---|
| **D（家里台式机）** | 开发 | 改代码、测逻辑、`git push`；**不必**长期跑监控 |
| **L（办公笔记本）** | 生产运行 | `git pull`、Docker 发现源、任务计划、`mp_watch` |

当前会话在 D 上完成的是「开发与文档」；**生产闭环只在 L 上收尾。**

---

## 7. 验收标准（勾完即项目第一版交付）

- [ ] L 上 `git pull` 后 `python -m mp_watch --dry-run` 能连上三个源并列出文章  
- [ ] 至少成功自动归档 **1 篇** 真实公众号文章到 `target_dirs.raw`  
- [ ] 同一链接第二轮不再重复归档（去重有效）  
- [ ] 任务计划已创建，到点会写新的 `logs/mp_watch_*.log`  
- [ ] 人为不打开微信一段时间，只要 L 开机/任务跑着，仍能抓到新文（在发现源授权有效期内）

---

## 8. 排障分层

| 现象 | 多半在哪一层 | 怎么处理 |
|---|---|---|
| 没有启用的 sources | 配置 | `enabled` / `feed_url` |
| 源拉取失败 | 发现源 Docker / 扫码 | `docker ps`、`docker logs`、网页重授权 |
| 有 URL 归档失败 | wechat_core / 微信风控 | headless=false；看 logs |
| 文件写到错误盘 | target_dirs | 改成 L 真实路径 |
| 任务计划不跑 | Windows | 起始于目录、权限、休眠 |

---

## 9. 相关代码入口（给继续改代码的人）

| 模块 | 职责 |
|---|---|
| `mp_watch/feed.py` | 拉并解析 RSS/JSON |
| `mp_watch/normalize.py` | 微信 URL 规范化 |
| `mp_watch/state.py` | 状态读写 |
| `mp_watch/config.py` | 读 `mp_watch_sources.json` |
| `mp_watch/runner.py` | 一轮：发现→归档→记状态 |
| `wechat_core.archive_urls` | Playwright 抓正文 |

---

## 10. 对话中已确认的决策记录（备忘）

1. 删帖一般是几小时到一天 → 1～2 小时轮询足够。  
2. 必须全自动，刷手机不算。  
3. 电脑可长期挂微信/任务（L 更合适）。  
4. 免费优先。  
5. 可用 Docker；L 已有 Docker 新闻任务。  
6. 三个准确名称：雷立刚本人、财经作家雷立刚、数字生命卡兹克。  
7. 项目与数据要清晰；运行数据与 Docker 卷放数据盘，少往 C 盘塞。  
8. 从 D 迁到 L：用 GitHub 同步代码，在 L 完成发现源与任务计划。

---

## 11. 下一步唯一行动句

**在 L 上打开 [`L_接手清单.md`](L_接手清单.md)，从第 1 项勾到最后一项；勾完即交付。**

若卡在 Docker 镜像拉取或 RSS 不含微信链接，把 L 上的报错原文与 `docker ps` 输出记下来，回到 D 侧会话或新开会话继续排障（代码已在 GitHub，不必从零描述项目）。
