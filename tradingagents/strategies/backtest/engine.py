# -*- coding: utf-8 -*-
"""A股回测引擎（独立轻量实现，不依赖 Vibe 框架）。

市场规则（均为合理简化的常用口径，见各策略 docstring）：
- T+1：当日买入的股票当日不可卖出（卖出时用持仓买入日期判断，同日拒绝）。
- 涨跌停：主板 ±10%（ST 简化为不区分）。简版判断用「当日收盘相对前收盘」：
  当日 close 较前收涨幅 ≥ +10% 视为涨停，当日买入信号被拒（保守假设涨停
  时买不到）；跌幅 ≤ -10% 视为跌停，当日卖出信号被拒（跌停时卖不出）。
  首日无前收，不做涨跌停限制。
- 手续费：佣金 万2.5（双边，单笔最低 5 元）；卖出印花税 千0.5；过户费忽略。
- 最小 100 股（整手），买入数量向下取整到整手。
- 无未来函数：信号在当日收盘产生，次一交易日开盘价成交（无滑点）；
  buy_hold 例外，首日开盘直接建仓。涨跌停以成交价相对前收判断。

内置策略（strategy: str + params: dict）：
- buy_hold      : 首日全仓买入，持有至末日收盘强制平仓。
- ma_cross      : 快线上穿慢线买入、下穿卖出（params: fast/slow，默认 5/20）。
- rsi_reverse   : RSI < oversold 买入、> overbought 卖出（params: period/
                   oversold/overbought，默认 14/30/70；复用 indicators.calc_rsi）。
- momentum      : 近 lookback 日动量为正持仓、为负空仓（params: lookback，默认 20）。
- 自定义        : params["strategy_fn"] 可传 callable(df, i, state) -> "buy"|"sell"|"hold"。

run_backtest 返回 dict：
  {symbol, period, initial_capital, final_value, total_return, annual_return,
   max_drawdown, sharpe, win_rate, num_trades, trades: [{date, side, price,
   shares, amount, fee}], equity_curve: [{date, value}],
   benchmark: {final_value, total_return}}（同区间 buy_hold）。

无数据/非法参数时返回含 "error" 键的 dict（不抛异常）。
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable, Dict, Optional

import numpy as np
import pandas as pd

from tradingagents.strategies.indicators import calc_rsi

# ── 市场规则常量 ──
COMMISSION_RATE = 0.00025    # 佣金 万2.5（双边）
COMMISSION_MIN = 5.0         # 佣金单笔最低 5 元
STAMP_TAX = 0.0005           # 卖出印花税 千0.5
PRICE_LIMIT = 0.10           # 主板 ±10%
LOT_SIZE = 100               # 整手
TRADING_DAYS_PER_YEAR = 244  # A股年化交易日数
DEFAULT_CAPITAL = 100_000.0  # 初始资金默认 10 万

BUILTIN_STRATEGIES = ("buy_hold", "ma_cross", "rsi_reverse", "momentum")

_SYMBOL_RE = re.compile(r"^\d{6}$")
_DATE_RE = re.compile(r"^\d{8}$")
_LIMIT_EPS = 1e-6


def _norm_date(v) -> str:
    """'2024-01-05' / Timestamp / '20240105' -> '20240105'"""
    s = str(v)
    if len(s) >= 10 and s[4] == "-":
        return s[0:4] + s[5:7] + s[8:10]
    return s[:8]


# ── 数据加载 ──

def load_daily(symbol: str, start: str, end: str,
               data_source: Optional[Callable] = None) -> pd.DataFrame:
    """加载前复权日线数据。

    默认复用桥接层 ProClient.daily()（东财前复权，trade_date=YYYYMMDD），
    补齐 open/high/low/close/volume 列（volume 由桥接层 vol(手) 换算为股）。
    ``data_source`` 可注入 callable(symbol, start, end) -> DataFrame（测试用
    fake，列名同桥接层：trade_date/open/high/low/close/vol/volume）。
    """
    if data_source is not None:
        df = data_source(symbol, start, end)
    else:
        from tradingagents.strategies import get_pro_api
        df = get_pro_api().daily(ts_code=symbol, start_date=start, end_date=end)
    if df is None:
        return pd.DataFrame()
    df = df.copy()
    if df.empty:
        return df
    # 列归一化：兼容 date / trade_date 两种列名
    if "trade_date" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "trade_date"})
    if "trade_date" not in df.columns:
        return pd.DataFrame()
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" not in df.columns:
        if "vol" in df.columns:
            df["volume"] = pd.to_numeric(df["vol"], errors="coerce") * 100.0
        else:
            df["volume"] = np.nan
    df["trade_date"] = df["trade_date"].map(_norm_date)
    df = df.dropna(subset=["close"]).sort_values("trade_date").reset_index(drop=True)
    return df[["trade_date", "open", "high", "low", "close", "volume"]]


# ── 账户撮合引擎 ──

class BacktestEngine:
    """单标的账户撮合引擎（A 股规则：T+1、整手、手续费）。

    只负责撮合与记账；涨跌停等需要前收盘价的判断由 run_backtest 主循环负责。
    """

    def __init__(self, initial_capital: float = DEFAULT_CAPITAL,
                 commission_rate: float = COMMISSION_RATE,
                 commission_min: float = COMMISSION_MIN,
                 stamp_tax: float = STAMP_TAX,
                 lot_size: int = LOT_SIZE):
        self.initial_capital = float(initial_capital)
        self.commission_rate = float(commission_rate)
        self.commission_min = float(commission_min)
        self.stamp_tax = float(stamp_tax)
        self.lot_size = int(lot_size)
        self.cash = self.initial_capital
        self.shares = 0
        self.buy_date: Optional[str] = None   # 当前持仓的买入日期（T+1 判断）
        self.buy_cost = 0.0                   # 当前持仓买入总成本（含佣金）
        self.trades: list = []
        self.closed_pnls: list = []           # 每笔平仓的已实现盈亏
        self.equity: list = []                # [{date, value}]

    # ── 费用 ──

    def _buy_fee(self, amount: float) -> float:
        return max(amount * self.commission_rate, self.commission_min)

    def _sell_fee(self, amount: float) -> float:
        return max(amount * self.commission_rate, self.commission_min) \
            + amount * self.stamp_tax

    # ── 撮合 ──

    def _try_buy(self, date: str, price: float) -> bool:
        """全仓买入（按整手向下取整，预留佣金）。已有持仓则拒绝。"""
        if self.shares > 0 or price <= 0:
            return False
        shares = int(self.cash // (price * self.lot_size)) * self.lot_size
        while shares > 0:
            amount = shares * price
            if amount + self._buy_fee(amount) <= self.cash + 1e-9:
                break
            shares -= self.lot_size
        if shares <= 0:
            return False
        amount = shares * price
        fee = self._buy_fee(amount)
        self.cash -= amount + fee
        self.shares = shares
        self.buy_date = date
        self.buy_cost = amount + fee
        self.trades.append({
            "date": date, "side": "buy", "price": round(float(price), 4),
            "shares": shares, "amount": round(amount, 2), "fee": round(fee, 2),
        })
        return True

    def _try_sell(self, date: str, price: float) -> bool:
        """平仓全部持仓。T+1：当日买入不可卖出（拒绝并返回 False）。"""
        if self.shares <= 0:
            return False
        if self.buy_date == date:
            return False   # T+1
        amount = self.shares * price
        fee = self._sell_fee(amount)
        pnl = (amount - fee) - self.buy_cost
        self.cash += amount - fee
        self.trades.append({
            "date": date, "side": "sell", "price": round(float(price), 4),
            "shares": self.shares, "amount": round(amount, 2), "fee": round(fee, 2),
        })
        self.closed_pnls.append(pnl)
        self.shares = 0
        self.buy_date = None
        self.buy_cost = 0.0
        return True

    def equity_value(self, price: float) -> float:
        """现金 + 持仓按 price 估值。"""
        return self.cash + self.shares * price

    def record_equity(self, date: str, price: float) -> None:
        self.equity.append({"date": date, "value": round(self.equity_value(price), 2)})


# ── 内置策略信号 ──

def _build_signal_fn(df: pd.DataFrame, strategy: str,
                     params: Dict[str, Any]) -> Callable:
    """构造策略信号函数 fn(df, i, state) -> 'buy'|'sell'|'hold'。

    信号基于截至当日（含当日）的收盘数据计算。自定义策略：
    params["strategy_fn"] 为 callable(df, i, state)。
    """
    p = dict(params or {})

    if strategy == "buy_hold":
        def buy_hold(df, i, state):
            return "buy" if i == 0 else "hold"
        return buy_hold

    if strategy == "ma_cross":
        fast = int(p.get("fast", 5))
        slow = int(p.get("slow", 20))
        if fast >= slow or fast < 1 or slow < 1:
            raise ValueError(f"ma_cross 参数无效: fast={fast} slow={slow}（需 0<fast<slow）")

        def ma_cross(df, i, state):
            if i < slow:
                return "hold"
            closes = df["close"].to_numpy(dtype=float)
            f = float(closes[i - fast + 1:i + 1].mean())
            s = float(closes[i - slow + 1:i + 1].mean())
            pf = float(closes[i - fast:i].mean())
            ps = float(closes[i - slow:i].mean())
            if pf <= ps and f > s:
                return "buy"
            if pf >= ps and f < s:
                return "sell"
            return "hold"
        return ma_cross

    if strategy == "rsi_reverse":
        period = int(p.get("period", 14))
        oversold = float(p.get("oversold", 30))
        overbought = float(p.get("overbought", 70))
        if period < 1 or oversold < 0 or overbought > 100 or oversold >= overbought:
            raise ValueError(
                f"rsi_reverse 参数无效: period={period} oversold={oversold} "
                f"overbought={overbought}")
        # 预计算 RSI（复用 Task A 的 calc_rsi，Wilder 平滑）
        rsi_arr = calc_rsi(df["close"], [period])[f"rsi{period}"].to_numpy(dtype=float)

        def rsi_reverse(df, i, state):
            v = rsi_arr[i] if i < len(rsi_arr) else np.nan
            if v is None or np.isnan(v):
                return "hold"
            if v < oversold:
                return "buy"
            if v > overbought:
                return "sell"
            return "hold"
        return rsi_reverse

    if strategy == "momentum":
        lookback = int(p.get("lookback", 20))
        if lookback < 1:
            raise ValueError(f"momentum 参数无效: lookback={lookback}")

        def momentum(df, i, state):
            if i < lookback:
                return "hold"
            closes = df["close"].to_numpy(dtype=float)
            return "buy" if closes[i] > closes[i - lookback] else "sell"
        return momentum

    if callable(p.get("strategy_fn")):
        return p["strategy_fn"]

    raise ValueError(f"未知策略: {strategy!r}（可选 {BUILTIN_STRATEGIES} 或 params['strategy_fn']）")


# ── 涨跌停（简版） ──

def _is_limit_up(pre_close, price) -> bool:
    return pre_close is not None and pre_close > 0 \
        and price / pre_close - 1.0 >= PRICE_LIMIT - _LIMIT_EPS


def _is_limit_down(pre_close, price) -> bool:
    return pre_close is not None and pre_close > 0 \
        and price / pre_close - 1.0 <= -PRICE_LIMIT + _LIMIT_EPS


# ── 基准（同区间 buy_hold） ──

def _buy_hold_benchmark(df: pd.DataFrame, initial_capital: float) -> dict:
    eng = BacktestEngine(initial_capital=float(initial_capital))
    closes = df["close"].to_numpy(dtype=float)
    dates = df["trade_date"].tolist()
    if len(df) > 0:
        eng._try_buy(dates[0], float(closes[0]))
        if eng.shares > 0 and eng.buy_date != dates[-1]:
            eng._try_sell(dates[-1], float(closes[-1]))
    final = eng.equity_value(float(closes[-1]))
    return {
        "final_value": round(float(final), 2),
        "total_return": round(float(final) / float(initial_capital) - 1.0, 6),
    }


# ── 错误结果 ──

def _error_result(symbol: str, message: str) -> dict:
    return {
        "symbol": symbol,
        "error": message,
        "period": None,
        "initial_capital": None,
        "final_value": None,
        "total_return": None,
        "annual_return": None,
        "max_drawdown": None,
        "sharpe": None,
        "win_rate": None,
        "num_trades": 0,
        "trades": [],
        "equity_curve": [],
        "benchmark": {"final_value": None, "total_return": None},
    }


# ── 参数校验 ──

def _validate_args(symbol, strategy, start, end, params, initial_capital):
    if not isinstance(symbol, str) or not _SYMBOL_RE.match(symbol):
        return _error_result(symbol, f"无效股票代码: {symbol!r}（需 6 位数字）")
    if not isinstance(start, str) or not _DATE_RE.match(start):
        return _error_result(symbol, f"无效开始日期: {start!r}（需 YYYYMMDD）")
    if not isinstance(end, str) or not _DATE_RE.match(end):
        return _error_result(symbol, f"无效结束日期: {end!r}（需 YYYYMMDD）")
    if start >= end:
        return _error_result(symbol, f"start 必须小于 end: {start} >= {end}")
    if strategy not in BUILTIN_STRATEGIES and not (
            isinstance(params, dict) and callable(params.get("strategy_fn"))):
        return _error_result(
            symbol, f"未知策略: {strategy!r}（可选 {BUILTIN_STRATEGIES} "
                    f"或 params['strategy_fn']）")
    try:
        cap = float(initial_capital)
        if not math.isfinite(cap) or cap <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _error_result(symbol, f"initial_capital 无效: {initial_capital!r}")
    return None


# ── 主入口 ──

def run_backtest(symbol: str, strategy: str, start: str, end: str,
                 params: Optional[Dict[str, Any]] = None,
                 initial_capital: float = DEFAULT_CAPITAL,
                 data_source: Optional[Callable] = None) -> dict:
    """运行 A 股单标的回测。

    参数
    ----
    symbol : 6 位股票代码（A 股，无后缀）。
    strategy : buy_hold | ma_cross | rsi_reverse | momentum。
    start/end : YYYYMMDD，start < end。
    params : 策略参数 dict（fast/slow、period/oversold/overbought、lookback、
             或自定义 strategy_fn）。
    initial_capital : 初始资金，默认 100000。
    data_source : 可选数据源 callable(symbol, start, end) -> DataFrame（测试注入）。

    返回
    ----
    dict：{symbol, period, initial_capital, final_value, total_return,
    annual_return, max_drawdown, sharpe, win_rate, num_trades, trades,
    equity_curve, benchmark}。无数据/非法参数时含 "error" 键。
    """
    err = _validate_args(symbol, strategy, start, end, params, initial_capital)
    if err is not None:
        return err
    capital = float(initial_capital)

    df = load_daily(symbol, start, end, data_source=data_source)
    if df is None or df.empty or len(df) == 0:
        return _error_result(symbol, "无行情数据（区间内没有交易日）")

    try:
        signal_fn = _build_signal_fn(df, strategy, params or {})
    except ValueError as exc:
        return _error_result(symbol, str(exc))

    eng = BacktestEngine(initial_capital=capital)
    opens = df["open"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    dates = df["trade_date"].tolist()
    n = len(df)
    state: Dict[str, Any] = {"symbol": symbol, "df": df}
    # 无未来函数：信号在当日收盘产生，次一交易日开盘价成交（buy_hold 例外：
    # 首日开盘直接建仓，不依赖信号）。T+1 天然满足（买入 bar 当日不产生可执行卖出）。
    pending: Optional[str] = None

    for i in range(n):
        date, price = dates[i], float(closes[i])
        pre_close = float(closes[i - 1]) if i > 0 else None

        # 1) 执行上一 bar 收盘产生的信号（今日开盘价成交）
        if pending is not None and i > 0:
            open_price = float(opens[i])
            if pending == "buy" and eng.shares == 0 and not _is_limit_up(pre_close, open_price):
                eng._try_buy(date, open_price)
            elif pending == "sell" and eng.shares > 0 and not _is_limit_down(pre_close, open_price):
                eng._try_sell(date, open_price)
            pending = None

        # 2) buy_hold 特判：首日开盘建仓
        if strategy == "buy_hold" and i == 0 and eng.shares == 0:
            open_price = float(opens[i])
            if not _is_limit_up(None, open_price):
                eng._try_buy(date, open_price)

        # 3) 计算当日信号（收盘后产生，次一交易日执行）
        try:
            sig = signal_fn(df, i, state)
        except Exception:
            sig = "hold"
        if sig == "buy" and eng.shares == 0:
            pending = "buy"
        elif sig == "sell" and eng.shares > 0:
            pending = "sell"

        # 4) 权益曲线按收盘价估值
        eng.record_equity(date, price)

    # 末日收盘强制平仓（估值性质，不检查涨跌停；T+1 仍适用：末日买入则无法当日平仓）
    if eng.shares > 0 and eng.buy_date != dates[-1]:
        eng._try_sell(dates[-1], float(closes[-1]))
    last_price = float(closes[-1])
    eng.equity[-1] = {"date": dates[-1], "value": round(eng.equity_value(last_price), 2)}

    # ── 指标 ──
    final_value = eng.equity_value(last_price)
    total_return = final_value / capital - 1.0
    if n >= 2:
        annual_return = (final_value / capital) ** (
            TRADING_DAYS_PER_YEAR / n) - 1.0
    else:
        annual_return = None

    values = np.array([e["value"] for e in eng.equity], dtype=float)
    peak = -np.inf
    max_drawdown = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - v) / peak)

    if len(values) >= 3:
        rets = values[1:] / values[:-1] - 1.0
        std = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
        if std > 1e-12:
            sharpe = float(np.mean(rets) / std) * math.sqrt(TRADING_DAYS_PER_YEAR)
        else:
            sharpe = None
    else:
        sharpe = None

    if eng.closed_pnls:
        win_rate = sum(1.0 for p in eng.closed_pnls if p > 0) / len(eng.closed_pnls)
    else:
        win_rate = None

    return {
        "symbol": symbol,
        "period": {"start": dates[0], "end": dates[-1]},
        "initial_capital": round(capital, 2),
        "final_value": round(float(final_value), 2),
        "total_return": round(float(total_return), 6),
        "annual_return": round(float(annual_return), 6) if annual_return is not None else None,
        "max_drawdown": round(float(max_drawdown), 6),
        "sharpe": round(float(sharpe), 6) if sharpe is not None else None,
        "win_rate": round(float(win_rate), 6) if win_rate is not None else None,
        "num_trades": len(eng.closed_pnls),
        "trades": eng.trades,
        "equity_curve": eng.equity,
        "benchmark": _buy_hold_benchmark(df, capital),
    }