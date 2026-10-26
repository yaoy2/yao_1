# M31 · QQ 归档机器人：多工作群归档与 L 部署续接

目标是让同一套机器人服务接入多个工作群，逐群授权、分别保存消息与文件，查询和整理保持群间隔离。

工具箱入口为 **行政 → M31 · QQ 归档机器人**，对应 [Streamlit 项目展示页](pages/30_31_qq_archive.py)。页面说明当前能力、指令、保存方式、处理流程和验收边界，不读取群内容或控制 L 上的服务。

**2026-10-26 当前状态：首个目标群的普通消息、新附件自动保存和四项归档指令已真实验收；L 已切换到 `20261026-ai-2`。** 用户指定的 DeepSeek Flash 已配置，只在发送“整理今天”时分析本群当天聊天、图片和文档，保存并回复摘要。离线检查和无真实群内容的模型实测已通过，群内 AI 回复正在验收。另一成员、跨群和 D 端回读仍待验收。旧 WorkBuddy 接入保留；登录自启尚未启用。

- [前因后果与当天验证记录](docs/history/2026-10-24-qq-group-archive/README.md)
- [L 安装与本轮验收进度](docs/history/2026-10-26-qq-group-archive/README.md)
- [以后能操作 L 时，从这里继续](docs/guides/qq-group-archive-L-handoff.md)
- [完整脱敏对话、可复用源码和归档包（需私有库权限）](https://github.com/yaoy2/yao_1-data/tree/main/data/qq_robot_archive/2026-10-24)
- [本轮修复源码与安装、验收回执（需私有库权限）](https://github.com/yaoy2/yao_1-data/tree/main/data/qq_robot_archive/2026-10-26)
- [AI 版源码与验证回执（需私有库权限）](https://github.com/yaoy2/yao_1-data/tree/main/data/qq_robot_archive/2026-10-26-ai)

本记录不保留具体群名、群号、成员、群内业务内容或 API Key。AI 报告带来源索引，未明确的负责人和期限保留为待确认；扫描 PDF、文档内嵌图片和平台未推送的合并转发内容不能视为已理解。各工作群专属流程仍需按具体需求处理。
