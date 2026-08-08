"""quantlib：金融数学库（Vibe quantlib 精选移植，pandas/numpy 实现，无 scipy 依赖）。

四大模块：
* ``options``     -- Black-Scholes 定价 / Greeks / 隐含波动率（Newton+二分）
* ``risk``        -- 历史/参数 VaR、CVaR、最大回撤分析
* ``performance`` -- 年化收益/波动、Sharpe / Sortino / Calmar / 信息比、最大回撤
* ``fundmath``    -- XIRR / IRR / MOIC / DPI / TVPI（现金流序列）
"""
from . import fundmath, options, performance, risk
from .fundmath import dpi, irr, moic, tvpi, xirr
from .options import bs_greeks, bs_price, implied_volatility, normalise_option_type
from .performance import (
    annualized_return,
    annualized_volatility,
    calmar_ratio,
    information_ratio,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
)
from .risk import historical_cvar, historical_var, max_drawdown_analysis, parametric_var

__all__ = [
    # options
    "bs_price", "bs_greeks", "implied_volatility", "normalise_option_type",
    # risk
    "historical_var", "parametric_var", "historical_cvar", "max_drawdown_analysis",
    # performance
    "annualized_return", "annualized_volatility", "sharpe_ratio", "sortino_ratio",
    "max_drawdown", "calmar_ratio", "information_ratio",
    # fundmath
    "xirr", "irr", "moic", "dpi", "tvpi",
    # modules
    "options", "risk", "performance", "fundmath",
]
