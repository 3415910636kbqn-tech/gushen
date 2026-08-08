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


