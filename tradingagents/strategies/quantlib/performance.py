"""绩效度量：年化收益/波动、Sharpe/Sortino/Calmar、信息比、最大回撤（Vibe quantlib performance.py 精选移植）。

约定（与参考源码同风格）：
* 收益序列按周期（默认 244 个交易日/年）输入；所有比率均**年化**输出。
* 年化收益为**几何年化**：``(1+总收益)^(ppy/n) - 1``。
* 年化波动率为样本标准差（ddof=1）乘 ``sqrt(ppy)``。
* 最大回撤为**正值**分数（0.25 表示跌去 25%）。
* 对空/异常输入抛 ``ValueError``（明确错误）；对无波动意义的输入（如常量收益
  序列的 Sharpe）返回 ``None``。
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

__all__ = [
    "annualized_return",
    "annualized_volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "calmar_ratio",
    "information_ratio",
]

DEFAULT_PERIODS_PER_YEAR = 244
"""默认每年周期数（交易日）。调用方可按自己的频率覆盖。"""

#: 无波动判定阈值（相对数据量级）。常量序列的 std 也会留下 ~1e-18 的
#: 浮点残差（numpy 2.x 归约），须视为无波动而非极端比率。
_SPREAD_EPS = 1e-12


def _clean_returns(returns: pd.Series | np.ndarray | Sequence[float]) -> np.ndarray:
    """规整收益序列为有限 1-D float 数组，剔除 NaN/inf。

    Raises:
        ValueError: 非 1-D 或空（无有限观测）。
    """
    values = np.asarray(returns, dtype=float)
    if values.ndim > 1:
        raise ValueError(f"returns must be 1-D, got shape {values.shape}")
    values = values.ravel()
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError("returns contains no finite observation")
    return finite


def _clean_equity(equity: pd.Series | np.ndarray | Sequence[float]) -> np.ndarray:
    """规整净值序列为严格正的 1-D float 数组。"""
    if not isinstance(equity, pd.Series):
        array = np.asarray(equity, dtype=float)
        if array.ndim > 1:
            raise ValueError(f"equity must be 1-D, got shape {array.shape}")
        equity = pd.Series(array)
    values = equity.astype(float).to_numpy()
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValueError("equity contains no finite observation")
    if (values <= 0.0).any():
        raise ValueError("equity must be strictly positive to express drawdown as a fraction")
    return values


def _is_flat_spread(spread: float, scale: float) -> bool:
    """spread 相对数据量级可忽略（浮点残差级别）即视为无波动。"""
    return not math.isfinite(spread) or spread <= _SPREAD_EPS * max(scale, 1e-300)


def annualized_return(returns: pd.Series | np.ndarray | Sequence[float],
                      periods_per_year: int = DEFAULT_PERIODS_PER_YEAR) -> float | None:
    """几何年化收益率：``(1+总收益)^(ppy/n) - 1``。

    Returns:
        年化收益率（如 0.08 表示 8%）。总收益 <= -100%（净值归零）时几何年化无意义，
        返回 ``None``。

    Raises:
        ValueError: ``returns`` 为空或非 1-D，``periods_per_year`` 非正。
    """
    if periods_per_year < 1:
        raise ValueError(f"periods_per_year must be >= 1, got {periods_per_year}")
    values = _clean_returns(returns)
    total = float(np.prod(1.0 + values))
    if not math.isfinite(total) or total <= 0.0:
        return None
    return float(total ** (periods_per_year / values.size) - 1.0)


def annualized_volatility(returns: pd.Series | np.ndarray | Sequence[float],
                          periods_per_year: int = DEFAULT_PERIODS_PER_YEAR) -> float:
    """年化波动率：``std(ddof=1) * sqrt(ppy)``。"""
    if periods_per_year < 1:
        raise ValueError(f"periods_per_year must be >= 1, got {periods_per_year}")
    values = _clean_returns(returns)
    if values.size < 2:
        raise ValueError(f"annualized_volatility needs at least 2 observations, got {values.size}")
    return float(values.std(ddof=1) * math.sqrt(periods_per_year))


def sharpe_ratio(returns: pd.Series | np.ndarray | Sequence[float],
                 rf: float = 0.0,
                 periods_per_year: int = DEFAULT_PERIODS_PER_YEAR) -> float | None:
    """年化 Sharpe 比率。

    超额收益 ``excess = returns - rf/ppy``（rf 为年化），
    ``sharpe = mean(excess)/std(excess, ddof=1) * sqrt(ppy)``。

    Returns:
        年化 Sharpe。超额收益无波动（如常量序列）时返回 ``None``。

    Raises:
        ValueError: 观测数 < 2 或 ``periods_per_year`` 非正。
    """
    if periods_per_year < 1:
        raise ValueError(f"periods_per_year must be >= 1, got {periods_per_year}")
    values = _clean_returns(returns)
    if values.size < 2:
        raise ValueError(f"sharpe_ratio needs at least 2 observations, got {values.size}")
    excess = values - rf / periods_per_year
    spread = float(excess.std(ddof=1))
    scale = float(np.max(np.abs(excess)))
    if _is_flat_spread(spread, scale):
        return None
    return float(excess.mean() / spread * math.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series | np.ndarray | Sequence[float],
                  rf: float = 0.0,
                  periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
                  target: float = 0.0) -> float | None:
    """年化 Sortino 比率：只惩罚下行波动。

    下行偏差 ``downside_dev = sqrt(mean(min(0, excess-target)^2))``（按样本数 n 平均），
    ``sortino = mean(excess) / downside_dev * sqrt(ppy)``。

    Returns:
        年化 Sortino。下行偏差为 0 时返回 ``None``。
    """
    if periods_per_year < 1:
        raise ValueError(f"periods_per_year must be >= 1, got {periods_per_year}")
    values = _clean_returns(returns)
    if values.size < 2:
        raise ValueError(f"sortino_ratio needs at least 2 observations, got {values.size}")
    excess = values - rf / periods_per_year
    downside = np.minimum(excess - target, 0.0)
    dev = float(np.sqrt(np.mean(downside ** 2)))
    scale = float(np.max(np.abs(downside)))
    if _is_flat_spread(dev, scale):
        return None
    return float(excess.mean() / dev * math.sqrt(periods_per_year))


def max_drawdown(equity: pd.Series | np.ndarray | Sequence[float]) -> float:
    """最大回撤（**正值**分数）：``1 - min(equity / running_peak)``。"""
    values = _clean_equity(equity)
    running_peak = np.maximum.accumulate(values)
    drawdown = values / running_peak - 1.0
    return float(-drawdown.min())


def calmar_ratio(returns: pd.Series | np.ndarray | Sequence[float],
                 equity: pd.Series | np.ndarray | Sequence[float] | None = None,
                 periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
                 rf: float = 0.0) -> float | None:
    """Calmar 比率：``(年化收益 - rf) / 最大回撤``。

    Args:
        returns: 周期收益序列。
        equity: 净值曲线。为 ``None`` 时由 ``cumprod(1+returns)`` 构造。
        periods_per_year: 每年周期数。rf: 年化无风险利率。

    Returns:
        Calmar 比率。最大回撤为 0 或年化收益无定义时返回 ``None``。
    """
    values = _clean_returns(returns)
    if equity is None:
        equity = np.cumprod(1.0 + values)
    mdd = max_drawdown(equity)
    if mdd <= 0.0:
        return None
    ann = annualized_return(values, periods_per_year=periods_per_year)
    if ann is None:
        return None
    return float((ann - rf) / mdd)


def information_ratio(returns: pd.Series | np.ndarray | Sequence[float],
                      benchmark: pd.Series | np.ndarray | Sequence[float],
                      periods_per_year: int = DEFAULT_PERIODS_PER_YEAR) -> float | None:
    """信息比：``mean(active)/std(active, ddof=1) * sqrt(ppy)``，``active = returns - benchmark``。

    Returns:
        年化信息比。超额收益无波动时返回 ``None``。

    Raises:
        ValueError: 两序列长度不一致、观测数 < 2 或 ``periods_per_year`` 非正。
    """
    if periods_per_year < 1:
        raise ValueError(f"periods_per_year must be >= 1, got {periods_per_year}")
    values = _clean_returns(returns)
    bench = _clean_returns(benchmark)
    if values.size != bench.size:
        raise ValueError(
            f"returns ({values.size}) and benchmark ({bench.size}) must have equal length"
        )
    if values.size < 2:
        raise ValueError(f"information_ratio needs at least 2 observations, got {values.size}")
    active = values - bench
    spread = float(active.std(ddof=1))
    scale = float(np.max(np.abs(active)))
    if _is_flat_spread(spread, scale):
        return None
    return float(active.mean() / spread * math.sqrt(periods_per_year))
