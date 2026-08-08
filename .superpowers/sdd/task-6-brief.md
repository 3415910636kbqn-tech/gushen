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


