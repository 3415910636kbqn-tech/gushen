# 量化能力整合计划（Vibe-Trading + stock-sdk）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Vibe-Trading（HKUDS，MIT）的回测引擎、Alpha Zoo 因子库、quantlib 金融数学库，以及 stock-sdk（chengzuopeng，ISC）的技术指标、筹码分布、前端行情 SDK，精选整合进"股神"（TradingAgents-CN）。

**Architecture:**
- 沿用 `tradingagents/strategies/` 目录（新增子模块），每个能力 = 纯 Python 模块（pandas 实现，无重量级新依赖）+ adapter + REST 端点 + 前端 tab/页面
- 原仓库只读参考：`C:\Users\cccbqn\strategies\Vibe-Trading`（agent/src/quantlib、agent/src/factors、agent/backtest）、`C:\Users\cccbqn\strategies\stock-sdk`（src/indicators、src/screener）
- 移植策略：**精选核心**（quantlib 250+ 函数只移 options/risk/performance/fundmath 四模块的核心函数；462 因子先移算子+精选 30 个；回测引擎先移 A 股 china_a + 基础框架）
- 数据源全部复用股神现有（akshare/yfinance/桥接层），不引入 Vibe 的 24 个 loader

**Tech Stack:** Python 3.11 / pandas / numpy / FastAPI / Vue3 + Element Plus / npm（stock-sdk 仅前端引入）

## Global Constraints

- 不新增重量级 Python 依赖（pandas/numpy/akshare/yfinance 已有）；stock-sdk 仅作为 frontend npm 依赖（纯前端）
- 所有 Python 新代码在 `tradingagents/strategies/` 下；REST 端点走 `app/routers/strategy.py`（复用现有注册）
- 移植代码保留原仓库 MIT/ISC 版权注释，来源记录在 `tradingagents/strategies/LICENSE-ORIGINAL.md` 追加
- 每个任务 = 模块 + 测试 + （必要时）REST 端点，测试用 pytest 真实数据或小型 fake（沿用桥接层测试风格）
- 全量测试命令：`cd C:\Users\cccbqn\gushen && .\env\Scripts\python.exe -m pytest tradingagents/strategies/ -q`
- 子代理写文件一律用 bash（write_file 受 workspace 限制）

---

### Task A: 技术指标移植（stock-sdk indicators → pandas）

**Files:**
- Create: `tradingagents/strategies/indicators.py`
- Test: `tradingagents/strategies/test_indicators.py`

**范围**（移植 stock-sdk `src/indicators/*.ts` 的 17 个指标，pandas 实现）：
MA(SMA/EMA/WMA) / MACD / BOLL / KDJ / RSI / WR / BIAS / CCI / ATR / OBV / ROC / DMI / SAR / KC / 基础 round

**接口：**
```python
def calculate_indicators(df: pd.DataFrame, indicators: dict) -> dict
# df 需含 open/high/low/close/volume；indicators 例：
#   {"ma": {"periods": [5,10,20]}, "macd": {"fast":12,"slow":26,"signal":9}, "kdj": {}, "rsi": {"period":14}}
# 返回 {"ma": {...}, "macd": {...}, ...} 每个值是 pd.Series 或 dict
```
+ 单独函数 calc_sma/calc_macd/calc_kdj/calc_rsi/calc_boll/calc_atr/calc_obv 等（每个可独立调用）

- [ ] 写测试（用已知序列验证关键指标：如 SMA 简单平均、MACD 金叉位置、RSI 在涨跌序列上的值域 0-100）
- [ ] 确认失败 → 移植实现（对照 stock-sdk TS 源码算法）
- [ ] 测试全绿 → 提交 `feat: 技术指标库移植（MA/MACD/KDJ/RSI 等 17 个，pandas）`

---

### Task B: 筹码分布 CYQ（stock-sdk chip.ts → Python + API）

**Files:**
- Create: `tradingagents/strategies/chips.py`（算法移植自 stock-sdk `src/indicators/chip.ts`）
- Test: `tradingagents/strategies/test_chips.py`
- Modify: `app/routers/strategy.py` 加 `GET /api/strategy/chips/{symbol}`（复用桥接层日线/换手数据）

**接口：**
```python
def calc_chip_distribution(klines: pd.DataFrame) -> dict
# klines 含 close/high/low/volume（+可选 turnover 换手率）
# 返回 {profit_ratio, avg_cost, cost_90: (low,high), cost_70: (low,high), peak_price, histogram: [(price, weight), ...]}
```
- [ ] 写测试（构造单峰筹码分布数据，验证获利比例/平均成本在合理范围、90% 成本区间包含峰）
- [ ] 失败 → 移植 chip.ts 算法（东财三角分布模型：按 (high, low, close) 分配当日筹码 + 换手衰减）
- [ ] 全绿 → REST 端点（需要真实 K 线：复用桥接层 weekly/daily + akshare 换手率；无换手率时用估算量）→ 提交

---

### Task C: Alpha Zoo 算子 + 精选因子（Vibe factors）

**Files:**
- Create: `tradingagents/strategies/factors/__init__.py`、`operators.py`、`factors.py`（精选 30 个）
- Test: `tradingagents/strategies/test_factors.py`

**范围：**
- 算子（移植 Vibe `agent/src/factors/base.py` 核心）：rank / scale / ts_mean / ts_std / ts_delay / ts_max / ts_min / delta / decay_linear / safe_div / vwap / ts_sum / ts_argmax / ts_corr（pandas 实现）
- 精选 30 个因子：动量类（MOM/ROC/RSI-based）、均值回复、波动类、量价类（OBV/VR）、基本面类（ROE/PE 变化）——从 qlib158/alpha101/gtja191 各挑常用
- `FACTOR_REGISTRY: dict[str, callable]`，`compute_factor(df, name)` / `compute_factor_panel(df, names)`

**接入：** 选股器增强——`app/routers/strategy.py` 加 `GET /api/strategy/factors`（列表）和 `POST /api/strategy/factor-screen`（传因子+阈值筛选，数据走桥接层全市场快照）

- [ ] 算子测试（rank 单调性/scale 标准化/ts_delay 移位）→ 失败 → 实现
- [ ] 因子测试（对构造的上升/下降序列，动量因子符号正确）→ 失败 → 实现
- [ ] REST 端点 + 验证 → 提交 `feat: Alpha 因子库（算子+精选30因子+因子选股）`

---

### Task D: A股回测引擎（Vibe backtest china_a）

**Files:**
- Create: `tradingagents/strategies/backtest/__init__.py`、`engine.py`（基础回测框架）、`china_a.py`（A股引擎，移植 Vibe `agent/backtest/engines/china_a.py` + `base.py` 核心）
- Test: `tradingagents/strategies/test_backtest.py`
- Modify: `app/routers/strategy.py` 加 `POST /api/strategy/backtest`

**接口：**
```python
def run_backtest(symbol: str, strategy: str, start: str, end: str, params: dict) -> dict
# strategy: "buy_hold" | "ma_cross" | "rsi_reverse" | "momentum"（内置 4 个）
# 或自定义：params 传 {"entry": "...", "exit": "..."} 表达式（简版：策略为可调用对象）
# 返回 {symbol, period, initial_capital, final_value, total_return, annual_return,
#        max_drawdown, sharpe, win_rate, trades: [...], equity_curve: [{date, value}], benchmark: {...}}
```
- 数据：复用桥接层 daily（前复权）
- 交易模型：A股 T+1、涨跌停限制（±10%，ST ±5% 简版）、手续费（佣金万2.5 + 印花税卖出千0.5，简版固定费率）、最小 100 股
- [ ] 框架测试（buy_hold 在已知序列上的收益/回撤计算）→ 失败 → 实现
- [ ] 策略测试（MA 金叉策略在构造趋势序列上产生交易）→ 实现
- [ ] REST + 验证 → 提交 `feat: A股回测引擎（buy_hold/MA交叉/RSI/动量 + 交易成本）`

---

### Task E: quantlib 精选（Vibe quantlib 四模块核心函数）

**Files:**
- Create: `tradingagents/strategies/quantlib/__init__.py`、`options.py`、`risk.py`、`performance.py`、`fundmath.py`
- Test: `tradingagents/strategies/test_quantlib.py`
- Modify: `app/routers/strategy.py` 加 `POST /api/strategy/quantlib`（函数名+参数 JSON 调用）

**范围（移植 Vibe `agent/src/quantlib/` 对应模块核心）：**
- `options.py`：Black-Scholes 定价、Greeks（delta/gamma/theta/vega/rho）、隐含波动率（Newton 迭代）
- `risk.py`：VaR（历史模拟/参数法）、CVaR、最大回撤、Sharpe/Calmar、下行偏差
- `performance.py`：总/年化收益率、年化波动、信息比、Sortino、回撤序列
- `fundmath.py`：XIRR、IRR、MOIC、DPI/TVPI（现金流序列）

- [ ] 每模块核心函数测试（BS 定价对已知参数与参考值误差 < 1e-6；VaR 对构造序列可验证）→ 失败 → 移植
- [ ] quantlib_call 端点（白名单函数表，校验输入）→ 提交 `feat: quantlib 金融数学库（期权/风险/绩效/现金流）`

---

### Task F: 前端整合

**Files:**
- Modify: `frontend/package.json`（加 `stock-sdk` npm 依赖）
- Modify: `frontend/src/views/Analysis/Strategy.vue`（加 tab：技术指标/筹码分布/因子选股/回测）或新建 `frontend/src/views/Analysis/Quant.vue`
- Modify: `frontend/src/router/index.ts`、`SidebarMenu.vue`
- Create: `frontend/src/api/quant.ts`

**范围：**
1. **行情看板/技术图**：用 stock-sdk（npm）在前端画 K 线 + 技术指标叠加（ECharts 已有）
2. **筹码分布图**：调 `/api/strategy/chips/{symbol}` → 前端筹码峰图
3. **因子选股**：因子列表 + 条件输入 → `/api/strategy/factor-screen`
4. **回测页**：股票/策略/区间 → `/api/strategy/backtest` → 权益曲线（ECharts）+ 指标卡片
5. **quantlib 调用**：简易计算器（BS 定价输入框）

- [ ] 装 stock-sdk：`cd frontend && npm install stock-sdk`
- [ ] 新页面/新 tab 组件（参考 Strategy.vue 现有风格）→ `npm run build` 成功
- [ ] 提交 `feat: 前端量化页（技术图/筹码/因子/回测）`

---

### Task G: 收尾

- [ ] 全量测试：`.\env\Scripts\python.exe -m pytest tradingagents/strategies/ -q` 全绿
- [ ] 端到端验证：重启 serve_prod，逐端点验证（chips/factors/backtest/quantlib）
- [ ] `LICENSE-ORIGINAL.md` 追加 Vibe-Trading（MIT）与 stock-sdk（ISC）来源
- [ ] `tradingagents/strategies/README.md` 更新新模块
- [ ] 提交 + 与用户确认后推送 origin main
