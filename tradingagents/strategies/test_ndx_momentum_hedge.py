# -*- coding: utf-8 -*-
"""NDX 动量对冲策略测试（TDD）。

说明：Yahoo Finance（yfinance/query2）在此网络环境被 403/429 拦截，故测试通过
注入本地构造的价格序列验证策略核心逻辑，另测数据源失败时的降级行为。
"""
import numpy as np
import pandas as pd

from tradingagents.strategies.ndx_momentum_hedge import run_ndx_momentum_hedge, _fetch_prices


def _series(start, mom20, mom5, last, n=60):
    """构造 n 天价格序列：20日动量 = mom20，5日动量 = mom5（%）。

    分段线性：idx0..39 start->at20；idx40..53 at20->at54；idx54..59 at54->last
    dates[-20]=idx40，dates[-6]=idx54，dates[-1]=idx59
    """
    at20 = last / (1 + mom20 / 100)
    at54 = last / (1 + mom5 / 100)
    s1 = np.linspace(start, at20, 40)
    s2 = np.linspace(at20, at54, 14)
    s3 = np.linspace(at54, last, 6)
    return [round(float(x), 4) for x in np.concatenate([s1, s2, s3])]


def _make_prices():
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-05-01", periods=60)]
    # (symbol, mom20%, mom5%, last)
    stocks = [
        ("NVDA", 12.0, 9.0, 130.0),
        ("MSFT", 9.0, 6.0, 110.0),
        ("GOOGL", 7.0, 5.0, 95.0),
        ("AMZN", 5.0, 4.0, 85.0),
        ("TSLA", 4.0, 2.5, 70.0),
        ("AAPL", 2.0, 1.0, 60.0),   # 20日动量>0 但 5日动量低，不入选
        ("AMD", -3.0, 0.5, 50.0),   # 20日动量<=0 被过滤
    ]
    prices = {}
    for sym, m20, m5, last in stocks:
        prices[sym] = dict(zip(dates, _series(60.0, m20, m5, last)))
    # QQQ: today=120, dates[-6]=117 → 周涨 2.6%；last_week=dates[-5]=118 → qqq_w≈1.7%
    qqq = _series(100.0, 20.0, 2.5, 120.0)
    prices["QQQ"] = dict(zip(dates, qqq))
    # PSQ: 反向，today=24, dates[-5]=24.8 → psq_w≈-3.2%
    psq = _series(30.0, -12.0, -3.0, 24.0)
    prices["PSQ"] = dict(zip(dates, psq))
    return prices


FAKE = _make_prices()


def test_report_shape():
    """报告结构：dict 含 top_symbols / performance / momentum_top5"""
    r = run_ndx_momentum_hedge(prices=FAKE)
    assert isinstance(r, dict)
    assert "top_symbols" in r and isinstance(r["top_symbols"], list)
    assert "performance" in r
    assert "momentum_top5" in r
    assert "date" in r and "week_start" in r
    assert "pool_size" in r
    assert "changes" in r
    assert "qqq_12w" in r
    assert "full_momentum" in r


def test_selection_rules():
    """方案B选股：20日动量>0 过滤 + 按5日动量降序取前5"""
    r = run_ndx_momentum_hedge(prices=FAKE)
    assert r["top_symbols"] == ["NVDA", "MSFT", "GOOGL", "AMZN", "TSLA"]
    assert len(r["momentum_top5"]) == 5
    for m in r["momentum_top5"]:
        assert m["momentum"] > 0
        assert m["momentum_5d"] is not None
    m5s = [m["momentum_5d"] for m in r["momentum_top5"]]
    assert m5s == sorted(m5s, reverse=True)


def test_performance_shape():
    r = run_ndx_momentum_hedge(prices=FAKE)
    p = r["performance"]
    assert set(p.keys()) == {"strategy_w", "qqq_w", "psq_w"}
    assert isinstance(p["qqq_w"], (int, float))
    assert isinstance(p["strategy_w"], (int, float))
    # strategy_w = 持仓股平均5日动量*0.5 + psq_w*0.5
    avg5 = sum(m["momentum_5d"] for m in r["momentum_top5"]) / len(r["momentum_top5"])
    expect = round(avg5 * 0.5 + p["psq_w"] * 0.5, 1)
    assert p["strategy_w"] == expect


def test_data_failure_returns_error(monkeypatch):
    """数据源全部失败时返回 {"error": ...}，不抛异常"""
    monkeypatch.setattr("tradingagents.strategies.ndx_momentum_hedge._fetch_prices", lambda tickers: {})
    r = run_ndx_momentum_hedge()
    assert isinstance(r, dict)
    assert "error" in r