# Task B 报告：筹码分布 CYQ

## 状态
✅ 完成

## Commit
`7392b40` — feat: 筹码分布 CYQ（东财算法移植）+ REST 端点（3 files changed, 468 insertions）

## 测试摘要
`tradingagents/strategies/test_chips.py`：**10 passed**（单峰筹码获利比例/平均成本/90-70 区间、一字板、换手率 NaN、部分 NaN、空输入、OHLC 全 NaN、脏行跳过、缺换手率列、trade_date 列别名）

## 实现
- `tradingagents/strategies/chips.py`
  - `calc_chip_distribution(klines, range_=120, decimals=3, include_histogram=True)`：严格移植 chip.ts
    - FACTOR=150 档，档宽 = max(0.01, (max-min)/149)
    - 逐 bar 存量 ×(1-换手率) 衰减 + 当日三角形分布（顶点在 avg=(O+C+H+L)/4，铺到 [low,high]）
    - 一字板 high==low 时堆入单档（权重 (FACTOR-1)*换手率/2，原版语义）
    - 换手率 NaN/0 → 0 换手（纯衰减不叠加，对齐 `hsl/100 || 0`）；负/超 1 夹逼到 [0,1]
    - 读出：profit_ratio（0..1，原版 getBenefitPart）、avg_cost（累计 50% 处价格，中位数口径）、cost_90/cost_70 区间与集中度 (高-低)/(高+低)、peak_price（直方图最大权重档）、histogram（150 档 [[price, weight]]，权重 6 位小数归一化）
    - 全字段 JSON 安全（无 numpy 标量泄漏）
    - 窗口内全 0 换手 → 分布退化返回全 None（对应原版 emptyItem），不抛异常
  - `fetch_chip_klines(symbol)`：东财 `stock_zh_a_hist`（含换手率列）→ 失败回退桥接层 `daily()`（新浪，无换手率）；换手率全缺失时按成交量占比估算（量/近20日均量 × 1%，避免退化全 None）
- `app/routers/strategy.py`：`GET /api/strategy/chips/{symbol}`
  - `Depends(get_current_user)` 认证（与 screening.py 同款）
  - symbol 校验 `^\d{6}(\.(SH|SZ|BJ))?$`，不匹配 → 400（复用 turtle-valuation 校验文案）
  - 无行情 → 404；返回 `{success, data: {symbol, date, ...chips}}`

## 端点实测（TestClient 直连真实 akshare 数据）
- `GET /api/strategy/chips/600519`（带 token）→ **200**
  `{symbol: "600519", date: "20260807", profit_ratio: 0.538, avg_cost: 1301.77, cost_90: [1186.78, 1432.09], cost_90_concentration: 0.094, cost_70: [1202.12, 1383.54], cost_70_concentration: 0.07, peak_price: 1373.32, histogram: 150 档}`
- `GET /api/strategy/chips/abc123` → **400** "无效股票代码…"
- 无/坏 token → **401** "Invalid token"（真实认证路径）

## Concerns
1. **东财接口网络不稳**：实测中 `stock_zh_a_hist` 多次 `RemoteDisconnected`（IP 限流/断连），自动回退到新浪日线（桥接层 daily）。回退数据无换手率，当前用成交量占比估算兜底——形状可信，但绝对换手率是估算值，集中度/获利比例对换手率幅度不敏感、对相对量能敏感，可接受。
2. **换手率估算基准 1%** 是相对量能尺度；若要求与东财 App 数值严格对拍，需真实换手率（akshare 换手率接口同源，网络恢复后自动走东财路径，无需改码）。
3. **date 格式不一致**：东财路径 `2026-08-07`（date 对象），回退路径 `20260807`（8 位数字），端点原样透传；前端如需要统一可自行格式化。
4. **一字板权重** `(FACTOR-1)*tr/2` 使一字板 bar 的总筹码大于其换手率（原版东财 JS 语义即如此），忠实移植，未做"修正"。
5. 复权口径默认 qfq，分布数值随复权方式变化（与 chip.ts 文档一致）。
6. 本任务未改动 `C:\Users\cccbqn\strategies\` 任何文件。
