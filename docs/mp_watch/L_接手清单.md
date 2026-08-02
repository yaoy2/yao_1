# L 接手清单（打勾用）

> 配套总说明：[`README.md`](README.md)  
> 在 **办公笔记本 L** 上操作。每完成一项打 `[x]`。

**目标公众号：** 雷立刚本人 · 财经作家雷立刚 · 数字生命卡兹克  

**怎样算做完：** 发现源可用 + 配置启用 + 成功归档过至少 1 篇 + 任务计划每 2 小时跑。

---

## 一、同步与环境

- [ ] 1. 打开 L 上 `yao_1` 目录（没有则 `git clone https://github.com/yaoy2/yao_1.git`，放数据盘）
- [ ] 2. `git pull`，确认存在目录 `mp_watch/`、`docs/mp_watch/`、文件 `公众号监控.bat`
- [ ] 3. `python -m pip install -r requirements.txt`
- [ ] 4. 确认本机有 **Microsoft Edge**（归档用）
- [ ] 5. 在仓库根目录执行：`python -m mp_watch --dry-run`（暂时提示未启用源 → 正常）

## 二、Docker 发现源

- [ ] 6. 在数据盘建卷目录（例：`D:\docker-data\we-mp-rss`）
- [ ] 7. `docker run` 启动公众号→RSS 服务（端口如 8001，重启策略 `unless-stopped`）
- [ ] 8. 浏览器打开管理页，微信扫码授权
- [ ] 9. 订阅三个公众号（名称与上表一致）
- [ ] 10. 复制三条 RSS 地址；浏览器打开 RSS，确认条目含 `mp.weixin.qq.com` 链接

## 三、配置

- [ ] 11. 编辑 `config/mp_watch_sources.json`
- [ ] 12. 三个源均填写 `feed_url`，且 `"enabled": true`
- [ ] 13. 设置 `target_dirs.raw` 为 **L 本机真实** Obsidian raw 路径（勿照抄 D 的 E: 除非路径相同）
- [ ] 14. 保存配置（如需提交 Git：确认无 cookie/密钥；本机路径可按习惯决定是否提交）

## 四、试跑验收

- [ ] 15. `python -m mp_watch --dry-run` → 能看到标题与链接
- [ ] 16. `python -m mp_watch` → 至少成功归档 1 篇
- [ ] 17. 检查 `logs/mp_watch_YYYY-MM-DD.log`
- [ ] 18. 检查 `data/mp_watch_state.json` 中有 `status: archived`
- [ ] 19. 检查 raw 目录下有 `.md`（及图片 assets）
- [ ] 20. 再跑一轮：同一链接不会重复归档

## 五、全自动

- [ ] 21. 任务计划：程序=`...\yao_1\公众号监控.bat`，起始于=`...\yao_1`
- [ ] 22. 触发器：每 **2** 小时（或 1 小时）
- [ ] 23. 到点后确认日志文件时间有更新
- [ ] 24. （建议）笔记本插电/休眠策略不影响任务执行

## 六、交付确认

- [ ] 25. 不打开微信也能靠 L 后台任务抓到新文（在发现源授权有效期内）
- [ ] 26. 知道授权过期时：打开发现源网页重新扫码
- [ ] 27. 知道排障：先分「发现源失败」还是「正文抓取失败」（见 README 第 8 节）

---

## 失败时记什么（方便下一会话）

```text
日期：
卡在清单第几项：
命令：
完整报错：
docker ps：
feed_url 是否能在浏览器打开（是/否）：
```

---

## 不要做

- 不要在 D 和 L 同时长期跑监控又双端 push `data/mp_watch_state.json`
- 不要把扫码 cookie、token 写进仓库
- 不要指望只填公众号名字、不配 RSS 就能自动发现新文
