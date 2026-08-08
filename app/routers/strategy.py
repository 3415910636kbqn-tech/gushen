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


@router.get("/turtle-valuation/{ts_code}")
async def turtle_valuation(ts_code: str):
    """运行龟龟估值引擎（DCF/DDM/PE Band/PEG/PS，akshare 数据）"""
    from tradingagents.strategies.turtle.adapter import run_turtle_valuation
    return {"success": True, "data": run_turtle_valuation(ts_code)}
@router.get("/turtle-screener")
async def turtle_screener(tier1_only: bool = True, tier2_limit: int = 10):
    """运行龟龟选股器（Tier1 全市场筛选，Tier2 深度分析；akshare 数据）"""
    from tradingagents.strategies.turtle.screener_adapter import run_turtle_screener
    return {"success": True, "data": run_turtle_screener(tier1_only=tier1_only, tier2_limit=tier2_limit)}
