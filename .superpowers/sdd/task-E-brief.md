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


