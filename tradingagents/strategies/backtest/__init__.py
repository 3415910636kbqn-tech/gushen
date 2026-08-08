# -*- coding: utf-8 -*-
"""A股回测引擎（独立轻量实现）。

规则：T+1、涨跌停 ±10%（简版）、佣金 万2.5（最低 5 元）/ 卖出印花税 千0.5、
最小 100 股整手。内置策略：buy_hold / ma_cross / rsi_reverse / momentum，
支持 params["strategy_fn"] 自定义信号函数。
"""
from .engine import (
    BacktestEngine,
    BUILTIN_STRATEGIES,
    DEFAULT_CAPITAL,
    load_daily,
    run_backtest,
)

__all__ = [
    "BacktestEngine",
    "BUILTIN_STRATEGIES",
    "DEFAULT_CAPITAL",
    "load_daily",
    "run_backtest",
]