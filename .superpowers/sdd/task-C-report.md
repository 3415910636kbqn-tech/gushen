# Task C 报告：Alpha Zoo 算子 + 精选 30 因子 + 因子选股端点

## 状态
✅ 完成

## Commit
`3e27165` — feat: Alpha 因子库（算子+精选30因子+因子选股端点）（6 files changed, 1211 insertions）

## 移植算子清单（`tradingagents/strategies/factors/operators.py`，移植自 Vibe `agent/src/factors/base.py`，MIT）
宽表形态（index=日期, columns=股票代码），17 个算子：
- **截面**（按行）：`rank`（pct=True, ties=average, NaN 保持）、`zscore`（ddof=1，零 std→NaN）、`scale`（**L2**：每行平方和=a²，与 Vibe 原版 L1 不同，见下）
- **时序**（按列，warmup→NaN）：`ts_rank`（窗口内末值百分位，`sliding_window_view` 向量化）、`ts_mean`/`ts_std`(ddof=1)/`ts_max`/`ts_min`/`ts_argmax`/`ts_argmin`（0-based 窗口索引）、`delta`（d≥1，lookahead ban）、`decay_linear`（权重 n,n-1,…,1 归一化，窗口含 NaN→NaN）、`signed_power`
- **双序列/面板**：`safe_div`（除零/NaN→NaN，eps 公式 a/(b+eps·sign(b))）、`ts_corr`/`ts_cov`（min_periods=n，常数窗口→NaN）、`vwap`（equity_cn 用 amount×1000/(vol×100+1)，兼容 volume/vol 列名；其它走 typical price）

**与 Vibe 的两处有意差异**：① `scale` 按任务验收断言实现为 **L2**（平方和=a²）而非 Vibe 的 L1（绝对值和=a），模块 docstring 已注明；② 不依赖 bottleneck，ts_rank/decay_linear 用 numpy `sliding_window_view`，ts_argmax/argmin 用 `rolling().apply`。

## 30 因子清单（`factors/registry.py`，`FACTOR_REGISTRY`，每个带 name/display_name/category/description/requires）
- **动量（8）**：MOM_20、ROC_10（qlib158）、RSI_14（gtja）、ALPHA_001（alpha101 #1 Kakushadze）、TS_RANK_20、MOM_ACCEL、MA_CROSS_20_60（gtja）、MAX_20_RET（gtja Max 类）
- **均值回复（5）**：BIAS_20（gtja）、BOLL_DIST、REV_TS_RANK_20（gtja 反转）、RSV_20（qlib158，KDJ）、PSY_20（gtja）
- **波动（5）**：VOL_20、ATR_14（gtja，需 high/low）、VOL_CHG_5（gtja STD 类）、VOL_RATIO、RANGE_20（需 high/low）
- **量价（6）**：OBV_20、VR_20（gtja）、VOL_RATIO_5（量比）、CORR_20（qlib158）、VMA_20（qlib158）、VSUMP_10（qlib158）——均需 panel["vol"]
- **基本面（6）**：ROE_CHG_Q、PE_PCT_250、EP_TTM、BP、PEG、DV_TTM——需 panel 携带 roe/pe_ttm/pb/profit_yoy/dv_ttm，**缺失返回全 NaN 占位**（docstring 注明，不抛异常）

函数签名统一 `f(df, panel=None)`：`df` 为 close 宽表（主序列），`panel` 可选提供 high/low/vol/基本面等字段。`compute_factor(data, name)` 接受单 DataFrame（视为 close）或面板 dict；未知因子名抛 `KeyError`；`compute_factor_panel(data, names)` 批量返回 `{name: 同形 df}`。

## factor-screen 取舍说明（`factors/screener.py` + 端点）
全市场实时算因子不可行（数千只 × 单只日线 = 数千次网络请求），采用**受限/示例实现**：
- `POST /api/strategy/factor-screen` body：`{factor, condition: top|bottom, top_n, trade_date?, symbols?}`，**必须传 symbols 列表（≤50 只）**
- 每只经桥接层 `daily()` 拉最近 ~420 自然日历史 → 拼同形 OHLCV 宽表面板 → `compute_factor` → 每列取各自**最后一期非 NaN** 值 → 按 condition 排序取 top_n
- 行情拉取全失败 → `last_date=None` → 端点返回 **503**（注明需预计算）；因子依赖基本面字段而面板缺失 → 对应股票为 NaN 被剔除，响应带 `note` 说明
- 性能：单只日线请求约 5-20s（东财不稳时回退新浪），3 只实测 65s——**≤50 只约 10-20 分钟量级**，仅作示例/受限用途，生产应离线预计算全市场因子快照（报告 Concerns #1）

## 测试 / 端点结果
- `tradingagents/strategies/test_factors.py`：**19 passed**（`pytest -q`）。算子行为断言 7 个（rank 0-1 归一、scale 平方和=a²、ts_mean 窗口均值、delta 差分、decay_linear 加权和 10/6、safe_div 除零→NaN、ts_rank 窗口内排名 2/3）+ 其余算子烟雾；因子行为断言 5 个（上升序列 MOM_20 为正/RSI≈100、反转因子符号、BIAS>0、线性序列 VOL_20≈0、OBV_20 为正）+ 基本面占位/取值 + registry（同形/KeyError/批量）+ **全量 30 因子烟雾测试**。附带确认 test_indicators+test_chips 30 passed 无回归。
- 端点实测（TestClient + 真实 akshare 数据）：
  - `GET /api/strategy/factors`：无 token→**401**；带 token→**200**，count=30，返回 name/display_name/category/description
  - `POST /api/strategy/factor-screen`：无 symbols→400、未知因子→400、坏 token→401；真实数据（600519.SH/000001.SZ/300750.SZ，MOM_20 top 3）→**200**，`last_date=20260807`，排序 `[300750(+11.3%), 600519(+8.7%), 000001(+7.1%)]`

## Concerns
1. **性能**：factor-screen 受单只日线请求数限制（≤50 只，实测 3 只 65s）。生产需离线预计算全市场因子快照（面板缓存）——本实现已在 503 分支和 docstring 注明。
2. **`scale` 语义偏离 Vibe 原版**：按任务简报验收断言实现为 L2（平方和=a²）；若后续要对接 Vibe 原版 alpha101 组合需注意（原版为 L1 绝对值和=a）。
3. **基本面因子需外部截面数据**：端点当前只用 daily() OHLCV 面板，EP/BP/PE_PCT 等返回 NaN 被剔除；如需可用，需把 daily_basic/fina_indicator 转宽表纳入面板（离线预计算的一部分）。
4. **末值截面近似**：各股停牌/上市日期不同，取各自最后一期非 NaN 因子值近似截面，与严格同日截面有细微差异（示例可接受）。
5. **面板日期为 YYYYMMDD 字符串 index**：排序按字典序（定长 OK），未转 DatetimeIndex；跨年/拼接下游如有需要可再转换。
6. 本任务未改动 `C:\Users\cccbqn\strategies\` 任何文件。

---

# Task C 审查修复（2026-08-08）

## 状态
✅ 完成，全绿

## Commit
`f1659bd` — fix: 因子公式对齐 qlib158 原版 + 补 ts_delay/ts_sum 算子（6 files changed, 146 insertions, 27 deletions）

## 测试摘要
- `pytest tradingagents/strategies/test_factors.py -v`：**24 passed**（原 19 + 新增 5）
- 新增断言：`ts_delay`/`ts_sum` 数值、VSUMP_10 全正增量→1/全负→0、VMA_20 放量<1/缩量>1、CORR_20 log1p 线性→corr≈1、EP_TTM pe<=0→NaN
- 手工对照：VSUMP_10/VMA_20/CORR_20 在随机 40 日面板上与 Vibe 参考原版 compute() 逐步一致（`np.allclose(equal_nan=True) == True`）；screener skipped 冒烟通过（部分失败 3 条 skipped、全失败 last_date=None 带 skipped、全格式无效 ValueError）

## 每项处理说明
1. **三个 qlib158 因子公式对齐原版**（对照 `strategies/Vibe-Trading/agent/src/factors/zoo/qlib158/{vsump10,vma20,corr20}.py`）：
   - `VSUMP_10`：改为 `sum(max(Δvol,0))/sum(|Δvol|)`，Δvol=vol-vol.shift(1)，10 日窗口（原版首行 Δvol=NaN 按 `where(diff>0,0)` 处理为 0，行为与原版一致）
   - `VMA_20`：改为 `ma20(vol)/vol`（方向翻转，>1 缩量/<1 放量），注册表 description 与 docstring 同步
   - `CORR_20`：补 `log1p(vol)` → `ts_corr(close, log1p(vol), 20)`
   - 现有测试未断言这三个因子的旧值，无需回改旧断言；新增数值测试锁定新公式
2. **补 ts_delay/ts_sum**：`operators.py` 新增 `ts_delay(df,d)=df.shift(d)`（d≥1，lookahead ban）与 `ts_sum(df,n)=df.rolling(n).sum()`，均导出到 `__init__.py` 的 `__all__`
3. **EP_TTM 修复**：`safe_div(1,pe)` 后 `ep.where(pe>0)` → pe<=0（含负/零 PE）输出 NaN，与 docstring 一致
4. **factor-screen 失败清单**：`screener._daily_panel` 返回 `(panel, last_date, skipped)`，daily() 拉取失败/空数据/缺 trade_date 均记入 `skipped=[{symbol,error}]`；`screen_by_factor` 增加 symbols 格式校验（非 6 位数字且无 .SH/.SZ/.BJ 后缀 → 拒绝并计入 skipped，全无效抛 ValueError）；响应含 `skipped`；503 分支的 detail 附跳过原因摘要
5. **其他族系抽查**（qilib158/alpha101/gtja191/academic 标称因子）：
   - ROC_10 vs qlib158 roc10、MOM_20 vs roc20、RSV_20 vs rsv20、ALPHA_001 vs alpha101 alpha_001：公式与参考逐一比对**一致**
   - gtja191 标称因子（BIAS/PSY/VR/ATR/RSI 等）均为标准定义，名字与公式相符（PSY 为 0-1 占比、ATR 为 ATR/close 归一，docstring 均注明），**无需改动**
   - 结论：除已修的 VSUMP_10/VMA_20/CORR_20 外未发现其他"名字与公式不符"问题
6. 未修改 `C:\Users\cccbqn\strategies\` 任何文件（仅只读参考）
