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


