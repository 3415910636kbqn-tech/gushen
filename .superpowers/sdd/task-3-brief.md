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


