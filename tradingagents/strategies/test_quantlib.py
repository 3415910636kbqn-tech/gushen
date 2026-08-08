"""quantlib 金融数学库测试（Vibe quantlib 精选移植）。

覆盖：BS 定价 / Greeks / 隐含波动率、VaR/CVaR/最大回撤、
绩效指标（年化收益/波动、Sharpe/Sortino/Calmar/信息比）、
现金流（XIRR/IRR/MOIC/DPI/TVPI）。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tradingagents.strategies.quantlib.options import (
    bs_price,
    bs_greeks,
    implied_volatility,
    normalise_option_type,
)
from tradingagents.strategies.quantlib.risk import (
    historical_var,
    parametric_var,
    historical_cvar,
    max_drawdown_analysis,
)
from tradingagents.strategies.quantlib.performance import (
    annualized_return,
    annualized_volatility,
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    calmar_ratio,
    information_ratio,
)
from tradingagents.strategies.quantlib.fundmath import xirr, irr, moic, dpi, tvpi


# ---------------------------------------------------------------------------
# options: Black-Scholes
# ---------------------------------------------------------------------------

def test_bs_price_call_matches_reference():
    p = bs_price(100, 100, 1.0, 0.05, 0.2, "call")
    assert abs(p - 10.450583572185565) < 1e-6


def test_bs_price_put_matches_reference():
    p = bs_price(100, 100, 1.0, 0.05, 0.2, "put")
    assert abs(p - 5.573526022256971) < 1e-6


def test_bs_price_aliases_and_case():
    assert bs_price(100, 100, 1, 0.05, 0.2, "C") == pytest.approx(
        bs_price(100, 100, 1, 0.05, 0.2, "call"), abs=1e-12)
    assert bs_price(100, 100, 1, 0.05, 0.2, "看跌") == pytest.approx(
        bs_price(100, 100, 1, 0.05, 0.2, "put"), abs=1e-12)


def test_bs_price_put_call_parity():
    c = bs_price(100, 100, 1.0, 0.05, 0.2, "call")
    p = bs_price(100, 100, 1.0, 0.05, 0.2, "put")
    assert abs((c - p) - (100 - 100 * np.exp(-0.05))) < 1e-9


def test_bs_greeks_no_nan_and_signs():
    g = bs_greeks(100, 100, 1.0, 0.05, 0.2, "call")
    assert all(np.isfinite(v) for v in g.values())
    assert 0 < g["delta"] < 1
    assert g["gamma"] > 0
    assert g["vega"] > 0
    assert g["rho"] > 0
    assert g["theta"] < 0  # 时间衰减为负
    pg = bs_greeks(100, 100, 1.0, 0.05, 0.2, "put")
    assert -1 < pg["delta"] < 0


def test_bs_greeks_delta_range():
    for S in (80.0, 100.0, 120.0):
        assert 0 < bs_greeks(S, 100, 1.0, 0.05, 0.2, "call")["delta"] < 1
        assert -1 < bs_greeks(S, 100, 1.0, 0.05, 0.2, "put")["delta"] < 0


def test_bs_price_degenerate_inputs_return_intrinsic():
    assert bs_price(100, 100, 0.0, 0.05, 0.2, "call") == 0.0
    assert bs_price(50, 100, 0.0, 0.05, 0.2, "call") == 0.0
    assert bs_price(120, 100, 0.0, 0.05, 0.2, "call") == 20.0
    assert bs_price(100, 100, 1.0, 0.05, 0.0, "put") == 0.0
    # 退化情形 Greeks：delta 报点质量值，其余为 0
    g = bs_greeks(120, 100, 0.0, 0.05, 0.2, "call")
    assert g["delta"] == 1.0 and g["gamma"] == 0.0 and g["vega"] == 0.0


def test_implied_volatility_recovers_input():
    sig = 0.30
    price = bs_price(100, 100, 1.0, 0.05, sig, "call")
    iv = implied_volatility(price, 100, 100, 1.0, 0.05, "call")
    assert abs(iv - sig) < 1e-6


def test_implied_volatility_put():
    sig = 0.25
    price = bs_price(90, 100, 0.5, 0.03, sig, "put")
    iv = implied_volatility(price, 90, 100, 0.5, 0.03, "put")
    assert abs(iv - sig) < 1e-6


def test_implied_volatility_invalid_quote_raises():
    # 报价高于无套利上界：不存在隐含波动率
    with pytest.raises(ValueError):
        implied_volatility(999.0, 100, 100, 1.0, 0.05, "call")


def test_normalise_option_type_rejects_unknown():
    with pytest.raises(ValueError):
        normalise_option_type("kall")


# ---------------------------------------------------------------------------
# risk: VaR / CVaR / max drawdown
# ---------------------------------------------------------------------------

def test_historical_var_hand_computed():
    r = [-0.10, -0.05, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.10]
    # n=10, conf=0.8 → 阶统计量 index = ceil(0.2*10)-1 = 1 → 排序后第2个 = -0.05
    assert historical_var(r, confidence=0.8) == pytest.approx(0.05, abs=1e-12)


def test_historical_cvar_hand_computed():
    r = [-0.10, -0.05, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.10]
    # 尾部 [-0.10, -0.05] 均值 -0.075 → cvar = 0.075
    assert historical_cvar(r, confidence=0.8) == pytest.approx(0.075, abs=1e-12)


def test_var_horizon_scales_by_sqrt_time():
    r = [-0.10, -0.05, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.10]
    assert historical_var(r, confidence=0.8, horizon=4) == pytest.approx(
        historical_var(r, confidence=0.8, horizon=1) * 2.0, abs=1e-12)


def test_parametric_var_matches_formula():
    r = np.array([0.01, -0.02, 0.03, -0.01, 0.0, 0.02, -0.03, 0.01])
    z = -1.6448536269514722  # norm.ppf(0.05)
    expected = -(r.mean() + z * r.std(ddof=1))
    assert parametric_var(r, confidence=0.95) == pytest.approx(expected, abs=1e-12)


def test_cvar_ge_var():
    rng = np.random.default_rng(42)
    r = rng.normal(0, 0.02, 500)
    assert historical_cvar(r) >= historical_var(r) - 1e-15


def test_returns_cleaning_drops_nan_inf():
    r = [0.01, np.nan, -0.02, np.inf, 0.03]
    # 清洗后 [-0.02, 0.01, 0.03]，conf=0.8, n=3 → index=ceil(0.6)-1=0 → -0.02 → var=0.02
    assert historical_var(r, confidence=0.8) == pytest.approx(0.02, abs=1e-12)


def test_max_drawdown_analysis_known_sequence():
    d = max_drawdown_analysis([100, 120, 90, 110])
    assert d["max_drawdown"] == pytest.approx(0.25, abs=1e-12)
    assert d["peak"] == 1
    assert d["trough"] == 2
    assert d["duration"] == 1


def test_max_drawdown_analysis_flat_curve():
    d = max_drawdown_analysis([100, 100, 100])
    assert d["max_drawdown"] == 0.0


# ---------------------------------------------------------------------------
# performance: 年化收益/波动、Sharpe/Sortino/Calmar/信息比
# ---------------------------------------------------------------------------

def test_annualized_return_geometric():
    r = np.array([0.10, 0.20, -0.10])
    expected = np.prod(1 + r) ** (244 / len(r)) - 1
    assert annualized_return(r) == pytest.approx(expected, abs=1e-12)


def test_annualized_volatility():
    r = np.array([0.01, -0.02, 0.03, -0.01])
    expected = r.std(ddof=1) * np.sqrt(244)
    assert annualized_volatility(r) == pytest.approx(expected, abs=1e-12)


def test_sharpe_ratio_formula():
    r = np.array([0.01, 0.02, -0.01, 0.03])
    excess = r - 0.0
    expected = excess.mean() / excess.std(ddof=1) * np.sqrt(244)
    assert sharpe_ratio(r, rf=0.0) == pytest.approx(expected, abs=1e-12)


def test_sharpe_ratio_with_rf():
    r = np.array([0.01, 0.02, -0.01, 0.03])
    rf = 0.02
    excess = r - rf / 244
    expected = excess.mean() / excess.std(ddof=1) * np.sqrt(244)
    assert sharpe_ratio(r, rf=rf) == pytest.approx(expected, abs=1e-12)


def test_sharpe_ratio_constant_returns_is_none():
    assert sharpe_ratio(np.ones(10) * 0.01) is None


def test_sortino_ratio_formula():
    r = np.array([0.01, -0.02, 0.03, -0.01])
    excess = r - 0.0
    downside = np.minimum(excess, 0.0)
    dev = np.sqrt(np.mean(downside ** 2))
    expected = excess.mean() / dev * np.sqrt(244)
    assert sortino_ratio(r) == pytest.approx(expected, abs=1e-12)


def test_max_drawdown_scalar():
    assert max_drawdown([100, 120, 90, 110]) == pytest.approx(0.25, abs=1e-12)
    assert max_drawdown([100, 110, 130]) == 0.0


def test_calmar_ratio():
    eq = np.array([100.0, 120.0, 90.0, 110.0])
    r = np.diff(eq) / eq[:-1]
    expected = annualized_return(r) / 0.25
    assert calmar_ratio(r, equity=eq) == pytest.approx(expected, abs=1e-12)


def test_information_ratio_formula():
    r = np.array([0.01, 0.02, -0.01, 0.03])
    b = np.array([0.005, 0.01, 0.00, 0.01])
    active = r - b
    expected = active.mean() / active.std(ddof=1) * np.sqrt(244)
    assert information_ratio(r, b) == pytest.approx(expected, abs=1e-12)


# ---------------------------------------------------------------------------
# fundmath: XIRR / IRR / MOIC / DPI / TVPI
# ---------------------------------------------------------------------------

def test_xirr_one_year_known():
    cf = [("2024-01-01", -1000.0), ("2024-12-31", 1100.0)]
    assert xirr(cf) == pytest.approx(0.10, abs=1e-6)


def test_xirr_fractional_year():
    # 半年翻倍：-1000 @ 2024-01-01, +2000 @ 2024-07-01（182 天）
    cf = [("2024-01-01", -1000.0), ("2024-07-01", 2000.0)]
    expected = 2.0 ** (365 / 182) - 1
    assert xirr(cf) == pytest.approx(expected, abs=1e-6)


def test_irr_periodic():
    assert irr([-1000.0, 1100.0]) == pytest.approx(0.10, abs=1e-9)
    assert irr([-1000.0, 0.0, 1210.0]) == pytest.approx(0.10, abs=1e-9)


def test_moic():
    assert moic(1000, 1500) == pytest.approx(1.5, abs=1e-12)
    assert moic(1000, 1000) == pytest.approx(1.0, abs=1e-12)


def test_dpi_tvpi():
    cf = [-1000.0, 400.0, 500.0]
    assert dpi(cf) == pytest.approx(0.9, abs=1e-12)
    assert tvpi(cf, residual=200.0) == pytest.approx(1.1, abs=1e-12)


# ---------------------------------------------------------------------------
# 空 / 异常输入：不崩溃（返回 None 或抛出明确 ValueError）
# ---------------------------------------------------------------------------

def test_empty_or_invalid_inputs_do_not_crash():
    with pytest.raises(ValueError):
        historical_var([])
    with pytest.raises(ValueError):
        historical_var([np.nan])
    with pytest.raises(ValueError):
        parametric_var([0.01])  # 样本数不足
    with pytest.raises(ValueError):
        max_drawdown_analysis([])
    with pytest.raises(ValueError):
        max_drawdown_analysis([100, 0, 50])  # 非正净值
    with pytest.raises(ValueError):
        sharpe_ratio([])
    with pytest.raises(ValueError):
        annualized_volatility([0.01])
    with pytest.raises(ValueError):
        xirr([])
    with pytest.raises(ValueError):
        xirr([("2024-01-01", 100.0), ("2024-01-01", -50.0)])  # 无时间跨度
    with pytest.raises(ValueError):
        irr([100.0, 200.0])  # 无符号变化
    with pytest.raises(ValueError):
        dpi([100.0, 200.0])  # 无投入
    assert moic(0, 100) is None  # 除零保护
    with pytest.raises(ValueError):
        historical_var([0.01, -0.02], confidence=1.5)  # 置信度越界
