# -*- coding: utf-8 -*-
"""策略分析 API：NDX 动量对冲 / 龟龟估值 / 龟龟选股"""
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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

class FactorScreenRequest(BaseModel):
    factor: str
    condition: str = "top"
    top_n: int = 20
    trade_date: Optional[str] = None
    symbols: Optional[List[str]] = None


@router.get("/factors")
async def list_factor_zoo(user: dict = Depends(get_current_user)):
    """Alpha 因子库列表（name/display_name/category/description）"""
    from tradingagents.strategies.factors.registry import list_factors
    factors = list_factors()
    return {"success": True, "data": {"count": len(factors), "factors": factors}}


@router.post("/factor-screen")
async def factor_screen(req: FactorScreenRequest,
                        user: dict = Depends(get_current_user)):
    """受限因子选股：按因子值对给定 symbols（≤50 只）排序。

    因子计算需要历史截面数据，全市场实时算不可行（数千只×单只日线）；
    本端点接受 body 传 symbols 列表，经桥接层 daily() 拉取历史构建面板后
    计算因子值并返回 top/bottom 排序（性能受单只日线请求数限制）。
    """
    from tradingagents.strategies import get_pro_api
    from tradingagents.strategies.factors.screener import screen_by_factor
    try:
        pro = get_pro_api()
        r = screen_by_factor(pro, factor=req.factor, condition=req.condition,
                             top_n=req.top_n, symbols=req.symbols,
                             trade_date=req.trade_date)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"未知因子: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if r.get("last_date") is None:
        detail = "因子选股需要历史截面数据，实时拉取失败；建议离线预计算全市场因子快照"
        skipped = r.get("skipped") or []
        if skipped:
            reasons = "; ".join(f"{s['symbol']}: {s['error']}" for s in skipped[:5])
            detail += f"（跳过 {len(skipped)} 只: {reasons}）"
        raise HTTPException(status_code=503, detail=detail)
    return {"success": True, "data": r}


class BacktestRequest(BaseModel):
    """A股回测请求体"""
    symbol: str
    strategy: str
    start: str
    end: str
    params: dict = {}
    initial_capital: float = 100000.0


@router.post("/backtest")
async def backtest(req: BacktestRequest, user: dict = Depends(get_current_user)):
    """A股回测：buy_hold/ma_cross/rsi_reverse/momentum（T+1/涨跌停/手续费）。

    安全边界：只接受白名单 4 个内置策略，拒绝 strategy_fn 自定义回调
    （防止任意代码执行）；symbol 为 6 位 A 股代码；start/end 为 YYYYMMDD
    且 start < end。
    """
    code = req.symbol.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(status_code=400, detail="无效股票代码，需 6 位数字（A股，无后缀）")
    if not re.fullmatch(r"\d{8}", req.start) or not re.fullmatch(r"\d{8}", req.end):
        raise HTTPException(status_code=400, detail="日期需为 YYYYMMDD 格式")
    if req.start >= req.end:
        raise HTTPException(status_code=400, detail="start 必须小于 end")
    if req.strategy not in ("buy_hold", "ma_cross", "rsi_reverse", "momentum"):
        raise HTTPException(status_code=400,
                            detail="strategy 仅支持 buy_hold/ma_cross/rsi_reverse/momentum")
    if req.initial_capital <= 0:
        raise HTTPException(status_code=400, detail="initial_capital 需为正数")

    from tradingagents.strategies.backtest import run_backtest
    r = run_backtest(code, req.strategy, req.start, req.end,
                     params=req.params or {}, initial_capital=req.initial_capital)
    if "error" in r:
        raise HTTPException(status_code=502, detail=r["error"])
    return {"success": True, "data": r}