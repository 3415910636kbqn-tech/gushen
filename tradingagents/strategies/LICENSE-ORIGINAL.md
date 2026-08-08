# 原仓库许可证记录（LICENSE-ORIGINAL）

`tradingagents/strategies/` 下的两个策略源码移植自以下 **MIT 许可** 的开源仓库。
按 MIT 条款，保留原作者的版权声明与许可文本。

---

## 1. 龟龟估值 / 选股框架（`turtle/`）

- **原仓库**：[terancejiang/Turtle_investment_framework](https://github.com/terancejiang/Turtle_investment_framework)
- **许可证**：MIT
- **移植文件**：
  - `tradingagents/strategies/turtle/valuation_engine.py`
  - `tradingagents/strategies/turtle/tushare_collector.py`
  - `tradingagents/strategies/turtle/tushare_modules/`
  - `tradingagents/strategies/turtle/screener_core.py` / `screener_config.py` / `screener_adapter.py`
  - `tradingagents/strategies/turtle/cache_utils.py` / `config.py` / `format_utils.py` 等
- **适配说明**：数据源替换为 akshare 桥接层（`tradingagents/strategies/akshare_tushare_bridge.py`），
  无需 tushare token；金额/单位语义对齐 tushare（详见桥接层 docstring）。

## 2. NDX 动量对冲策略（`ndx_momentum_hedge.py`）

- **原仓库**：[wepoets1107/ndx-momentum-hedge](https://github.com/wepoets1107/ndx-momentum-hedge)
- **许可证**：MIT
- **移植文件**：`tradingagents/strategies/ndx_momentum_hedge.py`

---

## MIT License

```
MIT License

Copyright (c) [原仓库作者]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
## 量化能力整合（2026-08-08）

- **Vibe-Trading**（HKUDS，MIT）：https://github.com/HKUDS/Vibe-Trading
  - `factors/operators.py` 算子、`factors/registry.py` 精选因子移植自 `agent/src/factors/`（base.py + zoo/qlib158 等）
  - `quantlib/` 移植自 `agent/src/quantlib/`（options/risk/performance/fundmath）
  - `backtest/` 借鉴 `agent/backtest/engines/`（china_a 的 A 股市场规则口径）
- **stock-sdk**（chengzuopeng，ISC）：https://github.com/chengzuopeng/stock-sdk
  - `indicators.py` 移植自 `src/indicators/*.ts`（17 个技术指标）
  - `chips.py` 移植自 `src/indicators/chip.ts`（东财 CYQ 筹码分布算法）
  - 前端 `stock-sdk` npm 包（行情 K 线）