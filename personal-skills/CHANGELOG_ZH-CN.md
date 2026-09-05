# 更新日志

**语言**：简体中文 | [English](CHANGELOG_EN.md)

**README**：[中文](README_ZH-CN.md) | [English](README_EN.md)

## 2026-09-06

- **集中保存三项个人技能**：同步 create-premium-ppt、save-xhs-comment-human-images、storage-analyzer，新增双语集合说明与日志；集合不计为新的独立运行项目。各台机器复制或安装到自己的 CODEX_HOME/skills，不依赖固定盘符或 Junction。
- **缩小重复工作**：PPT 局部修改复用已确认结构并做增量验收；小红书优先复用已登录可控浏览器；存储分析在单次扫描中缓存目录读取。原有交付标准、真人主体筛选、只读分析与清理授权边界保留。
- **证据与限制**：9 月 5 日存储缓存通过 5 项行为检查、8 组输出保持一致，虚构目录读取由 24 次降至 14 次；这不是整盘性能或模型费用测量。本轮没有真实全盘扫描、PPT 或小红书业务实跑，不把流程调整记作已经节省 token。详见[公开记录](../docs/history/2026-09-05-skill-cost-optimization.md)。
