# AStockLab

AStockLab 是一个完全保存在 `E:\GoogleDrive\Ding2026\stock\2_AStockLab` 的本地 A 股跟踪系统。当前跟踪力诺药包（301188.SZ）和信息发展（300469.SZ），均以创业板指（399006）为主比较基准。

系统只做数据整理、技术特征和规则标签，不自动交易，也不提供买入、卖出或收益承诺。

## 在线展示

- YaoYao 工具箱中的线上入口为 `E:\github\yao_1\pages\18_19_stock_portal.py` 的“AStockLab”子板块。
- 线上版使用经过大小和 SHA-256 校验的压缩数据库快照，只读展示本项目现有页面能力；采集、回填、特征计算、预测和数据校验仍只在本目录运行。
- 本目录是权威生产项目，线上副本不会写回本地数据库，也不会提交原始行情、日志、虚拟环境或账号凭据。

## 当前数据接口

- 股票首选接口：`akshare.stock_zh_a_hist(symbol="301188", period="daily")`
- 股票稳定备用接口：`akshare.stock_zh_a_daily(symbol="sz301188")`
- 指数接口：`akshare.stock_zh_index_daily(symbol="sz399006")`
- 逐笔成交接口：`akshare.stock_zh_a_tick_tx_js(symbol="sz301188")`
- 1分钟行情接口：`akshare.stock_zh_a_minute(symbol="sz301188", period="1")`
- 指数1分钟主接口：`akshare.stock_zh_a_minute(symbol="sz399006", period="1")`
- 指数1分钟备用接口：`akshare.index_zh_a_hist_min_em(symbol="399006", period="1")`

系统保存创业板指（399006）、深证成指（399001）、上证指数（000001）和科创综指（000680）。指数历史默认从2010年开始；科创综指保存接口能够提供的回溯历史。两只自选股均以创业板指作为主基准，其他指数用于市场环境联动。

AKShare 1.18.80 中已实际检查并测试相关接口。当前网络环境下，东方财富历史接口会偶发主动断开，新浪接口可稳定获取完整日线，因此 provider 会优先请求 `stock_zh_a_hist`，失败后自动切换到 `stock_zh_a_daily`。每行的 `source` 字段记录实际来源。

新浪指数接口不提供成交额，`benchmark_daily_bars.amount` 会如实保留为空值。系统不会用零或随机数补造数据。

## 快速使用

双击 `run_app.bat` 启动页面，或在命令行运行：

```bat
.\run_app.bat
```

浏览器访问：

```text
http://127.0.0.1:8501
```

每日收盘后双击 `run_daily.bat`。它会依次执行：

1. 更新最近 10 个自然日行情；
2. 抓取全部自选股和四个指数的近期1分钟行情；
3. 抓取最新交易日逐笔成交；
4. 逐笔合计与日线成交量、成交额及收盘价核验；
5. 第一次数据校验；
6. 重新计算日线、市场联动和资金行为特征；
7. 第二次数据校验；
8. 生成并校准未来5个交易日的研究型概率路径；
9. 生成 Markdown、JSON 和每日摘要。

任何一步失败都会停止并返回非零退出码，详细过程写入 `logs\run_daily.log`。

交易时段想刷新当天分时对比时，双击 `run_intraday.bat`。它只更新自选股和四个指数的分钟行情，不生成资金行为结论；成功后会自动打开 AStockLab，日志写入 `logs\run_intraday.log`。

## 常用维护命令

以下命令均使用项目虚拟环境，无需激活：

```bat
.\.venv\Scripts\python.exe scripts\init_database.py
.\.venv\Scripts\python.exe scripts\backfill_daily.py
.\.venv\Scripts\python.exe scripts\backfill_daily.py --start 2024-01-01 --end 2026-07-28 --code 301188 --force
.\.venv\Scripts\python.exe scripts\calculate_features.py
.\.venv\Scripts\python.exe scripts\update_intraday.py
.\.venv\Scripts\python.exe scripts\update_intraday.py --minute-only
.\.venv\Scripts\python.exe scripts\validate_data.py
.\.venv\Scripts\python.exe scripts\build_context_pack.py
.\.venv\Scripts\python.exe scripts\generate_predictions.py
.\.venv\Scripts\python.exe scripts\audit_research_pool.py
.\.venv\Scripts\python.exe scripts\update_ai_chain.py
.\.venv\Scripts\python.exe scripts\update_ai_chain.py --sector-only
.\.venv\Scripts\python.exe scripts\update_ai_chain.py --stocks-only
.\.venv\Scripts\python.exe -m pytest -q
```

也可以双击 `run_predictions.bat`，只更新本地预测文件。页面侧栏的
“显示概率预测”默认关闭；打开后点击页面顶部第二项“概率预测”查看结果。
该开关只会读取已经生成的本地结果，不会临时运行模型。
预测页将前序真实K线与未来T+5半透明概率合成K线放在同一图中展示。
模型原始路径占比与历史校准结果概率分开列示，方向冲突时页面会明确警告。

双击 `run_ai_chain.bat` 后，程序依次更新 AI 产业链板块与成分、补齐企业主营资料，
再分批补齐个股日 K 和分钟线；请等待窗口明确显示“AI产业链数据更新完成”。
首次补库时间较长；`--sector-only` 更新板块、
成分和股票池实时行情，`--stocks-only` 继续补个股资料，`--profiles-only`
只补企业主营资料。双击运行时窗口会在成功或失败后保留，失败原因写入
`logs\update_ai_chain.log`，不会再一闪而过。

运行 `scripts\audit_research_pool.py` 会读取最新AI产业链成分快照和本地前复权日线，
按上市历史、行情新鲜度、OHLC完整性、近期成交额以及ST/退市名称标记生成研究池
审计。结果保存到 `reports\research_pool`。这一步只做数据资格筛选，试验池顺序
不是收益预测排名。

同花顺文件必须先放到 `data\imports\ths`，原文件不会被修改：

```bat
.\.venv\Scripts\python.exe scripts\import_ths_file.py data\imports\ths\301188.xlsx
```

支持 `.csv`、`.xlsx` 和 `.xls`，导入前会打印识别到的字段映射。无法识别日期或 OHLC 时会停止，不写数据库。

## 数据与目录

- `config`：股票清单、数据起点和规则阈值。
- `data\database\astock.duckdb`：结构化数据库。
- `data\raw\daily\YYYY-MM-DD`：股票未复权和前复权 Parquet 快照。
- `data\raw\benchmark\YYYY-MM-DD`：基准指数 Parquet 快照。
- `data\raw\tick\YYYY-MM-DD`：逐笔成交 Parquet 快照。
- `data\raw\minute\YYYY-MM-DD`：个股和四个指数的1分钟行情 Parquet 快照。
- `reports\daily`：每日摘要。
- `reports\context_pack`：按 `YYYY-MM-DD_股票代码_context_pack` 命名的 Markdown 和 JSON 分析包，不同股票不会互相覆盖。
- `reports\predictions`：逐只股票保存的研究型概率路径与历史验证结果。
- `logs`：应用、数据、错误、批处理和最近校验结果。
- `.venv`、`.cache`、`.tmp`：虚拟环境、依赖缓存和临时文件，均在 E 盘。

配置中的快照保留期为 30 天。本 MVP 暂不自动删除更早文件；后续可增加一个先列出候选、再移入回收站的清理任务，避免误删。

## 特征和规则

全部特征只使用当日及以前的数据，按交易日期升序计算，不使用 centered rolling，不使用未来数据。滚动窗口不足、基准日期缺失或除数为零时返回空值。

主要阈值位于 `config\settings.yaml`：

- `trend_state`：收盘相对 MA20 的距离以 1% 区分趋势、5% 区分强趋势，并结合 MA20/MA60 方向。
- `volume_state`：20 日量比不低于 1.5 为高量，不高于 0.7 为低量。
- `location_state`：20 日区间位置不低于 0.8 为近高位，不高于 0.2 为近低位；创 20 日高低点分别标为 breakout/breakdown。
- `relative_strength_state`：20 日收益减创业板指 20 日收益，不低于 3% 为 strong，不高于 -3% 为 weak。
- `benchmark_linkage_features`：个股相对四个指数的1/5/20/60日超额收益、20/60日相关性和Beta。
- `daily_money_flow`：逐笔主动买卖净额、大额成交净额、VWAP、尾盘净额、日线覆盖率和资金行为标签。

这些标签是固定规则计算结果，只用于快速归纳事实。

## 概率预测边界

当前预测引擎为 `historical_joint_analog_v1`。系统比较“只看个股历史”与
“同时看个股和四个指数历史”，只有大盘信息在历史滚动验证中增加价值时才纳入
最终路径。未来5日中位路径、区间和形态概率均使用前复权日线生成。

每次历史预测只能读取当时已经发生的数据，相似样本的未来片段必须在预测起点前
完整结束。概率经过局部历史校准，区间采用基于滚动误差的校准半径，不把相似样本
占比直接称为真实概率。

系统设置四项最低可靠性检查：滚动验证次数、方向命中是否超过简单基线、
最终误差是否优于零收益基线、概率区间在后段历史中的实际覆盖率。任一项失败，
页面都会显示红色警示；结果仍可供诊断模型，但不应形成交易判断。

`config\settings.yaml` 中：

- `prediction.enabled` 控制是否允许生成和展示预测；
- `prediction.show_in_ui_default` 控制页面默认是否展示，当前为 `false`；
- `prediction.horizon_days`、`lookback_days` 和校准参数控制预测口径。

预测是本地研究功能，不包含自动交易、订单生成或收益承诺。

## AI 产业链

“AI产业链”页分成三个内页：

- 第一页按 AI 上游、AI 中游、AI 下游、AI 应用四个大类，继续细分到
  中类、细分行业、细分领域和细分方向；股票池展示现价、今日高低点、
  涨幅、振幅、成交量、量比、总市值和流通市值；单击股票代码或名称后自动进入第二页；
- 第二页先并排展示该股票所属细分方向的板块分时图和日 K，再展示所选个股的
  分时图和前复权日 K；下方展示企业主营介绍、AI 相关业务证据，以及板块位次、
  市值和量比等可核验优势线索；
- 第三页按“细分方向、涨幅、细分领域、细分行业、中类、大类”排列所有方向，
  按最新日涨幅从高到低排序；点击方向后展开该方向全部股票，股票同样按当日涨幅
  从高到低排列，单击股票代码或名称可进入第二页；下方继续展示板块分时图和日 K。

产业链分类由 `config\ai_industry_chain.yaml` 维护。板块行情来自同花顺概念指数；
实时股票池行情来自腾讯沪深京 A 股全市场快照与批量报价。代表性成分只是行情
观察池，不是完整成分清单，也不等于公司主营业务属于 AI。成分池保存日期快照，
同一板块同一天重复刷新会整组替换旧榜单；主营资料和个股行情按缺失/最久未更新
顺序分批补齐。

逐笔“大额成交”采用当日单笔成交金额前5%作为阈值。买盘、卖盘属于第三方行情分类，只能用于观察成交行为，不能证明基金、游资或其他具体投资者身份。只有逐笔成交额、成交量和收盘价与日线核验通过后，系统才生成资金行为结果。

“分时对比”页自动选择所有指数和自选股都具备分钟数据的最新共同交易日。每条曲线以各自昨收为0%；四个指数按指数组当日最大绝对涨跌幅共用一组上下对称范围，自选股按个股组最大绝对涨跌幅共用另一组上下对称范围，0%固定在中轴。左轴显示价格、右轴显示涨跌幅，按A股习惯红涨绿跌。这能比较走势强弱和节奏，但不能证明指数与个股之间存在因果关系。所有分钟图（包括资金行为页）只计算实际交易分钟，午间休市时间会被完全压缩，11:30和13:00落在同一中间位置并连续展示，禁止跨午休空档绘制斜长线。分钟更新会先完整抓取自选股和四个指数，校验交易日及最新时间一致后再一次性写入数据库；任一对象失败或落后超过2分钟时，本轮不会写入半套数据。盘中可运行 `update_intraday.py --minute-only` 更新分时图，不会生成未经完整日线核验的资金结论；收盘后运行 `run_daily.bat` 才会抓取逐笔成交并更新资金行为。

“市场联动”页把个股和四个指数叠加在同一张图中，可切换“累计收益率（%）”和“归一化走势（首日=100）”。累计收益率以区间首日为0%；归一化走势中的100只是统一比较基准，110表示较首日上涨10%，90表示下跌10%，不是实际价格。

## 数据保护和幂等性

- 空 DataFrame、必要字段缺失或请求失败时，不写空 Parquet，也不删除旧数据库记录。
- 上海时间 15:10 前自动剔除接口返回的当日未完成日K线；当天缓存快照也会执行相同检查。
- Parquet 先写临时文件并回读验证，成功后才替换目标快照。
- DuckDB 使用事务化主键 upsert；重复运行不会产生重复记录。
- 数据校验检查主键、OHLC、负成交量/成交额、日期顺序、复权覆盖、基准覆盖、最新日期、inf 和最近抓取状态。
- 逐笔数据额外核对成交额覆盖率、成交量覆盖率和末笔价格；核验失败不覆盖旧数据。
- Streamlit 加载页面时只读本地数据，不触发网络请求。

## 扩展股票

在 `config\watchlist.yaml` 的 `stocks` 下增加同结构条目，然后运行：

```bat
.\.venv\Scripts\python.exe scripts\init_database.py
.\.venv\Scripts\python.exe scripts\backfill_daily.py --code 新股票代码
```

股票代码和基准代码均来自配置，业务代码没有写死 301188。
