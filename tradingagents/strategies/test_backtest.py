# -*- coding: utf-8 -*-
"""A股回测引擎单元测试（test_backtest.py）

覆盖：buy_hold 收益/权益曲线、MA 交叉、RSI 反转、动量、T+1、涨跌停、
手续费、空数据/非法参数。全部注入 fake data_source，不访问网络。
"""
import numpy as np
import pandas as pd
import pytest

from tradingagents.strategies.backtest.engine import BacktestEngine, run_backtest


def _dates(n, start="20240101"):
    s = pd.Timestamp(start)
    return [(s + pd.Timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]


def _make_df(closes, dates=None):
    """桥接层口径 DataFrame（trade_date=YYYYMMDD，open/high/low/close/volume）"""
    n = len(closes)
    if dates is None:
        dates = _dates(n)
    return pd.DataFrame({
        "trade_date": dates,
        "open": [float(c) for c in closes],
        "high": [float(c) for c in closes],
        "low": [float(c) for c in closes],
        "close": [float(c) for c in closes],
        "volume": [10000] * n,
    })


def _fake_source(df):
    def source(symbol, start, end):
        return df.copy()
    return source


# ---------- buy_hold ----------

def test_buy_hold_known_series():
    """buy_hold: total_return ≈ 末价/首价-1（扣手续费）；权益曲线长度=交易日数"""
    closes = [10.0 + 0.2 * i for i in range(10)]   # 10 -> 11.8
    r = run_backtest("600000", "buy_hold", "20240101", "20240131",
                     params={}, data_source=_fake_source(_make_df(closes)))
    assert "error" not in r, r
    expect = closes[-1] / closes[0] - 1.0
    assert abs(r["total_return"] - expect) < 0.03, r["total_return"]
    assert r["final_value"] > 100000
    assert len(r["equity_curve"]) == 10
    assert r["trades"][0]["side"] == "buy"
    assert r["benchmark"]["total_return"] > 0


# ---------- ma_cross ----------

def test_ma_cross_produces_trades():
    """ma_cross: 先跌后涨（金叉）再跌（死叉）序列产生买入+卖出"""
    down = [10.0 - 0.2 * i for i in range(20)]
    up = [down[-1] + 0.3 * i for i in range(1, 31)]
    tail = [up[-1] - 0.3 * i for i in range(1, 21)]
    closes = down + up + tail
    r = run_backtest("600000", "ma_cross", "20240101", "20240401",
                     params={"fast": 5, "slow": 20},
                     data_source=_fake_source(_make_df(closes)))
    assert "error" not in r, r
    assert r["num_trades"] >= 1, r["trades"]
    sides = [t["side"] for t in r["trades"]]
    assert "buy" in sides and "sell" in sides, r["trades"]
    buys = [t for t in r["trades"] if t["side"] == "buy"]
    sells = [t for t in r["trades"] if t["side"] == "sell"]
    assert sells[0]["date"] > buys[0]["date"]


# ---------- rsi_reverse ----------

def test_rsi_reverse_buys_on_oversold():
    """rsi_reverse: 连跌致 RSI 超卖后触发买入"""
    down = [10.0 - 0.25 * i for i in range(15)]
    up = [down[-1] + 0.2 * i for i in range(1, 21)]
    closes = down + up
    r = run_backtest("600000", "rsi_reverse", "20240101", "20240301",
                     params={"period": 14, "oversold": 30, "overbought": 70},
                     data_source=_fake_source(_make_df(closes)))
    assert "error" not in r, r
    assert any(t["side"] == "buy" for t in r["trades"]), r["trades"]


# ---------- momentum ----------

def test_momentum_hold_and_exit():
    """momentum: 上升段持仓买入、下降段平仓"""
    up = [10.0 + 0.2 * i for i in range(40)]
    down = [up[-1] - 0.25 * i for i in range(1, 26)]
    closes = up + down
    r = run_backtest("600000", "momentum", "20240101", "20240401",
                     params={"lookback": 20},
                     data_source=_fake_source(_make_df(closes)))
    assert "error" not in r, r
    sides = [t["side"] for t in r["trades"]]
    assert "buy" in sides and "sell" in sides, r["trades"]


# ---------- T+1 ----------

def test_t_plus_1_blocks_same_day_sell():
    """T+1: 买入当日卖出被拒，次日允许"""
    eng = BacktestEngine(initial_capital=100000)
    assert eng._try_buy("20240102", 10.0)
    assert eng._try_sell("20240102", 10.5) is False   # 当日不可卖
    assert eng._try_sell("20240103", 10.5) is True    # 次日可卖


# ---------- 涨跌停 ----------

def test_limit_up_blocks_buy():
    """涨停（close 较前收 +10%）当日买入被拒（简版）"""
    closes = [10.0] * 4 + [11.0]
    dates = _dates(len(closes))

    def fn(df, i, state):
        return "buy" if i == len(df) - 1 else "hold"

    r = run_backtest("600000", "custom", "20240101", "20240131",
                     params={"strategy_fn": fn},
                     data_source=_fake_source(_make_df(closes, dates)))
    assert "error" not in r, r
    assert all(t["side"] != "buy" for t in r["trades"]), r["trades"]
    assert r["num_trades"] == 0


def test_limit_down_blocks_sell():
    """跌停（close 较前收 -10%）当日卖出被拒，次日恢复后卖出（简版）"""
    closes = [10.0] * 3 + [9.0, 9.5]
    dates = _dates(len(closes))

    def fn(df, i, state):
        if i == 0:
            return "buy"
        if i >= 3:
            return "sell"
        return "hold"

    r = run_backtest("600000", "custom", "20240101", "20240131",
                     params={"strategy_fn": fn},
                     data_source=_fake_source(_make_df(closes, dates)))
    assert "error" not in r, r
    sells = [t for t in r["trades"] if t["side"] == "sell"]
    assert len(sells) == 1, r["trades"]
    assert sells[0]["date"] == dates[4], sells[0]["date"]


# ---------- 手续费 ----------

def test_fee_calculation():
    """手续费: 佣金 万2.5（最低 5）+ 卖出印花税 千0.5"""
    closes = [10.0, 12.0]
    dates = _dates(len(closes))

    def fn(df, i, state):
        if i == 0:
            return "buy"
        if i == 1:
            return "sell"
        return "hold"

    r = run_backtest("600000", "custom", "20240101", "20240102",
                     params={"strategy_fn": fn}, initial_capital=100500,
                     data_source=_fake_source(_make_df(closes, dates)))
    assert "error" not in r, r
    buys = [t for t in r["trades"] if t["side"] == "buy"]
    sells = [t for t in r["trades"] if t["side"] == "sell"]
    assert len(buys) == 1 and len(sells) == 1, r["trades"]
    b, s = buys[0], sells[0]
    assert b["shares"] == 10000          # 100500 现金整手 10000 股 @10
    assert b["amount"] == pytest.approx(100000.0)
    assert b["fee"] == pytest.approx(25.0)        # max(100000*0.00025, 5) = 25
    assert s["amount"] == pytest.approx(120000.0)
    assert s["fee"] == pytest.approx(90.0)        # 佣金 30 + 印花税 60


# ---------- 空数据 / 非法参数 ----------

def test_empty_data_returns_error():
    """无数据 -> 返回 error，不抛异常"""
    r = run_backtest("600000", "buy_hold", "20240101", "20240131",
                     data_source=_fake_source(pd.DataFrame()))
    assert isinstance(r, dict) and "error" in r
    assert r["trades"] == []
    assert r["num_trades"] == 0


def test_invalid_params_returns_error():
    """非法参数 -> 返回 error，不抛异常"""
    r = run_backtest("abc", "buy_hold", "20240101", "20240131")
    assert "error" in r
    r2 = run_backtest("600000", "buy_hold", "20240131", "20240101")
    assert "error" in r2
    r3 = run_backtest("600000", "no_such", "20240101", "20240131")
    assert "error" in r3
    r4 = run_backtest("600000", "buy_hold", "20240101", "20240131",
                      initial_capital=-100)
    assert "error" in r4