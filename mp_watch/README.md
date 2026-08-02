# mp_watch

微信公众号：**自动发现 + 全文归档**（免费发现源 + 复用 `wechat_core`）。

## 项目文档（请从这里读）

**完整接手说明（目标 / 已完成 / L 上未完成）：**

→ [`docs/mp_watch/README.md`](../docs/mp_watch/README.md)

**L 机打勾清单：**

→ [`docs/mp_watch/L_接手清单.md`](../docs/mp_watch/L_接手清单.md)

## 一句话

Docker 负责「谁发了新文」，本包负责「发现后抓下来存盘」。  
目标号：雷立刚本人、财经作家雷立刚、数字生命卡兹克。  
**运行与收尾在办公笔记本 L；代码已在 GitHub `main`。**

## 快速命令

```powershell
# 在仓库根目录
python -m mp_watch --dry-run
python -m mp_watch
python -m unittest tests.test_mp_watch -v
```

配置：`config/mp_watch_sources.json`  
状态：`data/mp_watch_state.json`  
日志：`logs/mp_watch_YYYY-MM-DD.log`
