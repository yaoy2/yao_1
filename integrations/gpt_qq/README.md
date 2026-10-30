# 赛博QQ：GPT 小号兼容入口

本实例已归入 [赛博QQ](../cyber_qq/README.md)，源码和完整说明位于 [gpt_qq](../cyber_qq/gpt_qq/README.md)。

本目录仅保留原安装、配置、启动和管理命令的兼容入口。独立运行目录仍为 `.local/gpt_qq/`，账号、API Key、聊天记录和 QQ 登录数据没有迁移。

统一管理入口：

```powershell
& integrations/cyber_qq/manage.ps1 -Instance gpt -Action status
```
