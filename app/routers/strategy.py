# -*- coding: utf-8 -*-
"""策略分析 API：NDX 动量对冲 / 龟龟估值 / 龟龟选股"""
from fastapi import APIRouter, HTTPException
from tradingagents.strategies.ndx_momentum_hedge import run_ndx_momentum_hedge

router = APIRouter()


@router.get("/ndx-momentum")
def ndx_momentum():
    """运行 NDX 动量对冲策略（周度调仓报告）"""
    r = run_ndx_momentum_hedge()
    if isinstance(r, dict) and "error" in r:
        raise HTTPException(status_code=502, detail=r["error"])
    return {"success": True, "data": r}


@router.get("/health")
def strategy_health():
    return {"success": True, "data": {"strategies": ["ndx-momentum"]}}