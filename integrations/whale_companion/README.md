# 赛博QQ：呆小鲸兼容入口

呆小鲸已归入 [赛博QQ](../cyber_qq/README.md)，源码和完整说明位于 [whale_companion](../cyber_qq/whale_companion/README.md)。

本目录保留原安装、配置、启动、管理命令及两个批处理文件的兼容入口；现有计划任务路径仍然有效。运行目录仍为 `.local/whale_companion/`，账号、人格、配置和记忆没有迁移或合并。

统一管理入口：

```powershell
& integrations/cyber_qq/manage.ps1 -Instance whale -Action status
```
