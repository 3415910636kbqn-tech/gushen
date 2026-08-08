### Task C: Alpha Zoo 算子 + 精选因子（Vibe factors）

**Files:**
- Create: `tradingagents/strategies/factors/__init__.py`、`operators.py`、`factors.py`（精选 30 个）
- Test: `tradingagents/strategies/test_factors.py`

**范围：**
- 算子（移植 Vibe `agent/src/factors/base.py` 核心）：rank / scale / ts_mean / ts_std / ts_delay / ts_max / ts_min / delta / decay_linear / safe_div / vwap / ts_sum / ts_argmax / ts_corr（pandas 实现）
- 精选 30 个因子：动量类（MOM/ROC/RSI-based）、均值回复、波动类、量价类（OBV/VR）、基本面类（ROE/PE 变化）——从 qlib158/alpha101/gtja191 各挑常用
- `FACTOR_REGISTRY: dict[str, callable]`，`compute_factor(df, name)` / `compute_factor_panel(df, names)`

**接入：** 选股器增强——`app/routers/strategy.py` 加 `GET /api/strategy/factors`（列表）和 `POST /api/strategy/factor-screen`（传因子+阈值筛选，数据走桥接层全市场快照）

- [ ] 算子测试（rank 单调性/scale 标准化/ts_delay 移位）→ 失败 → 实现
- [ ] 因子测试（对构造的上升/下降序列，动量因子符号正确）→ 失败 → 实现
- [ ] REST 端点 + 验证 → 提交 `feat: Alpha 因子库（算子+精选30因子+因子选股）`

---


