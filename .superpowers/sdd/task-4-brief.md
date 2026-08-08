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


