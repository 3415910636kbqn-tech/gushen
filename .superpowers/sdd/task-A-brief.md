### Task A: 技术指标移植（stock-sdk indicators → pandas）

**Files:**
- Create: `tradingagents/strategies/indicators.py`
- Test: `tradingagents/strategies/test_indicators.py`

**范围**（移植 stock-sdk `src/indicators/*.ts` 的 17 个指标，pandas 实现）：
MA(SMA/EMA/WMA) / MACD / BOLL / KDJ / RSI / WR / BIAS / CCI / ATR / OBV / ROC / DMI / SAR / KC / 基础 round

**接口：**
```python
def calculate_indicators(df: pd.DataFrame, indicators: dict) -> dict
# df 需含 open/high/low/close/volume；indicators 例：
#   {"ma": {"periods": [5,10,20]}, "macd": {"fast":12,"slow":26,"signal":9}, "kdj": {}, "rsi": {"period":14}}
# 返回 {"ma": {...}, "macd": {...}, ...} 每个值是 pd.Series 或 dict
```
+ 单独函数 calc_sma/calc_macd/calc_kdj/calc_rsi/calc_boll/calc_atr/calc_obv 等（每个可独立调用）

- [ ] 写测试（用已知序列验证关键指标：如 SMA 简单平均、MACD 金叉位置、RSI 在涨跌序列上的值域 0-100）
- [ ] 确认失败 → 移植实现（对照 stock-sdk TS 源码算法）
- [ ] 测试全绿 → 提交 `feat: 技术指标库移植（MA/MACD/KDJ/RSI 等 17 个，pandas）`

---


