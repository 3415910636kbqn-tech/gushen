"""Alpha 因子库：算子 + 精选 30 因子（Vibe base.py 移植 + registry）。"""
from .operators import (
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
    delta,
    decay_linear,
    signed_power,
    safe_div,
    ts_corr,
    ts_cov,
    vwap,
)
from .registry import (
    FACTOR_REGISTRY,
    Factor,
    compute_factor,
    compute_factor_panel,
    list_factors,
)

__all__ = [
    "rank", "zscore", "scale", "ts_rank", "ts_mean", "ts_std",
    "ts_max", "ts_min", "ts_argmax", "ts_argmin", "delta",
    "decay_linear", "signed_power", "safe_div", "ts_corr", "ts_cov", "vwap",
    "FACTOR_REGISTRY", "Factor", "compute_factor", "compute_factor_panel",
    "list_factors",
]
