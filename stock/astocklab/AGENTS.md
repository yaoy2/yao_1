# AStockLab 在线副本规则

- 该目录是本地 AStockLab 的只读在线副本，不在这里运行采集、回填或模型训练。
- `src/` 保持与本地项目运行代码一致；在线差异只放在 `online_app.py` 和上级运行适配层。
- 数据库只以 `data/online/astock.duckdb.gz` 保存，禁止提交解压后的 `.duckdb`、WAL、原始行情、日志和缓存。
- 页面必须明确标注快照时间和研究边界。
