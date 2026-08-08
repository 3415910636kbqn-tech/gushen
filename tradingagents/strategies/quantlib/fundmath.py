"""现金流数学：XIRR（日现金流 IRR）/ IRR / MOIC / DPI / TVPI（Vibe quantlib fundmath.py 精选移植，简版）。

符号约定（与参考源码一致，投资者视角）：**付出为负、收到为正**。
* ``xirr`` 接受 ``(date_str, amount)`` 列表，日期按自然日 / 365 计年，
  求解 ``sum(amount_i / (1+r)**t_i) == 0``，主解用 Newton 迭代，不收敛时二分兜底。
* ``irr`` 为无日期定期现金流，``t_i = i``。
* ``dpi``/``tvpi`` 简版：负额为投入、正额为分配（残值可选）。

对空/异常输入抛 ``ValueError``（明确错误）；``moic`` 对非正投入返回 ``None``。
"""
from __future__ import annotations

import datetime as _dt
import math
from collections.abc import Sequence

import numpy as np

__all__ = ["xirr", "irr", "moic", "dpi", "tvpi"]

DAYS_PER_YEAR = 365.0
"""日计数基准；与 Excel XIRR 一致。"""

_IRR_LOW = -0.999999
_IRR_HIGH = 10000.0


def _to_date(raw) -> _dt.date:
    """把 str（ISO 格式）或 date/datetime 规整为 date。"""
    if isinstance(raw, str):
        try:
            return _dt.date.fromisoformat(raw.strip())
        except ValueError as exc:
            raise ValueError(f"unparsable date {raw!r}; expected ISO YYYY-MM-DD") from exc
    if isinstance(raw, _dt.datetime):
        return raw.date()
    if isinstance(raw, _dt.date):
        return raw
    raise ValueError(f"unparsable date {raw!r}")


def _coerce_amounts(cashflows: Sequence[float]) -> np.ndarray:
    """规整金额序列为有限 1-D float 数组。"""
    try:
        amounts = np.asarray([float(a) for a in cashflows], dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"cashflows must be a sequence of numbers, got {cashflows!r}") from exc
    if amounts.ndim != 1 or amounts.size == 0:
        raise ValueError("cashflows must be a non-empty 1-D sequence of amounts")
    if not np.all(np.isfinite(amounts)):
        raise ValueError("cashflows must contain only finite amounts")
    return amounts


def _npv(rate: float, times: np.ndarray, amounts: np.ndarray) -> float:
    """贴现因子用对数形式 ``exp(-t*log1p(rate))`` 计算，避免大利率长跨度溢出。"""
    if rate <= -1.0:
        return math.nan
    with np.errstate(over="ignore", invalid="ignore"):
        return float(np.sum(amounts * np.exp(-times * np.log1p(rate))))


def _npv_derivative(rate: float, times: np.ndarray, amounts: np.ndarray) -> float:
    if rate <= -1.0:
        return math.nan
    with np.errstate(over="ignore", invalid="ignore"):
        return float(np.sum(-times * amounts * np.exp(-(times + 1.0) * np.log1p(rate))))


def _check_sign_change(amounts: np.ndarray) -> None:
    """符号检查：全正或全负的现金流序列没有有限 IRR。"""
    gross = float(np.sum(np.abs(amounts)))
    if gross == 0.0:
        raise ValueError("every amount is zero, so no rate of return is defined")
    if not (amounts > 0).any() or not (amounts < 0).any():
        direction = "positive" if (amounts > 0).any() else "negative"
        raise ValueError(
            f"all {amounts.size} amounts are {direction}, so the net present value "
            "never crosses zero and no IRR exists. Check the sign convention: "
            "contributions must be negative and distributions positive."
        )


def _bisect_rate(times: np.ndarray, amounts: np.ndarray, tol: float) -> float:
    """二分兜底：在 (-100%, 1000000%) 上找 NPV 变号点。找不到返回 nan。"""
    lo, hi = _IRR_LOW, _IRR_HIGH
    f_lo = _npv(lo, times, amounts)
    f_hi = _npv(hi, times, amounts)
    if not math.isfinite(f_lo) or not math.isfinite(f_hi) or f_lo * f_hi > 0.0:
        return math.nan
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        f_mid = _npv(mid, times, amounts)
        if abs(f_mid) <= tol or (hi - lo) < 1e-12:
            return mid
        if f_mid * f_lo < 0.0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return math.nan


def _solve_newton(times: np.ndarray, amounts: np.ndarray,
                  guess: float, tol: float, max_iter: int) -> float:
    """Newton 迭代解 IRR，失败（发散/无符号变化/不收敛）返回 nan。"""
    _check_sign_change(amounts)
    rate = guess
    for _ in range(max_iter):
        f = _npv(rate, times, amounts)
        if not math.isfinite(f):
            return math.nan
        if abs(f) <= tol:
            return rate
        df = _npv_derivative(rate, times, amounts)
        if not math.isfinite(df) or df == 0.0:
            return math.nan
        new_rate = rate - f / df
        if not math.isfinite(new_rate) or new_rate <= -1.0:
            return math.nan
        if abs(new_rate - rate) <= 1e-13:
            return new_rate
        rate = new_rate
    return math.nan


def xirr(cashflows: Sequence[tuple],
         days_per_year: float = DAYS_PER_YEAR,
         guess: float = 0.1,
         tol: float = 1e-9,
         max_iter: int = 200) -> float:
    """不定期日期现金流的内在收益率（Money-weighted return）。

    Args:
        cashflows: ``(date, amount)`` 列表，顺序无关；同日金额自动汇总。
            date 为 ISO 字符串（``"2024-01-01"``）或 ``date``/``datetime``。
            付出为负、收到为正。days_per_year: 日计数基准，默认 365（同 Excel XIRR）。
        guess: Newton 起始利率。tol: 收敛容差（绝对 NPV 大小，按金额总规模缩放）。
        max_iter: 最大迭代次数。

    Returns:
        年化利率（十进制，0.10 表示 10%）。

    Raises:
        ValueError: 现金流少于两项、日期/金额不可用、所有金额落在同一天、
            无符号变化，或 Newton 与二分均未收敛到根。
    """
    if len(cashflows) < 2:
        raise ValueError(f"an XIRR needs at least two dated amounts, got {len(cashflows)}")
    totals: dict[_dt.date, float] = {}
    for raw_date, raw_amount in cashflows:
        when = _to_date(raw_date)
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"amount on {when} must be numeric, got {raw_amount!r}") from exc
        if not math.isfinite(amount):
            raise ValueError(f"amount on {when} must be finite, got {raw_amount!r}")
        totals[when] = totals.get(when, 0.0) + amount

    ordered = sorted(totals.items())
    if len(ordered) < 2:
        raise ValueError(
            f"every amount falls on {ordered[0][0]}; a rate of return is not "
            "identifiable without a time span"
        )
    origin = ordered[0][0]
    times = np.array([(when - origin).days / days_per_year for when, _ in ordered], dtype=float)
    amounts = np.array([amount for _, amount in ordered], dtype=float)

    _check_sign_change(amounts)
    gross = float(np.sum(np.abs(amounts)))
    tolerance = max(tol * max(gross, 1.0), 1e-12)

    rate = _solve_newton(times, amounts, guess, tolerance, max_iter)
    if math.isnan(rate) or abs(_npv(rate, times, amounts)) > tolerance:
        rate = _bisect_rate(times, amounts, tolerance)
    if math.isnan(rate) or abs(_npv(rate, times, amounts)) > tolerance:
        raise ValueError(
            "no IRR found: Newton did not converge and no bracketed root exists "
            "inside the search window; check the sign pattern of the cashflows"
        )
    return float(rate)


def irr(cashflows: Sequence[float],
        guess: float = 0.1,
        tol: float = 1e-9,
        max_iter: int = 200) -> float:
    """定期现金流的内在收益率：``sum(amount_i / (1+r)**i) == 0``。

    Args:
        cashflows: 等间隔金额序列（付出为负、收到为正）。

    Returns:
        每期利率（十进制）。

    Raises:
        ValueError: 金额不足两项、含非有限值、无符号变化或不收敛。
    """
    amounts = _coerce_amounts(cashflows)
    if amounts.size < 2:
        raise ValueError(f"an IRR needs at least two cashflows, got {amounts.size}")
    times = np.arange(amounts.size, dtype=float)

    _check_sign_change(amounts)
    gross = float(np.sum(np.abs(amounts)))
    tolerance = max(tol * max(gross, 1.0), 1e-12)

    rate = _solve_newton(times, amounts, guess, tolerance, max_iter)
    if math.isnan(rate) or abs(_npv(rate, times, amounts)) > tolerance:
        rate = _bisect_rate(times, amounts, tolerance)
    if math.isnan(rate) or abs(_npv(rate, times, amounts)) > tolerance:
        raise ValueError("no IRR found: the cashflows never cross zero or the solver did not converge")
    return float(rate)


def moic(invested: float, returned: float) -> float | None:
    """投入资本倍数（MOIC）：``returned / invested``。

    Returns:
        倍数。``invested`` 非正时返回 ``None``（除零保护）。
    """
    try:
        invested = float(invested)
        returned = float(returned)
    except (TypeError, ValueError):
        return None
    if invested <= 0.0:
        return None
    return float(returned / invested)


def dpi(cashflows: Sequence[float]) -> float:
    """分配对投入（DPI）：``已分配 / 已投入``。

    Args:
        cashflows: 金额序列；负额为投入、正额为分配。

    Returns:
        DPI 倍数。``1.0`` 表示已回收全部投入本金。

    Raises:
        ValueError: 无任何投入（无负额）或金额序列非法。
    """
    amounts = _coerce_amounts(cashflows)
    paid_in = -float(np.sum(amounts[amounts < 0]))
    if paid_in <= 0.0:
        raise ValueError("no capital drawn (no negative amount); DPI is undefined")
    distributed = float(np.sum(amounts[amounts > 0]))
    return float(distributed / paid_in)


def tvpi(cashflows: Sequence[float], residual: float = 0.0) -> float:
    """总价值对投入（TVPI）：``(已分配 + 残值) / 已投入``。

    Args:
        cashflows: 金额序列；负额为投入、正额为分配。residual: 期末残值/NAV。

    Raises:
        ValueError: 无任何投入或金额序列非法。
    """
    amounts = _coerce_amounts(cashflows)
    paid_in = -float(np.sum(amounts[amounts < 0]))
    if paid_in <= 0.0:
        raise ValueError("no capital drawn (no negative amount); TVPI is undefined")
    distributed = float(np.sum(amounts[amounts > 0]))
    return float((distributed + float(residual)) / paid_in)
