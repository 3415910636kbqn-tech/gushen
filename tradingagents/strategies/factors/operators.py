"""Alpha Zoo 截面/时序算子（pandas 实现）。

移植自 Vibe-Trading `agent/src/factors/base.py`（MIT），做两处调整：
1. **scale 采用 L2 归一**（使每行平方和 = a²），与原版 Vibe 的 L1（绝对值和 = a）
   不同——本任务验收断言按 L2（``sum(x²) = a²``），且 L2 保持欧氏长度语义。
2. 不依赖 bottleneck：``ts_rank`` / ``decay_linear`` 用 numpy
   ``sliding_window_view`` 向量化，``ts_argmax/ts_argmin`` 用
   ``rolling().apply``，无额外依赖。

数据形态（与 Vibe 一致）：
- **wide DataFrame**：``index = trading_date``（DatetimeIndex），
  ``columns = instrument_code``（str）。
- 时序算子（ts_* / delta / decay_linear）按**列**独立滚动；
  截面算子（rank / zscore / scale）按**行**（每个交易日横截面）计算。
- 每个算子返回与输入**同形**的 DataFrame，warmup / 缺失数据处 NaN，
  禁止 +/- inf（用 NaN 替代），不做隐式 fillna(0)。

Lookahead ban：``delta(df, d)`` 要求 ``d >= 1``；负移位形式（Ref(df, -n)）刻意不提供。
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


def _as_float(df: pd.DataFrame) -> pd.DataFrame:
    if df.dtypes.eq(np.float64).all():
        return df
    return df.astype(np.float64)


# ---------------- 截面算子 ----------------

def rank(df: pd.DataFrame) -> pd.DataFrame:
    """截面百分位排名（axis=1，ties=average，pct=True，0-1 归一）。

    NaN 输入保持 NaN；全 NaN 行输出全 NaN 行。
    """
    return df.rank(axis=1, method="average", pct=True, na_option="keep")


def zscore(df: pd.DataFrame) -> pd.DataFrame:
    """截面 z-score（axis=1，样本标准差 ddof=1）。

    行内标准差为 0 或 NaN 时该行输出 NaN（绝不静默置 0）。
    """
    df = _as_float(df)
    mean = df.mean(axis=1, skipna=True)
    std = df.std(axis=1, ddof=1, skipna=True)
    result = df.sub(mean, axis=0).div(std.where(std > 0), axis=0)
    return result.replace([np.inf, -np.inf], np.nan)


def scale(df: pd.DataFrame, a: float = 1.0) -> pd.DataFrame:
    """截面 L2 归一化：每行平方和 = a²（``x * a / sqrt(sum(x²))``）。

    与 Vibe base.py 原版 L1（sum|·|=a）不同，见模块 docstring。
    行内平方和为 0（或全 NaN）→ NaN，绝不静默置 0。
    """
    df = _as_float(df)
    sq_sum = (df**2).sum(axis=1, skipna=True)
    sq_sum = sq_sum.where(sq_sum > 0)  # 0 → NaN
    denom = np.sqrt(sq_sum)
    return df.mul(a).div(denom, axis=0)


# ---------------- 时序算子（按列滚动） ----------------

def ts_rank(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动窗口内最后一个值的百分位排名（per column），warmup（前 n-1 行）→ NaN。

    与截面 rank 兼容，输出 [0,1]。窗口内任一个 NaN → 输出 NaN
    （min_periods=n）。用 numpy ``sliding_window_view`` 向量化。
    """
    if n < 1:
        raise ValueError(f"ts_rank window must be >= 1, got {n}")

    def _last_rank(arr: np.ndarray) -> float:
        if np.isnan(arr).all():
            return np.nan
        last = arr[-1]
        if np.isnan(last):
            return np.nan
        valid = arr[~np.isnan(arr)]
        less = (valid < last).sum()
        eq = (valid == last).sum()
        return float((less + 0.5 * (eq + 1)) / valid.size)

    arr = df.to_numpy(dtype=np.float64)
    T, C = arr.shape
    if T < n:
        return df.rolling(window=n, min_periods=n).apply(_last_rank, raw=True)

    windows = sliding_window_view(arr, window_shape=n, axis=0)  # (T-n+1, C, n)
    last_vals = windows[:, :, -1]
    valid_mask = ~np.isnan(windows)
    less = np.sum(np.where(valid_mask, windows < last_vals[:, :, None], 0), axis=2)
    eq = np.sum(np.where(valid_mask, windows == last_vals[:, :, None], 0), axis=2)
    valid_count = valid_mask.sum(axis=2)
    rank_avg = less + 0.5 * (eq + 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = rank_avg / valid_count

    nan_any = (~valid_mask).any(axis=2)
    result = np.full((T, C), np.nan)
    result[n - 1 :] = np.where(nan_any, np.nan, pct)
    return pd.DataFrame(result, index=df.index, columns=df.columns)


def ts_mean(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动均值（per column），warmup → NaN。"""
    if n < 1:
        raise ValueError(f"ts_mean window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).mean()


def ts_sum(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动求和（per column），warmup → NaN。"""
    if n < 1:
        raise ValueError(f"ts_sum window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).sum()


def ts_std(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动样本标准差（ddof=1，per column），warmup → NaN。"""
    if n < 2:
        raise ValueError(f"ts_std window must be >= 2, got {n}")
    return df.rolling(window=n, min_periods=n).std(ddof=1)


def ts_max(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动最大值（per column），warmup → NaN。"""
    if n < 1:
        raise ValueError(f"ts_max window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).max()


def ts_min(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动最小值（per column），warmup → NaN。"""
    if n < 1:
        raise ValueError(f"ts_min window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).min()


def ts_argmax(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动窗口内最大值的位置（0-based 窗口内索引），warmup → NaN。"""
    if n < 1:
        raise ValueError(f"ts_argmax window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).apply(
        lambda a: np.nan if np.isnan(a).all()
        else float(np.argmax(np.where(np.isnan(a), -np.inf, a))),
        raw=True,
    )


def ts_argmin(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动窗口内最小值的位置（0-based 窗口内索引），warmup → NaN。"""
    if n < 1:
        raise ValueError(f"ts_argmin window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).apply(
        lambda a: np.nan if np.isnan(a).all()
        else float(np.argmin(np.where(np.isnan(a), np.inf, a))),
        raw=True,
    )


def ts_delay(df: pd.DataFrame, d: int) -> pd.DataFrame:
    """滞后移位 ``df.shift(d)``（回看 d 期，历史方向）。

    lookahead ban：``d >= 1`` 严格；``d == 0`` / 负移位（未来数据）不提供。
    """
    if d < 1:
        raise ValueError(f"ts_delay lag must be >= 1 (lookahead ban), got {d}")
    return df.shift(d)


def delta(df: pd.DataFrame, d: int) -> pd.DataFrame:
    """滞后差分 ``df - df.shift(d)``；lookahead ban：``d >= 1`` 严格。"""
    if d < 1:
        raise ValueError(f"delta lag must be >= 1 (lookahead ban), got {d}")
    return df - df.shift(d)


def decay_linear(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """线性衰减加权均值，权重 ``n, n-1, ..., 1`` 归一化；warmup → NaN。

    窗口内任一个 NaN → NaN。用 ``sliding_window_view`` + einsum 向量化，
    因果对齐：output[i] 只依赖 input[i-n+1:i+1]。
    """
    if n < 1:
        raise ValueError(f"decay_linear window must be >= 1, got {n}")
    weights = np.arange(n, 0, -1, dtype=np.float64)
    weights /= weights.sum()

    def _apply(arr: np.ndarray) -> float:
        if np.isnan(arr).any():
            return np.nan
        return float(np.dot(arr, weights))

    arr = df.to_numpy(dtype=np.float64)
    T, C = arr.shape
    if T < n:
        return df.rolling(window=n, min_periods=n).apply(_apply, raw=True)

    windows = sliding_window_view(arr, window_shape=n, axis=0)  # (T-n+1, C, n)
    nan_mask = np.isnan(windows).any(axis=2)
    weighted = np.where(nan_mask[..., np.newaxis], 0.0, windows)
    dot = np.einsum("ijk,k->ij", weighted, weights)

    result = np.full((T, C), np.nan)
    result[n - 1 :] = np.where(nan_mask, np.nan, dot)
    return pd.DataFrame(result, index=df.index, columns=df.columns)


def signed_power(df: pd.DataFrame, p: float) -> pd.DataFrame:
    """``sign(x) * |x|**p``——保号、不产生复数输出；NaN 保持 NaN。"""
    df = _as_float(df)
    arr = df.to_numpy(dtype=np.float64, na_value=np.nan)
    out = np.sign(arr) * np.power(np.abs(arr), p)
    return pd.DataFrame(out, index=df.index, columns=df.columns)


# ---------------- 双序列 / 面板 ----------------

def safe_div(a: pd.DataFrame, b: pd.DataFrame, eps: float = 1e-12) -> pd.DataFrame:
    """安全除法：``a / (b + eps * sign(b))``。

    ``b == 0`` 或 NaN 时结果为 NaN——绝不静默 inf 或 0。
    """
    a = _as_float(a)
    b = _as_float(b)
    sign = np.sign(b.to_numpy(dtype=np.float64, na_value=np.nan))
    denom_arr = b.to_numpy(dtype=np.float64, na_value=np.nan) + eps * sign
    denom = pd.DataFrame(denom_arr, index=b.index, columns=b.columns)
    result = a.div(denom)
    return result.replace([np.inf, -np.inf], np.nan)


def ts_corr(x: pd.DataFrame, y: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动 Pearson 相关（per column，min_periods=n）。常数序列窗口 → NaN。"""
    if n < 2:
        raise ValueError(f"ts_corr window must be >= 2, got {n}")
    x = _as_float(x)
    y = _as_float(y)
    cols = x.columns.union(y.columns)
    xa = x.reindex(columns=cols)
    ya = y.reindex(columns=cols)
    corr = xa.rolling(window=n, min_periods=n).corr(ya)
    return corr.replace([np.inf, -np.inf], np.nan)


def ts_cov(x: pd.DataFrame, y: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动样本协方差（per column，min_periods=n）。"""
    if n < 2:
        raise ValueError(f"ts_cov window must be >= 2, got {n}")
    x = _as_float(x)
    y = _as_float(y)
    cols = x.columns.union(y.columns)
    xa = x.reindex(columns=cols)
    ya = y.reindex(columns=cols)
    cov = xa.rolling(window=n, min_periods=n).cov(ya)
    return cov.replace([np.inf, -np.inf], np.nan)


def vwap(panel: Mapping[str, pd.DataFrame], market: str = "equity_cn") -> pd.DataFrame:
    """参考价 / 成交均价（市场相关）。

    - ``panel["vwap"]`` 存在 → 直接返回。
    - ``equity_cn``：``(amount * 1000) / (volume * 100 + 1)``——tushare
      daily.amount 单位为千元、vol 单位为手（100 股）；桥接层同此口径。
      兼容 ``volume`` / ``vol`` 两种列名。
    - 其它市场或 CN 面板缺 amount/volume：typical price ``(O+H+L+C)/4``
      （需 open/high/low/close）。
    - 缺所有必需列 → ``KeyError``。
    """
    if "vwap" in panel:
        return panel["vwap"]
    market = str(market).lower()
    if market == "equity_cn":
        vol = panel.get("volume", panel.get("vol"))
        if "amount" in panel and vol is not None:
            return safe_div(panel["amount"] * 1000.0, vol * 100.0 + 1.0)
    required = ("open", "high", "low", "close")
    missing = [k for k in required if k not in panel]
    if missing:
        raise KeyError(f"vwap({market}) requires panel keys {required}; missing {missing}")
    return (panel["open"] + panel["high"] + panel["low"] + panel["close"]) / 4.0
