# 策略整合实施计划（NDX 动量对冲 + 龟龟估值/选股）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ndx-momentum-hedge（美股动量对冲）和 Turtle_investment_framework（A股基本面估值/选股）深度融合进"股神"（TradingAgents-CN），提供策略信号计算 + 估值分析 + 选股能力，并通过新前端页面展示。

**Architecture:**
- 新建 `tradingagents/strategies/` 目录放三个可独立调用的策略模块：NDX 动量对冲（移植自原仓库 server.py 的 build_report，数据源换 yfinance）、龟龟估值引擎（移植 ValuationEngine）、龟龟选股器（移植 TushareScreener）。
- 新建 `tradingagents/strategies/akshare_tushare_bridge.py` 数据桥接层：伪装成 `ts.pro_api()` client，内部全部用 akshare 实现，列名对齐 tushare，使龟龟代码改动最小。
- 新建 `app/routers/strategy.py`（prefix=`/api/strategy`）暴露三个 REST 端点；前端新增 `frontend/src/views/Analysis/Strategy.vue` 页面（三个 tab）接入。
- 两个策略均为 MIT 协议，移植代码保留 LICENSE 归属注释（`tradingagents/strategies/LICENSE-ORIGINAL.md` 记录来源）。

**Tech Stack:** Python 3.11 / FastAPI / akshare（已装）/ yfinance（已装）/ pandas / Vue3 + Element Plus

## Global Constraints

- Python 3.10+，复用股神 `env/` venv，不新增重量级依赖（akshare/yfinance/pandas 已有）
- 所有新代码放 `tradingagents/strategies/`，REST 端点走 `app/routers/strategy.py`
- 数据源：A股一律 akshare（用户无 Tushare token），美股一律 yfinance
- 前端页面路由 `/analysis/strategy`，菜单项"策略分析"（SidebarMenu.vue）
- 移植代码必须保留原作者 MIT 版权声明，新增 LICENSE-ORIGINAL.md
- 每次任务完成跑 pytest（股神 `env\Scripts\python.exe -m pytest`）或对应单测
- 提交走股神 git（origin = 用户 fork），commit message 中文描述

---

### Task 1: 数据桥接层 akshare_tushare_bridge

**Files:**
- Create: `tradingagents/strategies/__init__.py`
- Create: `tradingagents/strategies/akshare_tushare_bridge.py`
- Test: `tradingagents/strategies/test_akshare_tushare_bridge.py`

**Interfaces:**
- Produces: `get_pro_api() -> ProClient`；`ProClient.stock_basic(**kw) -> pd.DataFrame`、`daily_basic(**kw)`、`income(**kw)`、`balancesheet(**kw)`、`cashflow(**kw)`、`fina_indicator(**kw)`、`dividend(**kw)`、`weekly(**kw)`、`daily(**kw)`、`close()`。所有返回 DataFrame 列名对齐 tushare（snake_case 英文字段，A股金额单位=元）。

- [ ] **Step 1: 写桥接层骨架 + 单测（先写测试）**

测试文件 `test_akshare_tushare_bridge.py`：
```python
import pytest
from tradingagents.strategies.akshare_tushare_bridge import get_pro_api

@pytest.fixture(scope="module")
def pro():
    return get_pro_api()

def test_stock_basic_columns(pro):
    df = pro.stock_basic()
    assert {"ts_code", "name", "industry"}.issubset(df.columns)
    assert len(df) > 3000

def test_daily_basic_columns(pro):
    df = pro.daily_basic(ts_code="000001.SZ")
    assert {"ts_code", "trade_date", "pe_ttm", "pb", "total_mv", "dv_ttm"}.issubset(df.columns)

def test_fina_indicator_columns(pro):
    df = pro.fina_indicator(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "roe", "grossprofit_margin"}.issubset(df.columns)

def test_income_columns(pro):
    df = pro.income(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "revenue", "n_income"}.issubset(df.columns)

def test_balancesheet_columns(pro):
    df = pro.balancesheet(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "total_assets", "total_liab", "money_cap"}.issubset(df.columns)

def test_cashflow_columns(pro):
    df = pro.cashflow(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "n_cashflow_act"}.issubset(df.columns)

def test_dividend_columns(pro):
    df = pro.dividend(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "cash_div_tax"}.issubset(df.columns)

def test_weekly_columns(pro):
    df = pro.weekly(ts_code="000001.SZ")
    assert {"ts_code", "trade_date", "close"}.issubset(df.columns)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd C:\Users\cccbqn\gushen && .\env\Scripts\python.exe -m pytest tradingagents/strategies/test_akshare_tushare_bridge.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现桥接层**

`tradingagents/strategies/akshare_tushare_bridge.py` 骨架：
```python
"""Tushare Pro API 兼容桥接层（akshare 实现，无 token）。
移植自 Turtle_investment_framework（MIT）数据层适配。
所有接口返回 DataFrame，列名对齐 tushare（英文字段、A股单位=元）。
"""
import pandas as pd
import akshare as ak
import re

def _normalize_ts_code(ts_code):
    """'000001.SZ' -> '000001'"""
    return str(ts_code).split(".")[0] if ts_code else None

def _pick(df, mapping):
    """akshare 中文列 -> tushare 英文字段重命名；缺失列置 None"""
    out = pd.DataFrame(index=df.index)
    for en, zh in mapping.items():
        if zh in df.columns:
            out[en] = df[zh]
        else:
            out[en] = None
    return out

class ProClient:
    def __init__(self):
        self._sina_basic_cache = None

    def _sina_basic(self):
        # 新浪 A股 基础信息（全市场）: ts_code/name/industry
        if self._sina_basic_cache is None:
            df = ak.stock_info_a_code_name()  # code, name
            ind = ak.stock_board_industry_name_em()  # 行业板块
            # 简化：code+name，industry 置空（可后续用 stock_individual_info_em 补）
            df.columns = ["ts_code", "name"]
            df["ts_code"] = df["ts_code"].apply(lambda c: f"{c}.SH" if c.startswith("6") or c.startswith("9") else f"{c}.SZ")
            self._sina_basic_cache = df
        return self._sina_basic_cache

    def stock_basic(self, **kw):
        return self._sina_basic()

    def daily_basic(self, ts_code=None, trade_date=None, **kw):
        code = _normalize_ts_code(ts_code)
        spot = ak.stock_zh_a_spot_em()  # 东方财富实时快照
        spot.columns = [c.strip() for c in spot.columns]
        mapping = {
            "ts_code": "代码", "trade_date": None,
            "pe_ttm": "市盈率-动态", "pb": "市净率", "total_mv": "总市值",
            "turnover_rate": "换手率", "dv_ttm": None,
        }
        df = _pick(spot, mapping)
        df["ts_code"] = df["ts_code"].apply(lambda c: f"{c}.SH" if str(c).startswith("6") else f"{c}.SZ")
        if code:
            df = df[df["ts_code"] == f"{code}.SH" if False else df["ts_code"].str.startswith(code)]
        return df

    def fina_indicator(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        # 新浪财务指标（含 ROE/毛利率等）
        df = ak.stock_financial_analysis_indicator(symbol=code)
        mapping = {"ts_code": None, "end_date": "日期", "roe": "净资产收益率(%)",
                   "grossprofit_margin": "销售毛利率(%)"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def income(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        # 新浪利润表（报告期）
        df = ak.stock_financial_report_sina(stock=code, symbol="利润表")
        mapping = {"ts_code": None, "end_date": "报告日", "revenue": "营业收入",
                   "n_income": "净利润"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def balancesheet(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_financial_report_sina(stock=code, symbol="资产负债表")
        mapping = {"ts_code": None, "end_date": "报告日", "total_assets": "资产总计",
                   "total_liab": "负债合计", "money_cap": "货币资金"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def cashflow(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_financial_report_sina(stock=code, symbol="现金流量表")
        mapping = {"ts_code": None, "end_date": "报告日", "n_cashflow_act": "经营现金流量净额"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def dividend(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_fhps_detail_em(symbol=code)
        mapping = {"ts_code": None, "end_date": "报告期", "cash_div_tax": "派息"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def weekly(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        mapping = {"ts_code": None, "trade_date": "日期", "close": "收盘"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def daily(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        mapping = {"ts_code": None, "trade_date": "日期", "close": "收盘"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def close(self):
        pass

def get_pro_api():
    return ProClient()
```

> 注意：akshare 各接口列名可能随版本变化，Step 4 若失败用 `df.columns` 实际值调整 mapping（打印诊断）。股票代码后缀规则：6/9 开头=SH，0/3 开头=SZ（简化版）。

- [ ] **Step 4: 运行测试，按需调整列名映射**

Run: `cd C:\Users\cccbqn\gushen && .\env\Scripts\python.exe -m pytest tradingagents/strategies/test_akshare_tushare_bridge.py -v`
Expected: PASS（若个别接口列名不匹配，按实际 `df.columns` 修正 mapping 后重跑）

- [ ] **Step 5: 提交**

```bash
cd C:\Users\cccbqn\gushen
git add tradingagents/strategies/
git commit -m "feat: 新增 akshare→tushare 数据桥接层（龟龟策略数据适配）"
```

---

### Task 2: NDX 动量对冲策略模块 + API

**Files:**
- Create: `tradingagents/strategies/ndx_momentum_hedge.py`
- Create: `app/routers/strategy.py`
- Modify: `app/main.py:688` 附近（include_router 注册 strategy router）
- Test: `tradingagents/strategies/test_ndx_momentum_hedge.py`

**Interfaces:**
- Consumes: 无（yfinance 直接拉数据）
- Produces: `run_ndx_momentum_hedge() -> dict`（date/week_start/pool_size/momentum_top5/top_symbols/changes/performance/qqq_12w/full_momentum）；REST `GET /api/strategy/ndx-momentum`

- [ ] **Step 1: 写失败测试**

`test_ndx_momentum_hedge.py`：
```python
from tradingagents.strategies.ndx_momentum_hedge import run_ndx_momentum_hedge

def test_report_shape():
    r = run_ndx_momentum_hedge()
    assert isinstance(r, dict)
    assert "top_symbols" in r and isinstance(r["top_symbols"], list)
    assert "performance" in r
    assert "momentum_top5" in r
```

- [ ] **Step 2: 验证测试失败**

Run: `.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_ndx_momentum_hedge.py -v`
Expected: FAIL

- [ ] **Step 3: 移植策略逻辑**

`ndx_momentum_hedge.py`：移植 `C:\Users\cccbqn\strategies\ndx-momentum-hedge\server.py` 的 `NDX_100`（L22-33）、`build_report`（L90-206）核心逻辑，数据获取改为 yfinance：
```python
"""NDX 动量对冲策略（移植自 wepoets1107/ndx-momentum-hedge，MIT）。
纳斯达克100动量选股 + PSQ 1x 反向 QQQ 对冲，周频调仓。
"""
import time
import yfinance as yf
from datetime import datetime

TOP_K = 5
LOOKBACK = 20

NDX_100 = [
    "NVDA","AAPL","AVGO","META","MU","MSFT","AMD","AMZN","TSLA","GOOGL",
    "GOOG","INTC","ASML","CSCO","COST","AMAT","LRCX","NFLX","PLTR","PANW",
    "ARM","TXN","KLAC","LIN","AMGN","CRWD","PEP","ADBE","ADI",
    "QCOM","BKNG","WDAY","MRVL","INTU","CDNS","SNPS","PCAR","NXPI","FTNT",
    "MCHP","ROP","ODFL","MAR","CPRT","ORLY","CTAS","PAYX","AZN","MNST",
    "KDP","DASH","DDOG","MDB","TTD","TEAM","KHC","XEL","EXC",
    "GEHC","CSGP","BKR","ROST","LULU","IDXX","FAST","EA","VRTX","REGN",
    "GFS","SBUX","CMCSA","ADP","MELI","GILD","MDLZ","ZS","WBD","PDD","MRNA","DXCM",
    "CRM","NOW","ISRG","BIIB","CEG","CDW","CHTR","DLTR","FANG","ILMN",
    "MSTR","ON","PYPL","RIVN","SMCI","TTWO","VRSK","ZM",
]

def _fetch_prices(tickers):
    """yfinance 批量下载 60 天日线（adj close），返回 {ticker: {date: price}}"""
    data = yf.download(tickers + ["QQQ", "PSQ"], period="60d", interval="1d",
                       auto_adjust=True, progress=False, threads=True)
    close = data["Close"]
    out = {}
    for t in close.columns:
        t = str(t)
        out[t] = {d.strftime("%Y-%m-%d"): float(v) for d, v in close[t].dropna().items()}
        time.sleep(0.1)
    return out

def _momentum(prices, ticker, dates):
    vals = [prices.get(ticker, {}).get(d) for d in dates[-LOOKBACK:] if prices.get(ticker, {}).get(d)]
    if len(vals) < 2:
        return None, None
    return round((vals[-1] / vals[0] - 1) * 100, 1), vals[-1]

def run_ndx_momentum_hedge():
    prices = _fetch_prices(NDX_100)
    qqq_dates = sorted(prices.get("QQQ", {}).keys())
    if not qqq_dates:
        return {"error": "数据获取失败"}
    today = qqq_dates[-1]
    last_week = qqq_dates[-5]
    week_start = qqq_dates[-6]
    # 动量排名 + 方案B选股（20日动量>0，按5日动量取前5）
    momentum_list = []
    for tkr in NDX_100:
        mom, price = _momentum(prices, tkr, qqq_dates)
        if mom is None or price is None:
            continue
        p_wk, p_now = prices.get(tkr, {}).get(week_start), prices.get(tkr, {}).get(today)
        mom5 = round((p_now / p_wk - 1) * 100, 1) if p_wk and p_now and p_wk > 0 else None
        momentum_list.append({"symbol": tkr, "momentum": mom, "momentum_5d": mom5, "price": round(price, 2)})
    qualified = [m for m in momentum_list if m["momentum"] > 0 and m["momentum_5d"] is not None]
    qualified.sort(key=lambda x: x["momentum_5d"], reverse=True)
    top_k = qualified[:TOP_K]
    qqq_now, qqq_lw = prices.get("QQQ", {}).get(today), prices.get("QQQ", {}).get(last_week)
    psq_now, psq_lw = prices.get("PSQ", {}).get(today), prices.get("PSQ", {}).get(last_week)
    qqq_w = round((qqq_now / qqq_lw - 1) * 100, 1) if qqq_now and qqq_lw else 0
    psq_w = round((psq_now / psq_lw - 1) * 100, 1) if psq_now and psq_lw else 0
    return {
        "date": today, "week_start": week_start,
        "pool_size": len(momentum_list),
        "momentum_top5": top_k,
        "top_symbols": [m["symbol"] for m in top_k],
        "performance": {"strategy_w": round(sum(m.get("momentum_5d", 0) for m in top_k) / max(1, len(top_k)) * 0.5 + psq_w * 0.5, 1),
                        "qqq_w": qqq_w, "psq_w": psq_w},
        "full_momentum": momentum_list[:30],
    }
```

> 注意：yfinance 国内网络可能不稳定，Step 4 若超时/失败，改用原仓库的 Yahoo query2 直连方式（requests + crumb，见原 server.py L43-81）并缓存到 `data/cache/ndx_prices.pkl`。

- [ ] **Step 4: 运行测试**

Run: `.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_ndx_momentum_hedge.py -v`
Expected: PASS（若网络不通，按上方注意项切换数据获取方式）

- [ ] **Step 5: 新增 REST 端点**

`app/routers/strategy.py`：
```python
"""策略分析 API：NDX 动量对冲 / 龟龟估值 / 龟龟选股"""
from fastapi import APIRouter
from tradingagents.strategies.ndx_momentum_hedge import run_ndx_momentum_hedge

router = APIRouter()

@router.get("/ndx-momentum")
async def ndx_momentum():
    return {"success": True, "data": run_ndx_momentum_hedge()}

@router.get("/health")
async def strategy_health():
    return {"success": True, "data": {"strategies": ["ndx-momentum"]}}
```

`app/main.py` 的 include_router 区（约 L686-703）加一行：
```python
from app.routers import strategy  # 顶部 import 区
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
```

- [ ] **Step 6: 重启后端验证端点**

Run（重启 serve_prod 后）：`Invoke-WebRequest http://127.0.0.1:8000/api/strategy/health`
Expected: 200，返回 strategies 列表

- [ ] **Step 7: 提交**

```bash
git add tradingagents/strategies/ndx_momentum_hedge.py app/routers/strategy.py app/main.py
git commit -m "feat: 整合 NDX 动量对冲策略（yfinance 数据 + REST API）"
```

---

### Task 3: 龟龟估值引擎移植

**Files:**
- Create: `tradingagents/strategies/turtle_valuation.py`
- Modify: `app/routers/strategy.py`（加估值端点）
- Test: `tradingagents/strategies/test_turtle_valuation.py`

**Interfaces:**
- Consumes: `get_pro_api()`（Task 1）
- Produces: `run_turtle_valuation(ts_code: str) -> dict`（classification/wacc/method_results/cross_validate/reverse/markdown_report）

- [ ] **Step 1: 写失败测试**

```python
from tradingagents.strategies.turtle_valuation import run_turtle_valuation

def test_valuation_000001():
    r = run_turtle_valuation("000001")
    assert "classification" in r and "method_results" in r
    assert "dcf" in r["method_results"] or "pe_band" in r["method_results"]
```

- [ ] **Step 2: 确认失败**

Run: `.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_turtle_valuation.py -v`
Expected: FAIL

- [ ] **Step 3: 移植 ValuationEngine**

复制 `C:\Users\cccbqn\strategies\Turtle_investment_framework\scripts\valuation_engine.py` 到 `tradingagents/strategies/turtle_valuation.py`，改动点：
- 顶部 import 保留原版权注释，`from tushare_collector import TushareClient`（L1495）改为 `from tradingagents.strategies.akshare_tushare_bridge import get_pro_api`
- `main()` 的 client 构造替换为 `get_pro_api()`
- 新增模块级入口：
```python
def run_turtle_valuation(ts_code: str) -> dict:
    from .akshare_tushare_bridge import get_pro_api
    client = get_pro_api()
    from .valuation_engine import ValuationEngine
    engine = ValuationEngine(ts_code=ts_code, output_dir="data/strategies/valuation", client=client)
    ...
```
> 若复制后模块内相对 import 报错（原代码用 `from tushare_modules.xxx import`），把 `tushare_modules/` 目录一并复制到 `tradingagents/strategies/tushare_modules/` 并保持相对 import。
> 注意：原 `TushareClient` 的 `__init__` 签名可能是 `(token)`，桥接层 `get_pro_api()` 无参数——若 ValuationEngine 构造时传 client，需保证与桥接层返回对象兼容（实现 `daily_basic/income/...` 方法即可）。

- [ ] **Step 4: 运行测试并修正**

Run: `.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_turtle_valuation.py -v`
Expected: PASS

- [ ] **Step 5: 加 REST 端点**

`app/routers/strategy.py` 追加：
```python
@router.get("/turtle-valuation/{ts_code}")
async def turtle_valuation(ts_code: str):
    from tradingagents.strategies.turtle_valuation import run_turtle_valuation
    return {"success": True, "data": run_turtle_valuation(ts_code)}
```

- [ ] **Step 6: 重启验证 + 提交**

Run: `Invoke-WebRequest http://127.0.0.1:8000/api/strategy/turtle-valuation/000001` Expected: 200
```bash
git add tradingagents/strategies/ app/routers/strategy.py
git commit -m "feat: 整合龟龟估值引擎（DCF/DDM/PE Band/PEG/PS，akshare 数据）"
```

---

### Task 4: 龟龟选股器移植

**Files:**
- Create: `tradingagents/strategies/turtle_screener.py`
- Modify: `app/routers/strategy.py`
- Test: `tradingagents/strategies/test_turtle_screener.py`

**Interfaces:**
- Consumes: `get_pro_api()`
- Produces: `run_turtle_screener(tier1_only: bool = False, tier2_limit: int | None = None) -> dict`

- [ ] **Step 1: 写失败测试**

```python
from tradingagents.strategies.turtle_screener import run_turtle_screener

def test_tier1():
    r = run_turtle_screener(tier1_only=True, tier2_limit=5)
    assert "candidates" in r and isinstance(r["candidates"], list)
```

- [ ] **Step 2: 确认失败**

- [ ] **Step 3: 移植 screener_core**

复制 `C:\Users\cccbqn\strategies\Turtle_investment_framework\scripts\screener_core.py` 到 `tradingagents/strategies/turtle_screener.py`，同样把 `ts.pro_api(token)` 替换为 `get_pro_api()`（`_get_pro` L100 处）。Tier1 的 `_tier1_bulk_data` 依赖 `daily_basic(trade_date=...)` + `stock_basic()`——桥接层已实现；Tier2 逐股依赖 `fina_indicator/income/balancesheet/cashflow/dividend/weekly`——桥接层已实现。
> 若 `screener_config.py` 有依赖一并复制。`run()` 返回 DataFrame，`run_turtle_screener` 包装成 dict（candidates/params）。

- [ ] **Step 4: 运行测试修正**

- [ ] **Step 5: 加 REST 端点**

```python
@router.get("/turtle-screener")
async def turtle_screener(tier1_only: bool = True, tier2_limit: int = 10):
    from tradingagents.strategies.turtle_screener import run_turtle_screener
    return {"success": True, "data": run_turtle_screener(tier1_only=tier1_only, tier2_limit=tier2_limit)}
```

- [ ] **Step 6: 重启验证 + 提交**

---

### Task 5: 前端"策略分析"页面

**Files:**
- Create: `frontend/src/views/Analysis/Strategy.vue`
- Modify: `frontend/src/router/index.ts`（`/analysis` children 加 strategy 路由）
- Modify: `frontend/src/components/Layout/SidebarMenu.vue`（加"策略分析"菜单项）
- Modify: `frontend/src/api/strategy.ts`（新建 API 封装）

**Interfaces:**
- Consumes: `GET /api/strategy/ndx-momentum`、`/turtle-valuation/{code}`、`/turtle-screener?tier1_only=..&tier2_limit=..`
- Produces: Strategy.vue（三个 tab：NDX 动量对冲 / 龟龟估值 / 龟龟选股）

- [ ] **Step 1: 写 API 封装 `frontend/src/api/strategy.ts`**

```typescript
import request from '@/utils/request'

export const strategyApi = {
  ndxMomentum: () => request.get('/api/strategy/ndx-momentum'),
  turtleValuation: (code: string) => request.get(`/api/strategy/turtle-valuation/${code}`),
  turtleScreener: (params: { tier1_only?: boolean; tier2_limit?: number }) =>
    request.get('/api/strategy/turtle-screener', { params }),
}
```

- [ ] **Step 2: 新建 Strategy.vue**（Element Plus，三个 el-tab：NDX 信号卡片表格 / 估值表单+结果 Markdown / 选股结果表格），参考 `frontend/src/views/Screening/index.vue` 的表格写法与 `SingleAnalysis.vue` 的 markdown 渲染（`vue3-markdown-it` 已装）

- [ ] **Step 3: 注册路由**（`frontend/src/router/index.ts` 的 `/analysis` children，约 L58-70）：
```typescript
{ path: 'strategy', name: 'Strategy', component: () => import('@/views/Analysis/Strategy.vue'), meta: { title: '策略分析' } }
```

- [ ] **Step 4: 菜单**（`frontend/src/components/Layout/SidebarMenu.vue` L19-28 股票分析子菜单）加：
```vue
<el-menu-item index="/analysis/strategy">策略分析</el-menu-item>
```

- [ ] **Step 5: 重新构建前端 + 验证**

Run: `cd frontend && npm run build`
Expected: 构建成功
验证：重启 serve_prod 后访问 `http://127.0.0.1:8000/analysis/strategy`（登录后）

- [ ] **Step 6: 提交**

```bash
git add frontend/
git commit -m "feat: 前端新增策略分析页面（NDX 动量/龟龟估值/龟龟选股）"
```

---

### Task 6: 基本面分析师注入估值结果（增强）

**Files:**
- Modify: `tradingagents/agents/utils/agent_utils.py`（`Toolkit.get_stock_fundamentals_unified` 各市场分支，约 L695/L853-987）
- Test: `tradingagents/strategies/test_integration_in_analyst.py`

- [ ] **Step 1: 写集成测试**（验证 fundamentals 工具返回文本中包含估值段落）

- [ ] **Step 2: 在 `get_stock_fundamentals_unified` 的 A 股分支（`_generate_fundamentals_report` 之后）追加估值输出**

```python
# 追加：龟龟估值摘要（异常时静默跳过，不影响主流程）
try:
    from tradingagents.strategies.turtle_valuation import run_turtle_valuation
    val = run_turtle_valuation(symbol)
    result_data += f"\n\n## 估值引擎摘要\n" + str(val.get("summary", ""))[:2000]
except Exception:
    pass
```

- [ ] **Step 3: 运行测试 + 提交**

---

### Task 7: 收尾

- [ ] **Step 1: 运行全部新测试**：`.\env\Scripts\python.exe -m pytest tradingagents/strategies/ -v` 全绿
- [ ] **Step 2: 端到端验证**：启动股神，页面访问三个策略 tab，各返回正常数据
- [ ] **Step 3: 写 `tradingagents/strategies/README.md`**：说明三个模块用法、数据源、LICENSE 归属（原仓库链接 + MIT）
- [ ] **Step 4: 提交** `git add -A && git commit -m "docs: 策略模块文档"`；推送到用户 fork 前先与用户确认
