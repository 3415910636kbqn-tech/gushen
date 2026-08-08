"""Black-Scholes 期权定价、Greeks 与隐含波动率（Vibe quantlib options.py 精选移植）。

纯 pandas/numpy/math 实现，无 scipy 依赖：
* 正态 CDF/PDF 用 ``math.erf`` 实现；
* 隐含波动率用 Newton 迭代，vega 塌缩或迭代不收敛时回退手写二分。

约定（与参考源码一致）：
* ``T`` 为年，``r``/``q`` 为连续复利年化利率。
* ``theta`` 为每自然日，``vega``/``rho`` 为每 1 个百分点，``delta``/``gamma`` 为每 1.0 标的。
* 退化输入（``T <= 0``、``sigma <= 0``、``S <= 0``、``K <= 0``）返回内在价值 / 点质量 Greeks，不抛异常。
"""
from __future__ import annotations

import math
from typing import Dict

__all__ = ["bs_price", "bs_greeks", "implied_volatility", "normalise_option_type"]

#: 隐含波动率搜索的最宽上界（年化 1000%）。
MAX_SIGMA = 10.0
#: 搜索最窄下界；同时是二分的下括点。
MIN_SIGMA = 1e-6
#: vega 低于此值时 Newton 步长数值上无意义，交还二分。
MIN_VEGA = 1e-10
#: Brenner-Subrahmanyam 种子只对近似平值有效，先夹紧再使用。
MAX_SEED_SIGMA = 5.0
MIN_SEED_SIGMA = 1e-3
#: 一个波动率点。若移动 sigma 一个点对价格的影响不超过求解容差，
#: 说明价格不携带波动率信息，求解结果不具意义。
SIGMA_RESOLUTION = 0.01

_CALL = "call"
_PUT = "put"

#: 归一到 ``"call"`` 的拼写（大小写/空白不敏感，含中英文别名）。
_CALL_ALIASES = frozenset({"call", "calls", "c", "看涨", "认购"})
_PUT_ALIASES = frozenset({"put", "puts", "p", "看跌", "认沽"})

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    """标准正态 CDF（``math.erf`` 实现）。"""
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _norm_pdf(x: float) -> float:
    """标准正态 PDF。"""
    return math.exp(-0.5 * x * x) / _SQRT2PI


def normalise_option_type(option_type: str) -> str:
    """把期权类型字符串归一到 ``"call"`` / ``"put"``。

    大小写、空白及别名（``c``/``calls``/``看涨``/``认购`` 等）均接受；
    未识别的拼写抛 ``ValueError``，绝不默认（默认正是把 call 腿按 put 结算的根源）。
    """
    folded = str(option_type).strip().lower()
    if folded in _CALL_ALIASES:
        return _CALL
    if folded in _PUT_ALIASES:
        return _PUT
    raise ValueError(
        f"unrecognised option_type {option_type!r}. Accepted (any case): "
        f"{sorted(_CALL_ALIASES)} for a call, {sorted(_PUT_ALIASES)} for a put."
    )


def _intrinsic(S: float, K: float, option_type: str) -> float:
    """未贴现的行权价值：call 为 max(S-K,0)，put 为 max(K-S,0)。"""
    return float(max(S - K, 0.0) if option_type == _CALL else max(K - S, 0.0))


def _is_degenerate(S: float, K: float, T: float, sigma: float) -> bool:
    """对数正态是否已塌缩成点质量（此时 d1/d2 无定义）。"""
    return T <= 0 or sigma <= 0 or S <= 0 or K <= 0


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float,
           q: float) -> tuple[float, float]:
    """Black-Scholes d1/d2。"""
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + sigma ** 2 / 2) * T) / (sigma * sqrt_T)
    return float(d1), float(d1 - sigma * sqrt_T)


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str = "call", q: float = 0.0) -> float:
    """Black-Scholes-Merton 欧式期权定价。

    Args:
        S: 标的现价。K: 行权价。T: 到期年限。r: 连续复利年化无风险利率。
        sigma: 年化波动率。option_type: ``"call"`` 或 ``"put"``，大小写不敏感。
        q: 连续分红率，年化，默认 0。

    Returns:
        理论价格。退化输入返回内在价值。

    Raises:
        ValueError: ``option_type`` 无法识别。
    """
    option_type = normalise_option_type(option_type)
    if _is_degenerate(S, K, T, sigma):
        return _intrinsic(S, K, option_type)

    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    spot_pv = S * math.exp(-q * T)
    strike_pv = K * math.exp(-r * T)
    if option_type == _CALL:
        return float(spot_pv * _norm_cdf(d1) - strike_pv * _norm_cdf(d2))
    return float(strike_pv * _norm_cdf(-d2) - spot_pv * _norm_cdf(-d1))


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str = "call", q: float = 0.0) -> Dict[str, float]:
    """五个 Black-Scholes Greeks。

    Returns:
        ``{delta, gamma, theta, vega, rho}``。theta 为每自然日，vega/rho 为每 1 个百分点。
        退化输入返回点质量 Greeks：delta 按实值性取 1/0（call）/ 0/-1（put），平值时取
        极限中点 0.5/-0.5，其余为 0。

    Raises:
        ValueError: ``option_type`` 无法识别。
    """
    option_type = normalise_option_type(option_type)
    if _is_degenerate(S, K, T, sigma):
        if S == K:
            delta = 0.5 if option_type == _CALL else -0.5
        elif option_type == _CALL:
            delta = 1.0 if S > K else 0.0
        else:
            delta = -1.0 if S < K else 0.0
        return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    sqrt_T = math.sqrt(T)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    pdf_d1 = _norm_pdf(d1)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)

    carry_theta = -(S * disc_q * pdf_d1 * sigma) / (2 * sqrt_T)
    if option_type == _CALL:
        delta = disc_q * _norm_cdf(d1)
        theta = (carry_theta - r * K * disc_r * _norm_cdf(d2)
                 + q * S * disc_q * _norm_cdf(d1))
        rho = K * T * disc_r * _norm_cdf(d2) / 100.0
    else:
        delta = disc_q * (_norm_cdf(d1) - 1.0)
        theta = (carry_theta + r * K * disc_r * _norm_cdf(-d2)
                 - q * S * disc_q * _norm_cdf(-d1))
        rho = -K * T * disc_r * _norm_cdf(-d2) / 100.0

    return {
        "delta": float(delta),
        "gamma": float(disc_q * pdf_d1 / (S * sigma * sqrt_T)),
        "theta": float(theta / 365.0),
        "vega": float(S * disc_q * pdf_d1 * sqrt_T / 100.0),
        "rho": float(rho),
    }


def _no_arbitrage_bounds(S: float, K: float, T: float, r: float,
                         option_type: str, q: float) -> tuple[float, float]:
    """Black-Scholes 可达价格区间 ``(lower, upper)``。

    sigma→0 收敛到贴现远期内在价值，sigma→∞ 时 call 收敛到 ``S*exp(-qT)``、
    put 收敛到 ``K*exp(-rT)``。区间外的报价不存在隐含波动率。
    """
    spot_pv = S * math.exp(-q * T)
    strike_pv = K * math.exp(-r * T)
    if option_type == _CALL:
        return max(spot_pv - strike_pv, 0.0), float(spot_pv)
    return max(strike_pv - spot_pv, 0.0), float(strike_pv)


def implied_volatility(market_price: float, S: float, K: float, T: float,
                       r: float, option_type: str = "call", q: float = 0.0,
                       tol: float = 1e-6, max_iter: int = 200) -> float:
    """反解隐含波动率：Newton 迭代优先，回退二分。

    以 Brenner-Subrahmanyam 平值近似 ``sigma_0 = sqrt(2*pi/T)*price/S`` 为种子，
    迭代 ``sigma -= (BS(sigma) - price) / vega``。vega 塌缩（深度实值/虚值或临近到期）
    时 Newton 步长失去意义，交还 ``[MIN_SIGMA, MAX_SIGMA]`` 上的二分。

    Returns:
        年化隐含波动率。两种方法都未收敛、或报价不携带波动率信息（价格对 sigma
        平坦，移动一个波动率点价格变化小于求解容差）时返回 ``nan``。

    Raises:
        ValueError: ``option_type`` 无法识别、``T``/``S``/``K`` 非正、
            或报价落在无套利区间外（含低于贴现内在价值）。
    """
    option_type = normalise_option_type(option_type)
    if T <= 0:
        raise ValueError(f"T must be > 0 to imply a volatility, got {T}")
    if S <= 0 or K <= 0:
        raise ValueError(f"S and K must be > 0, got S={S}, K={K}")

    lower, upper = _no_arbitrage_bounds(S, K, T, r, option_type, q)
    if market_price < lower - tol:
        raise ValueError(
            f"market price {market_price} is below intrinsic value {lower}"
        )
    if market_price >= upper:
        raise ValueError(
            f"market price {market_price} is at or above the no-arbitrage "
            f"ceiling {upper}; no implied volatility exists"
        )

    def identified(candidate: float) -> float:
        """仅当报价真正钉住该波动率时才返回它，否则 ``nan``。

        检验标准：移动 sigma 一个波动率点（SIGMA_RESOLUTION）使价格变化是否超过
        求解容差。若不超过，则一整段波动率都可在容差内复现报价，返回任意端点是
        搜索的假象而非市场读数。
        """
        vega = bs_greeks(S, K, T, r, candidate, option_type, q)["vega"] * 100.0
        return candidate if abs(vega) * SIGMA_RESOLUTION >= tol else float("nan")

    sigma = math.sqrt(2 * math.pi / T) * market_price / S
    sigma = min(max(sigma, MIN_SEED_SIGMA), MAX_SEED_SIGMA)

    for _ in range(max_iter):
        diff = bs_price(S, K, T, r, sigma, option_type, q) - market_price
        if abs(diff) < tol:
            return identified(sigma)
        vega = bs_greeks(S, K, T, r, sigma, option_type, q)["vega"] * 100.0
        if abs(vega) < MIN_VEGA:
            break
        sigma = min(max(sigma - diff / vega, MIN_SIGMA), MAX_SIGMA)

    # Newton 未收敛 → 二分回退。brentq 不在依赖里，手写二分。
    lo, hi = MIN_SIGMA, MAX_SIGMA
    f_lo = bs_price(S, K, T, r, lo, option_type, q) - market_price
    f_hi = bs_price(S, K, T, r, hi, option_type, q) - market_price
    if f_lo == 0.0:
        return identified(lo)
    if f_hi == 0.0:
        return identified(hi)
    if f_lo * f_hi > 0.0:
        return float("nan")
    for _ in range(max_iter * 2):
        mid = 0.5 * (lo + hi)
        f_mid = bs_price(S, K, T, r, mid, option_type, q) - market_price
        if abs(f_mid) < tol or (hi - lo) < 1e-12:
            return identified(mid)
        if f_mid * f_lo < 0.0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return float("nan")
