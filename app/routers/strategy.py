# -*- coding: utf-8 -*-
"""策略分析 API：NDX 动量对冲 / 龟龟估值 / 龟龟选股"""
import math
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


# ---------------------------------------------------------------------------
# quantlib 金融数学库：POST /api/strategy/quantlib
# ---------------------------------------------------------------------------
# 白名单函数表：fn -> {参数名 -> (校验器, 默认值)}。校验器把 JSON 参数规整为
# 函数需要的 Python 值，校验失败抛 ValueError（端点统一转 400）。
# 只允许这张表里的函数，杜绝任意调用（如 getattr/__import__ 逃逸）。


class _Require:
    """必需参数哨兵。"""

    def __repr__(self):  # pragma: no cover
        return "<required>"


_REQUIRED = _Require()


def _num(v, name):
    """数值（int/float，非 bool，有限）。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"参数 {name} 必须是数值")
    f = float(v)
    if not math.isfinite(f):
        raise ValueError(f"参数 {name} 必须是有限数值")
    return f


def _prob(v, name):
    """置信度：严格位于 (0, 1)。"""
    f = _num(v, name)
    if not 0.0 < f < 1.0:
        raise ValueError(f"参数 {name}（置信度）必须在 (0, 1) 之间，收到 {v}")
    return f


def _positive(v, name):
    f = _num(v, name)
    if f <= 0.0:
        raise ValueError(f"参数 {name} 必须为正数，收到 {v}")
    return f


def _int_ge1(v, name):
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"参数 {name} 必须是整数")
    if v < 1:
        raise ValueError(f"参数 {name} 必须 >= 1，收到 {v}")
    return v


def _opt_type(v, name):
    if not isinstance(v, str):
        raise ValueError(f"参数 {name}（期权类型）必须是字符串，收到 {v!r}")
    return v


def _series(v, name):
    """数值序列（list/tuple → float 列表）。"""
    if isinstance(v, (str, bytes, dict)) or not isinstance(v, (list, tuple)):
        raise ValueError(f"参数 {name} 必须是数值序列")
    try:
        out = [float(x) for x in v]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"参数 {name} 必须是数值序列") from exc
    if not all(math.isfinite(x) for x in out):
        raise ValueError(f"参数 {name} 必须只含有限数值")
    return out


def _cashflows(v, name):
    """现金流：[(date, amount), ...]，date 为日期字符串或 date。"""
    if not isinstance(v, (list, tuple)):
        raise ValueError(f"参数 {name} 必须是 [日期, 金额] 对的列表")
    out = []
    for item in v:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(
                f"参数 {name} 每一项必须是 [日期, 金额] 二元组，收到 {item!r}"
            )
        d, a = item
        if not isinstance(d, str):
            raise ValueError(f"参数 {name} 的日期必须是字符串（ISO YYYY-MM-DD），收到 {d!r}")
        try:
            amount = float(a)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"参数 {name} 的金额必须是数值，收到 {a!r}") from exc
        if not math.isfinite(amount):
            raise ValueError(f"参数 {name} 的金额必须是有限数值")
        out.append((d, amount))
    return out


_QL_FUNC_PARAMS: dict = {
    # ---- options ----
    "bs_price": {
        "S": (_positive, _REQUIRED), "K": (_positive, _REQUIRED),
        "T": (_positive, _REQUIRED), "r": (_num, _REQUIRED),
        "sigma": (_num, _REQUIRED), "option_type": (_opt_type, "call"), "q": (_num, 0.0),
    },
    "bs_greeks": {
        "S": (_positive, _REQUIRED), "K": (_positive, _REQUIRED),
        "T": (_positive, _REQUIRED), "r": (_num, _REQUIRED),
        "sigma": (_num, _REQUIRED), "option_type": (_opt_type, "call"), "q": (_num, 0.0),
    },
    "implied_volatility": {
        "market_price": (_num, _REQUIRED), "S": (_positive, _REQUIRED),
        "K": (_positive, _REQUIRED), "T": (_positive, _REQUIRED),
        "r": (_num, _REQUIRED), "option_type": (_opt_type, "call"), "q": (_num, 0.0),
    },
    # ---- risk ----
    "historical_var": {
        "returns": (_series, _REQUIRED), "confidence": (_prob, 0.95), "horizon": (_int_ge1, 1),
    },
    "parametric_var": {
        "returns": (_series, _REQUIRED), "confidence": (_prob, 0.95), "horizon": (_int_ge1, 1),
    },
    "historical_cvar": {
        "returns": (_series, _REQUIRED), "confidence": (_prob, 0.95), "horizon": (_int_ge1, 1),
    },
    "max_drawdown_analysis": {"equity": (_series, _REQUIRED)},
    # ---- performance ----
    "annualized_return": {
        "returns": (_series, _REQUIRED), "periods_per_year": (_int_ge1, 244),
    },
    "annualized_volatility": {
        "returns": (_series, _REQUIRED), "periods_per_year": (_int_ge1, 244),
    },
    "sharpe_ratio": {
        "returns": (_series, _REQUIRED), "rf": (_num, 0.0),
        "periods_per_year": (_int_ge1, 244),
    },
    "sortino_ratio": {
        "returns": (_series, _REQUIRED), "rf": (_num, 0.0),
        "periods_per_year": (_int_ge1, 244), "target": (_num, 0.0),
    },
    "max_drawdown": {"equity": (_series, _REQUIRED)},
    "calmar_ratio": {
        "returns": (_series, _REQUIRED), "equity": (_series, None),
        "periods_per_year": (_int_ge1, 244), "rf": (_num, 0.0),
    },
    "information_ratio": {
        "returns": (_series, _REQUIRED), "benchmark": (_series, _REQUIRED),
        "periods_per_year": (_int_ge1, 244),
    },
    # ---- fundmath ----
    "xirr": {
        "cashflows": (_cashflows, _REQUIRED), "days_per_year": (_num, 365.0),
        "guess": (_num, 0.1), "tol": (_num, 1e-9), "max_iter": (_int_ge1, 200),
    },
    "irr": {
        "cashflows": (_series, _REQUIRED), "guess": (_num, 0.1),
        "tol": (_num, 1e-9), "max_iter": (_int_ge1, 200),
    },
    "moic": {"invested": (_num, _REQUIRED), "returned": (_num, _REQUIRED)},
    "dpi": {"cashflows": (_series, _REQUIRED)},
    "tvpi": {"cashflows": (_series, _REQUIRED), "residual": (_num, 0.0)},
}


def _call_quantlib(fn: str, params: dict):
    """白名单校验 + 调用 quantlib 函数。非法 fn / 参数问题抛 ValueError。"""
    param_spec = _QL_FUNC_PARAMS.get(fn)
    if param_spec is None:
        raise ValueError(
            f"未知 quantlib 函数 {fn!r}；可用: {sorted(_QL_FUNC_PARAMS)}"
        )
    from tradingagents.strategies import quantlib as _ql
    func = getattr(_ql, fn, None)
    if func is None:
        raise ValueError(f"quantlib 函数 {fn!r} 不可调用")
    if not isinstance(params, dict):
        raise ValueError("params 必须是 JSON 对象")
    kwargs = {}
    for name, (validator, default) in param_spec.items():
        if name in params:
            kwargs[name] = validator(params[name], name)
        elif isinstance(default, _Require):
            raise ValueError(f"缺少必需参数 {name}")
        else:
            kwargs[name] = default
    return func(**kwargs)


def _json_safe(value):
    """把非有限 float 转为 None，保证 JSON 可序列化。"""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class QuantlibRequest(BaseModel):
    fn: str
    params: dict = {}


@router.post("/quantlib")
async def quantlib_call(req: QuantlibRequest, user: dict = Depends(get_current_user)):
    """quantlib 金融数学库白名单调用（期权/风险/绩效/现金流）。

    安全边界：fn 必须是白名单函数，params 逐参校验（数值类型、置信度范围等），
    非法 fn 或参数返回 400；不做任意代码调用。
    """
    try:
        result = _call_quantlib(req.fn, req.params or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "data": _json_safe(result)}
