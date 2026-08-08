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


