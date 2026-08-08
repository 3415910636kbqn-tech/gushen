# Task D 报告：A股回测引擎

## 状态
✅ 完成。独立轻量回测引擎（不依赖 Vibe），10/10 单测通过，全量 `tradingagents/strategies` 111 passed，端点已注册，真实数据 smoke test 通过。

## Commit
`f87c2c9` feat: A股回测引擎（buy_hold/MA交叉/RSI/动量 + 交易成本）
- 新增 `tradingagents/strategies/backtest/__init__.py`、`engine.py`（723 行新增，含测试）
- 修改 `app/routers/strategy.py`：`POST /api/strategy/backtest`

## 测试摘要
`.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_backtest.py -v` → **10 passed, 1 warning in 0.88s**
（buy_hold 收益/权益曲线、MA 金叉死叉、RSI 超卖买入、动量持仓/空仓、T+1 同日拒卖、涨停拒买、跌停拒卖、手续费精确、空数据/非法参数 → error dict）

## 实现要点
- **数据**：`load_daily(symbol, start, end, data_source=None)` 复用桥接层 `ProClient.daily()`（东财前复权），补齐 open/high/low/close/volume（volume 由 vol 手换算成股）；`data_source` 可注入 fake。
- **交易模型**（A 股规则，docstring 说明简化口径）：
  - T+1：卖出时校验持仓买入日期，同日拒绝。
  - 涨跌停：±10%（ST 不区分）；简版用「当日 close 较前收 ≥+10% 拒买、≤-10% 拒卖」，首日无前收不限。
  - 手续费：佣金万2.5（双边、最低 5 元）+ 卖出印花税千0.5，过户费忽略。
  - 最小 100 股整手，买入数量向下取整且预留佣金。
  - 信号基于截至当日 close，当日收盘价成交；末日收盘强制平仓（估值性质，T+1 仍适用）。
- **内置策略**：`buy_hold`（首日全仓）/`ma_cross`（fast/slow 默认 5/20）/`rsi_reverse`（period/oversold/overbought 默认 14/30/70，复用 Task A `indicators.calc_rsi`）/`momentum`（lookback 默认 20）；`params["strategy_fn"]` 支持自定义信号函数。
- **返回**：`{symbol, period, initial_capital, final_value, total_return, annual_return(244 交易日), max_drawdown, sharpe(无风险 0), win_rate(按平仓), num_trades, trades, equity_curve, benchmark(同区间 buy_hold)}`；无数据/非法参数返回含 `error` 键 dict，不抛异常。

## 端点
`POST /api/strategy/backtest`（`Depends(get_current_user)` 认证）body `{symbol, strategy, start, end, params?, initial_capital?}`：
- symbol 校验 `^\d{6}$`（A 股无后缀）；start/end `^\d{8}$` 且 start<end；initial_capital>0。
- **安全边界**：strategy 仅白名单 4 个内置策略，拒绝 `strategy_fn`（防任意代码执行）。

## Concerns
1. **真实数据 buy_hold**（akshare 实拉）：
   - `600519`（茅台）2024-01-02~2024-06-28：一手约 15 万 > 10 万本金，买入被整手规则拒绝 → 0 交易、final=100000。这是正确行为（合理空值），但前端需提示"本金不足以买入一手"。
   - `000001`（平安银行）同区间：买 12900 股 @7.74，卖 @9.14，**total_return +17.95%、年化 +41.09%、max_drawdown 7.74%、sharpe 1.59**，benchmark 一致（buy_hold 即基准）。
2. 简化口径（已在 docstring 说明）：涨跌停用「当日 close 相对前收」判断且 ST/创业板 ±20% 不区分；成交为当日收盘价（无滑点/次日开盘模型）；末日强制平仓不受涨跌停限制。
3. 真实数据依赖 akshare 网络（本项目桥接层已有东财→新浪回退）；茅台场景提示了整手买入失败时结果偏"空"，建议后续对买入失败原因透出到前端。
4. 运行环境控制台为 GBK，`tradingagents.config` 的 emoji 日志会在 stdout 报 UnicodeEncodeError（无害噪音，pytest 结果不受影响）。
5. `num_trades` 定义为「完成平仓的交易对数」（买入+卖出算 1 笔），未平仓（如本金不足）为 0；`win_rate/sharpe/annual_return` 在数据不足时为 null。