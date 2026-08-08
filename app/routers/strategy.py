# -*- coding: utf-8 -*-
"""策略分析 API：NDX 动量对冲 / 龟龟估值 / 龟龟选股"""
import re

from fastapi import APIRouter, Depends, HTTPException

from app.routers.auth_db import get_current_user
from tradingagents.strategies.ndx_momentum_hedge import run_ndx_momentum_hedge

router = APIRouter()


@router.get("/ndx-momentum")
def ndx_momentum(user: dict = Depends(get_current_user)):
    """运行 NDX 动量对冲策略（周度调仓报告）"""
    r = run_ndx_momentum_hedge()
    if isinstance(r, dict) and "error" in r:
        raise HTTPException(status_code=502, detail=r["error"])
    return {"success": True, "data": r}


@router.get("/health")
def strategy_health():
    return {"success": True, "data": {"strategies": ["ndx-momentum"]}}


@router.get("/turtle-valuation/{ts_code}")
async def turtle_valuation(ts_code: str, user: dict = Depends(get_current_user)):
    """运行龟龟估值引擎（DCF/DDM/PE Band/PEG/PS，akshare 数据）"""
    code = ts_code.strip().upper()
    if not re.fullmatch(r"\d{6}(\.(SH|SZ|BJ))?", code):
        raise HTTPException(status_code=400, detail="无效股票代码，需 6 位数字（可带 .SH/.SZ/.BJ 后缀）")
    from tradingagents.strategies.turtle.adapter import run_turtle_valuation
    return {"success": True, "data": run_turtle_valuation(code)}


@router.get("/chips/{symbol}")
async def chips(symbol: str, user: dict = Depends(get_current_user)):
    """筹码分布 CYQ（东财算法移植）：获利比例/平均成本/90-70 成本区间/筹码峰"""
    code = symbol.strip().upper()
    if not re.fullmatch(r"\d{6}(\.(SH|SZ|BJ))?", code):
        raise HTTPException(status_code=400, detail="无效股票代码，需 6 位数字（可带 .SH/.SZ/.BJ 后缀）")
    from tradingagents.strategies.chips import calc_chip_distribution, fetch_chip_klines
    klines = fetch_chip_klines(code)
    if klines is None or len(klines) == 0:
        raise HTTPException(status_code=404, detail="无可用行情数据")
    r = calc_chip_distribution(klines)
    date = str(klines.iloc[-1]["date"])
    return {"success": True, "data": {"symbol": code, "date": date, **r}}


@router.get("/turtle-screener")
async def turtle_screener(tier1_only: bool = True, tier2_limit: int = 10,
                          user: dict = Depends(get_current_user)):
    """运行龟龟选股器（Tier1 全市场筛选，Tier2 深度分析；akshare 数据）"""
    from tradingagents.strategies.turtle.screener_adapter import run_turtle_screener
    return {"success": True, "data": run_turtle_screener(tier1_only=tier1_only, tier2_limit=tier2_limit)}