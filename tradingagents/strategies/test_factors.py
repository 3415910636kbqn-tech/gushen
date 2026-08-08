"""Alpha 因子库测试（Vibe base.py 算子移植 + 精选 30 因子 + registry）。

覆盖：
- 算子：rank 0-1 归一 / scale 平方和=a² / ts_mean 窗口均值 / delta 差分 /
  decay_linear 加权和 / safe_div 除零保护 / ts_rank 窗口内排名
- 因子：上升序列 MOM_20 为正、RSI 接近 100、反转因子符号正确、BIAS 符号、
  VOL_20 线性序列≈0、OBV_20 上涨为正、全量 30 因子烟雾测试
- registry：compute_factor 同形、未知因子名 KeyError、compute_factor_panel
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tradingagents.strategies.factors.operators import (
    rank,
    zscore,
    scale,
    ts_rank,
    ts_mean,
    ts_std,
    ts_max,
    ts_min,
    ts_argmax,
    ts_argmin,
    ts_delay,
    ts_sum,
    delta,
    decay_linear,
    signed_power,
    safe_div,
    ts_corr,
    ts_cov,
    vwap,
)
from tradingagents.strategies.factors.registry import (
    FACTOR_REGISTRY,
    compute_factor,
    compute_factor_panel,
)


def make_cs_wide(n_stocks=5, n_days=60, seed=42, start=10.0):
    """index=日期, columns=股票代码 的随机宽表（close 形态）。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-02", periods=n_days)
    cols = [f"{i:06d}" for i in range(1, n_stocks + 1)]
    close = start + np.cumsum(rng.normal(0.0, 0.1, (n_days, n_stocks)), axis=0)
    close = np.maximum(close, 1.0)
    return pd.DataFrame(close, index=dates, columns=cols)


def rising_close(n=40, start=10.0, step=0.5):
    return pd.DataFrame(
        {"000001": start + np.arange(n) * step},
        index=pd.bdate_range("2025-01-02", periods=n),
    )


def falling_close(n=40, start=30.0, step=0.5):
    return pd.DataFrame(
        {"000001": start - np.arange(n) * step},
        index=pd.bdate_range("2025-01-02", periods=n),
    )


def ohlcv_panel(df, seed=7):
    """从 close 宽表构造完整 OHLCV 面板（同形）。"""
    hi = df * 1.02
    lo = df * 0.98
    rng = np.random.default_rng(seed)
    vol = pd.DataFrame(
        np.abs(rng.normal(1e5, 2e4, df.shape)), index=df.index, columns=df.columns
    )
    return {
        "open": df,
        "high": hi,
        "low": lo,
        "close": df,
        "vol": vol,
        "amount": vol * 10.0,
    }


# ==================== 算子 ====================

def test_rank_pct_normalized():
    df = pd.DataFrame([[3.0, 1.0, 2.0], [5.0, 5.0, 1.0]], columns=["a", "b", "c"])
    out = rank(df)
    # 第一行 3,1,2 → pct rank 1.0, 1/3, 2/3（0-1 归一）
    assert np.allclose(out.iloc[0].to_numpy(), [1.0, 1 / 3, 2 / 3])
    assert out.min().min() >= 0.0 and out.max().max() <= 1.0
    # NaN 保持 NaN
    df2 = pd.DataFrame([[1.0, np.nan, 3.0]], columns=["a", "b", "c"])
    out2 = rank(df2)
    assert np.isnan(out2.iloc[0, 1])
    # pct rank 分母 = 非 NaN 数量（2 个）→ 0.5, NaN, 1.0
    assert np.allclose(out2.iloc[0, [0, 2]].to_numpy(), [0.5, 1.0])


def test_scale_square_sum_equals_a2():
    df = pd.DataFrame([[3.0, 4.0, 0.0]], columns=["a", "b", "c"])
    out = scale(df, a=2.0)
    sq = (out**2).sum(axis=1)
    assert np.allclose(sq, 4.0)  # 平方和 = a²
    assert np.allclose(out.iloc[0, 0], 3.0 / 5.0 * 2.0)
    assert np.allclose(out.iloc[0, 1], 4.0 / 5.0 * 2.0)
    # 零向量行 → NaN，不是 0
    df2 = pd.DataFrame([[0.0, 0.0]], columns=["a", "b"])
    out2 = scale(df2, a=1.0)
    assert out2.isna().all().all()


def test_ts_mean_window():
    s = pd.DataFrame({"a": [1.0, 2, 3, 4, 5]})
    out = ts_mean(s, 3)
    assert np.isnan(out.iloc[0, 0]) and np.isnan(out.iloc[1, 0])
    assert np.allclose(out["a"].iloc[2:].to_numpy(), [2.0, 3.0, 4.0])


def test_delta_lag():
    s = pd.DataFrame({"a": [1.0, 2, 4, 8, 16]})
    out = delta(s, 2)
    assert np.isnan(out.iloc[0, 0]) and np.isnan(out.iloc[1, 0])
    assert np.allclose(out["a"].iloc[2:].to_numpy(), [3.0, 6.0, 12.0])
    with pytest.raises(ValueError):
        delta(s, 0)


def test_decay_linear_weights():
    s = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    out = decay_linear(s, 3)
    assert np.isnan(out.iloc[0, 0]) and np.isnan(out.iloc[1, 0])
    # 权重 3,2,1 归一化 → (3*1+2*2+1*3)/6 = 10/6
    assert np.allclose(out.iloc[2, 0], 10.0 / 6.0)


def test_safe_div_zero_protection():
    a = pd.DataFrame({"x": [1.0, 2.0], "y": [4.0, 8.0]})
    b = pd.DataFrame({"x": [0.0, 2.0], "y": [0.0, np.nan]})
    out = safe_div(a, b)
    assert np.isnan(out.loc[0, "x"])  # 除零 → NaN
    assert np.isnan(out.loc[0, "y"])
    assert np.isnan(out.loc[1, "y"])  # NaN 分母 → NaN
    assert np.allclose(out.loc[1, "x"], 1.0)


def test_ts_rank_window_percentile():
    s = pd.DataFrame({"a": [1.0, 3.0, 2.0]})
    out = ts_rank(s, 3)
    assert np.isnan(out.iloc[0, 0]) and np.isnan(out.iloc[1, 0])
    # 窗口 [1,3,2]，last=2：小于者 1 个，等于者 1 个 → (1+0.5*2)/3 = 2/3
    assert np.allclose(out.iloc[2, 0], 2.0 / 3.0)


def test_ts_delay_shift():
    s = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
    out = ts_delay(s, 2)
    assert np.isnan(out.iloc[0, 0]) and np.isnan(out.iloc[1, 0])
    assert np.allclose(out["a"].iloc[2:].to_numpy(), [1.0, 2.0])
    with pytest.raises(ValueError):
        ts_delay(s, 0)  # lookahead ban


def test_ts_sum_window():
    s = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
    out = ts_sum(s, 2)
    assert np.isnan(out.iloc[0, 0])
    assert np.allclose(out["a"].iloc[1:].to_numpy(), [3.0, 5.0, 7.0])
    with pytest.raises(ValueError):
        ts_sum(s, 0)


def test_extra_operators_smoke():
    """其余算子抽查：不抛异常、输出同形。"""
    df = make_cs_wide()
    vol = ohlcv_panel(df)["vol"]
    ops = [
        lambda d: zscore(d),
        lambda d: ts_std(d, 20),
        lambda d: ts_max(d, 5),
        lambda d: ts_min(d, 5),
        lambda d: ts_argmax(d, 5),
        lambda d: ts_argmin(d, 5),
        lambda d: signed_power(d, 2.0),
        lambda d: ts_corr(d, vol, 20),
        lambda d: ts_cov(d, vol, 20),
    ]
    for op in ops:
        out = op(df)
        assert out.shape == df.shape
    # vwap：typical price 与 equity_cn（amount/volume）两条路径
    v = vwap(ohlcv_panel(df))
    assert v.shape == df.shape
    assert not v.isna().all().all()


# ==================== 因子 ====================

def test_mom20_positive_on_uptrend():
    df = rising_close()
    out = compute_factor(df, "MOM_20")
    assert out.shape == df.shape
    assert np.isnan(out.iloc[0, 0])  # warmup
    assert out.iloc[-1, 0] > 0


def test_rsi_near_100_on_uptrend():
    df = rising_close()
    out = compute_factor(df, "RSI_14")
    assert out.iloc[-1, 0] > 90.0


def test_reversal_factor_sign():
    rev_up = compute_factor(rising_close(), "REV_TS_RANK_20")
    rev_down = compute_factor(falling_close(), "REV_TS_RANK_20")
    assert rev_up.iloc[-1, 0] < 0    # 上升 → 反转信号偏空
    assert rev_down.iloc[-1, 0] > 0  # 下降 → 反转信号偏多


def test_bias_positive_above_ma():
    out = compute_factor(rising_close(), "BIAS_20")
    assert out.iloc[-1, 0] > 0


def test_vol_small_on_linear_trend():
    out = compute_factor(rising_close(), "VOL_20")
    assert out.iloc[-1, 0] < 0.02  # 线性序列收益近似恒定


def test_obv_positive_on_uptrend():
    df = rising_close()
    panel = {"close": df, "vol": pd.DataFrame({"000001": 100.0}, index=df.index)}
    out = compute_factor(panel, "OBV_20")
    assert out.iloc[-1, 0] > 0


def test_vsump10_delta_vol_formula():
    """VSUMP_10 = sum(max(Δvol,0))/sum(|Δvol|)（qlib158 vsump10）。

    单调递增量 → 全正增量 → 1.0；单调递减量 → 全负增量 → 0.0。
    首个完整窗口（前 10 行含首行 Δvol=NaN）为 NaN。
    """
    n = 25
    idx = pd.bdate_range("2025-01-02", periods=n)
    close = pd.DataFrame({"000001": 10.0 + np.arange(n) * 0.5}, index=idx)
    up = pd.DataFrame({"000001": 100.0 + np.arange(n) * 10.0}, index=idx)
    down = pd.DataFrame({"000001": 100.0 + np.arange(n) * -10.0}, index=idx)
    out_up = compute_factor({"close": close, "vol": up}, "VSUMP_10")
    out_down = compute_factor({"close": close, "vol": down}, "VSUMP_10")
    assert np.isnan(out_up.iloc[9, 0])          # 首个窗口含首行 NaN 增量
    assert np.allclose(out_up.iloc[-1, 0], 1.0)   # 全正增量 → 1
    assert np.allclose(out_down.iloc[-1, 0], 0.0)  # 全负增量 → 0


def test_vma20_ma_over_vol_formula():
    """VMA_20 = ma20(vol)/vol（qlib158 vma20）：>1 缩量、<1 放量。"""
    n = 40
    idx = pd.bdate_range("2025-01-02", periods=n)
    close = pd.DataFrame({"000001": 10.0 + np.arange(n) * 0.5}, index=idx)
    rising = pd.DataFrame({"000001": 1.0 + np.arange(n) * 1.0}, index=idx)
    falling = pd.DataFrame({"000001": 40.0 - np.arange(n) * 1.0}, index=idx)
    out_r = compute_factor({"close": close, "vol": rising}, "VMA_20")
    out_f = compute_factor({"close": close, "vol": falling}, "VMA_20")
    assert np.isnan(out_r.iloc[18, 0])          # warmup（19 行）
    assert out_r.iloc[-1, 0] < 1.0              # 递增 → 当日量 > 均值 → 放量 <1
    assert out_f.iloc[-1, 0] > 1.0              # 递减 → 当日量 < 均值 → 缩量 >1


def test_corr20_log1p_formula():
    """CORR_20 = ts_corr(close, log1p(vol), 20)：log1p(vol) 与 close 线性相关 → corr≈1。"""
    n = 30
    idx = pd.bdate_range("2025-01-02", periods=n)
    c = np.arange(1.0, n + 1.0)
    close = pd.DataFrame({"000001": c}, index=idx)
    vol = pd.DataFrame({"000001": np.exp(c / 100.0) - 1.0}, index=idx)
    out = compute_factor({"close": close, "vol": vol}, "CORR_20")
    assert np.isnan(out.iloc[18, 0])            # warmup（19 行）
    assert abs(out.iloc[-1, 0] - 1.0) < 1e-6


def test_fundamental_placeholder_and_value():
    df = make_cs_wide()
    # 无基本面数据 → NaN 占位（不抛异常）
    assert compute_factor(df, "EP_TTM").isna().all().all()
    assert compute_factor(df, "ROE_CHG_Q").isna().all().all()
    # 面板携带 pe_ttm → 1/pe
    pe = pd.DataFrame(10.0, index=df.index, columns=df.columns)
    out = compute_factor({"close": df, "pe_ttm": pe}, "EP_TTM")
    assert np.allclose(out, 0.1, equal_nan=True)
    # pe<=0（负/零 PE）→ NaN，不是负 EP
    pe_neg = pd.DataFrame(-5.0, index=df.index, columns=df.columns)
    out_neg = compute_factor({"close": df, "pe_ttm": pe_neg}, "EP_TTM")
    assert out_neg.isna().all().all()
    pe_zero = pd.DataFrame(0.0, index=df.index, columns=df.columns)
    out_zero = compute_factor({"close": df, "pe_ttm": pe_zero}, "EP_TTM")
    assert out_zero.isna().all().all()


# ==================== registry ====================

def test_compute_factor_same_shape_and_columns():
    df = make_cs_wide()
    panel = ohlcv_panel(df)
    for name in ["MOM_20", "ROC_10", "RSI_14", "VOL_20", "BIAS_20", "ATR_14",
                 "VR_20", "PE_PCT_250", "ALPHA_001"]:
        out = compute_factor(panel, name)
        assert out.shape == df.shape, name
        assert list(out.columns) == list(df.columns), name
        assert list(out.index) == list(df.index), name


def test_unknown_factor_keyerror():
    with pytest.raises(KeyError):
        compute_factor(make_cs_wide(), "NOT_A_FACTOR")


def test_compute_factor_panel_multi():
    df = make_cs_wide()
    out = compute_factor_panel(df, ["MOM_20", "ROC_10", "BIAS_20"])
    assert set(out) == {"MOM_20", "ROC_10", "BIAS_20"}
    for v in out.values():
        assert v.shape == df.shape


def test_all_30_factors_smoke():
    """全部因子在完整 OHLCV 面板上不抛异常、输出同形（抽查）。"""
    df = make_cs_wide(n_days=120, n_stocks=8)
    panel = ohlcv_panel(df)
    assert len(FACTOR_REGISTRY) == 30
    for name, meta in FACTOR_REGISTRY.items():
        out = compute_factor(panel, name)
        assert out.shape == df.shape, name
        assert isinstance(meta.display_name, str) and meta.description
