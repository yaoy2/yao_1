# 股票研究中心

这是 YaoYao 工具箱的在线股票展示模块，统一承载两个子板块：

- **AStockLab**：读取本地项目生成的只读数据快照，展示自选股、市场联动、分时、资金行为、概率研究和 AI 产业链。
- **股票搜索**：展示雪球与淘股吧公开信息快照，并提供个股或关键词检索。

## 数据边界

在线页面只负责研究展示，不在页面加载时抓取行情，不自动交易，也不提供投资建议。AStockLab 的采集、校验、特征计算和预测仍在 `E:\GoogleDrive\Ding2026\stock\2_AStockLab` 本地完成；SerchHTML 的完整本地采集服务仍在 `E:\GoogleDrive\Ding2026\stock\1_SerchHTML`。

数据库使用 `astocklab/data/online/astock.duckdb.gz` 压缩发布，首次打开页面时解压到系统临时目录。仓库内不会生成可写数据库、WAL 或锁文件。

线上实时搜索通过 `packages.txt` 安装系统 Chromium，并使用无登录临时会话访问公开入口；不会隐藏自动化状态或读取用户浏览器资料。站点拒绝访问时页面会保留“不完整”状态。

## 目录

```text
stock/
├─ astocklab/       # AStockLab 在线运行副本与只读快照
├─ search_html/     # 公开信息搜索规则与快照
├─ portal.py        # 两个子板块的统一渲染入口
└─ runtime.py       # 数据库快照解压与运行隔离
```
