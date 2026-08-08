"""风险度量：VaR（历史模拟/参数法）、CVaR、最大回撤（Vibe quantlib risk.py 精选移植）。

符号约定（与参考源码一致）：
**损失为正数。** 本模块返回的每个风险"大小"均为非负，并随风险恶化而增大：
* ``historical_var`` / ``parametric_var`` -- ``0.028`` 表示"2.8% 的损失"。
* ``historical_cvar`` -- ``0.042`` 表示"尾部平均 4.2% 的损失"。
* ``max_drawdown_analysis()["max_drawdown"]`` -- ``0.325`` 表示"32.5% 的峰谷回撤"。

分位数约定：``historical_var`` 取**非插值下阶统计量** -- 升序排序后取
``ceil((1-confidence)*n) - 1`` 位并取负。``historical_cvar`` 对不高于该阶统计量
的所有收益（含该点）取平均，这正是标准期望缺口，因此天然保证 ``cvar >= var``。
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

__all__ = ["historical_var", "parametric_var", "historical_cvar", "max_drawdown_analysis"]

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _norm_ppf(p: float) -> float:
    """标准正态分位数（Acklam 近似 + Newton 精化，无 scipy 依赖）。"""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow = 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    elif p > 1.0 - plow:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    else:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
            ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    # Newton 精化：cdf 与 pdf 都由 math.erf 给出，收敛到机器精度。
    for _ in range(10):
        err = _norm_cdf(x) - p
        if abs(err) < 1e-15:
            break
        x = x - err * _SQRT2PI * math.exp(x * x / 2.0)
    return x


def _clean_returns(returns: pd.Series | np.ndarray | Sequence[float]) -> np.ndarray:
    """把收益序列规整为有限 1-D float 数组，剔除 NaN/inf。

    Raises:
        ValueError: 输入不是 1-D，或不含任何有限观测。
    """
    values = np.asarray(returns, dtype=float)
    if values.ndim > 1:
        raise ValueError(f"returns must be 1-D, got shape {values.shape}")
    values = values.ravel()
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError("returns contains no finite observation")
    return finite


def _validate_confidence(confidence: float) -> None:
    """置信度必须在 (0, 1) 开区间。"""
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")


def _validate_horizon(horizon: int) -> None:
    """持有期必须 >= 1。"""
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")


def _tail_index(n: int, confidence: float) -> int:
    """升序样本中 VaR 阶统计量的位置：``ceil((1-confidence)*n) - 1``，夹紧到 ``[0, n-1]``。"""
    return int(min(max(math.ceil((1.0 - confidence) * n) - 1, 0), n - 1))


def historical_var(
    returns: pd.Series | np.ndarray | Sequence[float],
    confidence: float = 0.95,
    horizon: int = 1,
) -> float:
    """历史模拟法 VaR：从经验分布直接读取 ``1 - confidence`` 阶损失。

    Returns:
        正的损失大小（如 0.028 表示 2.8% 损失）。尾部没有损失时可能返回负值（即收益）。

    Raises:
        ValueError: 无有限观测、置信度越界或 horizon < 1。
    """
    _validate_confidence(confidence)
    _validate_horizon(horizon)
    values = np.sort(_clean_returns(returns))
    quantile_return = values[_tail_index(values.size, confidence)]
    return float(-quantile_return * math.sqrt(horizon))


def parametric_var(
    returns: pd.Series | np.ndarray | Sequence[float],
    confidence: float = 0.95,
    horizon: int = 1,
) -> float:
    """参数法 VaR：对收益拟合正态分布，``-(mu + z*sigma) * sqrt(horizon)``，z=norm.ppf(1-confidence)。"""

    _validate_confidence(confidence)
    _validate_horizon(horizon)
    values = _clean_returns(returns)
    if values.size < 2:
        raise ValueError("parametric_var needs at least 2 observations for a std estimate")
    mu = float(values.mean())
    sigma = float(values.std(ddof=1))
    z = _norm_ppf(1.0 - confidence)
    return float(-(mu + z * sigma) * math.sqrt(horizon))


def historical_cvar(
    returns: pd.Series | np.ndarray | Sequence[float],
    confidence: float = 0.95,
    horizon: int = 1,
) -> float:
    """历史模拟法 CVaR（期望缺口）：对不高于 VaR 阶统计量的所有收益取平均。"""

    _validate_confidence(confidence)
    _validate_horizon(horizon)
    values = np.sort(_clean_returns(returns))
    tail = values[: _tail_index(values.size, confidence) + 1]
    return float(-tail.mean() * math.sqrt(horizon))


def max_drawdown_analysis(equity: pd.Series | np.ndarray | Sequence[float]) -> dict:
    """定位净值曲线最深的峰谷回撤及其位置。

    Args:
        equity: 净值序列，须严格为正。pandas Series 保留索引，``peak``/``trough``
            返回索引标签；其他输入包装为 RangeIndex，返回整数位置。

    Returns:
        dict:
            max_drawdown (float): 最深回撤，**正值**分数（0.25 表示跌去 25%）；曲线不回撤时为 0.0。
            duration (int): 峰到谷的观测数。
            peak: 回撤前运行峰的索引标签/位置。
            trough: 最深点的索引标签/位置。

    Raises:
        ValueError: 非 1-D、无有限观测、或存在非正净值。
    """
    if not isinstance(equity, pd.Series):
        array = np.asarray(equity, dtype=float)
        if array.ndim > 1:
            raise ValueError(f"equity must be 1-D, got shape {array.shape}")
        equity = pd.Series(array)
    series = equity.astype(float)
    series = series[np.isfinite(series.to_numpy())]
    if series.empty:
        raise ValueError("equity contains no finite observation")
    values = series.to_numpy()
    if (values <= 0.0).any():
        raise ValueError("equity must be strictly positive to express drawdown as a fraction")

    running_peak = np.maximum.accumulate(values)
    drawdown = values / running_peak - 1.0
    trough_pos = int(np.argmin(drawdown))
    peak_pos = int(np.argmax(values[: trough_pos + 1]))
    index = series.index
    return {
        "max_drawdown": float(-drawdown[trough_pos]),
        "duration": trough_pos - peak_pos,
        "peak": index[peak_pos],
        "trough": index[trough_pos],
    }
