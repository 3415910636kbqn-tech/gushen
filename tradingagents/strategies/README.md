# tradingagents/strategies — 策略模块

「股神」整合的外部策略集。全部为免费数据源（A股=akshare，美股=yfinance），无 API token 依赖。

## 模块一览

| 模块 | 功能 | 数据源 | 入口 |
|------|------|--------|------|
| `akshare_tushare_bridge.py` | Tushare Pro API 兼容桥接层（列名对齐 tushare，单位：金额=元、total_mv/circ_mv=万元、amount=千元、vol=手，日期=YYYYMMDD） | akshare | `get_pro_api()` |
| `ndx_momentum_hedge.py` | 纳斯达克100动量选股（20日动量>0 过滤 + 5日动量排序取 Top5）+ PSQ 反向 QQQ 对冲，周频调仓 | yfinance（失败回退 Yahoo query2 → pkl 缓存） | `run_ndx_momentum_hedge()` |
| `turtle/` | 龟龟框架源码副本（MIT，原仓库 https://github.com/terancejiang/Turtle_investment_framework） | akshare（经桥接层） | 见下 |

## turtle/ 子目录

- `adapter.py` — `run_turtle_valuation(ts_code)`：DCF/DDM/PE Band/PEG/PS 五法估值 + WACC + 公司分类，返回 `{ts_code, markdown, classification, wacc}`
- `screener_adapter.py` — `run_turtle_screener(tier1_only=True, tier2_limit=None)`：两级选股。
  **契约：默认 `tier1_only=True`**（全市场批量过滤，约 1-5 分钟）；Tier2 为逐股深度分析（每只 18-65s，仅当 `tier1_only=False` 时运行，会非常慢）
- `inject.py` — `inject_turtle_valuation(ticker, result_data)`：把估值摘要追加进基本面文本（供分析师工具调用）

## 已知限制

- **dv_ttm（股息率）**：akshare 无全市场股息率接口 → `daily_basic` 全市场场景 dv_ttm 为 None，龟龟选股主通道已做"全 None 时跳过股息率过滤"降级（排名退化为 pe/pb 各 0.5）
- **list_date**：沪市个股的 list_date 来自交易所代码表，个别缺失时为 NaN，选股器已做掩码（NaN 行不参与上市年限过滤）
- **NDX 数据源**：Yahoo Finance 对国内网络可能 403/429，策略逻辑已单测验证；真实数据需在可访问 Yahoo 的网络下运行（或配置代理）
- **估值耗时**：首次单股估值 18-65s（akshare 拉财务数据）；后续调用可设 `TURTLE_TTL_CACHE=1` 启用龟龟磁盘缓存加速

## REST API（后端注册于 app/routers/strategy.py）

- `GET /api/strategy/ndx-momentum` — NDX 信号（数据源不可用返回 502）
- `GET /api/strategy/turtle-valuation/{ts_code}` — 估值（如 `/000001.SZ`）
- `GET /api/strategy/turtle-screener?tier1_only=true&tier2_limit=10` — 选股

## 前端

`frontend/src/views/Analysis/Strategy.vue`（路由 `/analysis/strategy`，侧边栏"策略分析"）：三个 tab 分别对接上述三个 API。

## LICENSE

- `turtle/` 源码移植自 Turtle_investment_framework（MIT）：https://github.com/terancejiang/Turtle_investment_framework
- `ndx_momentum_hedge.py` 移植自 ndx-momentum-hedge（MIT）：https://github.com/wepoets1107/ndx-momentum-hedge
- 桥接层与适配层为本项目新增（Apache 2.0，随主项目）