# Task A 报告：技术指标库移植（stock-sdk → pandas）

**状态：完成** ｜ commit `38af413bd07216a5a7fe783514911511d684ce5b`
**文件：** `tradingagents/strategies/indicators.py`（约 1000 行）、`tradingagents/strategies/test_indicators.py`（20 个测试）

## 移植范围（17 个）

| 函数 | 对应 TS | 返回 |
|---|---|---|
| `calc_sma` | ma.ts `calcSMA` | Series |
| `calc_ema` | ma.ts `calcEMA` | Series |
| `calc_wma` | ma.ts `calcWMA` | Series |
| `calc_ma` | ma.ts `calcMA` | `{"ma5": …}`（periods×type=sma/ema/wma） |
| `calc_macd` | macd.ts | `{"dif","dea","macd"}` |
| `calc_boll` | boll.ts | `{"mid","upper","lower","bandwidth"}` |
| `calc_kdj` | kdj.ts | `{"k","d","j"}` |
| `calc_rsi` | rsi.ts | `{"rsi6","rsi12",…}`（Wilder 平滑，periods 复数） |
| `calc_wr` | wr.ts | `{"wr6","wr10"}` |
| `calc_bias` | bias.ts | `{"bias6","bias12",…}` |
| `calc_cci` | cci.ts | Series |
| `calc_atr` | atr.ts | `{"tr","atr"}` |
| `calc_obv` | obv.ts | `{"obv","obv_ma"}` |
| `calc_roc` | roc.ts | `{"roc","signal"}` |
| `calc_dmi` | dmi.ts | `{"pdi","mdi","adx","adxr"}` |
| `calc_sar` | sar.ts | `{"sar","trend","ep","af"}` |
| `calc_kc` | kc.ts | `{"mid","upper","lower","width"}` |
| `calculate_indicators` | addIndicators + registry | 组合 dict |

chip（筹码分布）不在范围，未移植。

## 算法要点（与 TS 严格对齐）

- **舍入**：实现 JS `Math.round` 语义（`floor(v*10^d + 0.5)/10^d`，非 Python 银行家舍入），默认 `decimals=3`；OBV/ROC/DMI/SAR/KC 保持裸浮点不舍入，与 TS 一致。
- **EMA**：前 `period-1` 根 null，以**前 period 根的 SMA 播种**（非 pandas `ewm` 首个值播种），之后 `ema = α·v + (1-α)·ema`；空值保持上一值；种子未集齐时逐根重试。
- **MACD**：`dif = round(EMA12) - round(EMA26)`（用已舍入 EMA 相减，与 TS 一致）；`dea = calcEMA(dif, signal)`；柱 `= round((dif - dea)*2)`；DEA 输入用未再舍入的 dif（TS 同）。
- **BOLL**：mid=舍入 SMA；std 按恒等式 `Σx² − 2m·Σx + n·m²`（m 为已舍入 mid，与 TS 口径一致），方差 clamp 到 0 防 NaN；bandwidth 用**未舍入**的 upper/lower 差。
- **KDJ**：单调队列滑窗最值；K/D 初值 50；窗口含 null 或 `highN==lowN` → 输出 null 且**不更新**状态。
- **RSI**：Wilder 平滑；种子窗口取 `changes[1..period]`（TS 已修正的窗口）；`avgLoss==0 → 100`、`avgGain==0 → 0`（纯涨/纯跌）。
- **CCI**：`md==0 → 0`（平段精确判定，不做滚动近似，与 TS 评估结论一致）。
- **ATR**：TR 首根 `H-L`，昨收 null 时退化 `H-L`；ATR 以近 period 根 TR 简单平均播种后 Wilder；非法周期（非整数/≤0）→ ATR 全 null（TR 仍算）。
- **OBV**：首根=volume（null→0）；涨加/跌减/平不变；null 根输出 null 但累计值保持。
- **DMI**：`+DM/−DM/TR` 逐根；`i==period` 时并入第 period 根（TS 修正）；ADX 种子窗 `dx[period..period+adxPeriod-1]` 简单平均后 Wilder；ADXR 滞后 adxPeriod 平均。
- **SAR**：跳过前导无效 bar 播种（`seed`），初始趋势按 seed 与其后首根 close 判断；回看 clamp 下限收紧到 `max(seed, i-2)`（TS R7-7 修正）。
- **KC**：mid=EMA(close, emaPeriod)（默认舍入 3）+ ATR(默认舍入 3)，upper/lower/width 不舍入。
- **组合入口**：实现 registry 的简写归一（`ma:[5,10]`→`{periods}`、`rsi:{period:14}`→`{periods:[14]}`）、macd 的 `fast/slow` 别名（简报示例用）、`type`→`ma_type`；入口校验必需列。

## 测试结果

`.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_indicators.py -v` → **20 passed**（0.86s）

覆盖：SMA/EMA/WMA/MA 已知小序列（`[1..5]`、period=3）；MACD 金叉（构造先跌后涨序列，断言金叉处 dif>dea 且柱>0）；RSI 值域 0–100 与纯涨≈100/纯跌≈0；BOLL/KC 中轨=对应均线且上≥中≥下；ATR 恒定波动=2；CCI 平段=0；KDJ 上涨后 K 高位且值域 0–100；WR/BIAS 值域与符号；OBV 涨加跌减精确序列 `[100,150,90,160,80,170]`；ROC/DMI/SAR 抽查；组合入口全量跑 + 缺列报错 + 索引对齐。

另做了独立对拍/健壮性检查：DMI period=2 手算前几根（+DI=66.667、ADX=100 逐位一致）、BOLL std 与手算 `Σ(x−m)²/n` 一致（最大偏差 3.5e-05，为 round(3) 输出所致）、空 DataFrame 与全 NaN 输入不抛异常、日期索引对齐。

## 偏差（与 TS 的已知差异）

1. **浮点求和顺序**：SMA/BOLL/OBV/ROC 的窗口和用 pandas `rolling`（pairwise 求和），TS 用 `SlidingWindowSum`（Kahan 补偿）——两者约 1ulp 差异；round(3) 后输出逐位一致，仅在"窗口均值恰好落在 x.xxx5"的刀尖值上可能差 ±0.001（TS 源码注释对同样问题有说明，属契约外）。
2. **null 表示**：TS 契约输入为 `number|null`，pandas 用 NaN 表示缺失，本实现将 NaN 一律视为 TS 的 null（TS 对 NaN/Infinity 属契约外输入）。
3. **WMA/EMA 种子求和**：TS 用普通循环加法，本实现用 numpy `sum()`（pairwise）——同样 ~1ulp 级差异。
4. **`calc_sma` 的 `period=0` 防御**：TS 未防御（0 周期会异常/出 NaN），本实现统一输出全 null（宽容语义，与 TS 对 ATR 非法周期的处理一致）。

## 备注

- 未修改 `C:\Users\cccbqn\strategies\`（只读参考）。
- `.superpowers/sdd/*.md` 与计划文档为未跟踪文件，本次提交仅含 `indicators.py` + `test_indicators.py`。
- 后续 Task B 可直接 `from tradingagents.strategies.indicators import calculate_indicators` 使用。
