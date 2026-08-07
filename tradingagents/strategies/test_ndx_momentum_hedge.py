# -*- coding: utf-8 -*-
"""NDX 动量对冲策略测试（TDD）。

说明：Yahoo Finance（yfinance/query2）在此网络环境被 403/429 拦截，故测试通过
注入本地构造的价格序列验证策略核心逻辑，另测数据源失败时的降级行为。
"""
import json
import os

import numpy as np
import pandas as pd
import pytest

import tradingagents.strategies.ndx_momentum_hedge as mod
from tradingagents.strategies.ndx_momentum_hedge import run_ndx_momentum_hedge, _fetch_prices


@pytest.fixture(autouse=True)
def _isolate_files(tmp_path, monkeypatch):
    """每个测试用独立 tmp 目录隔离缓存/last_top 文件，避免污染真实 data/cache"""
    monkeypatch.setattr(mod, "CACHE_PATH", str(tmp_path / "ndx_prices.pkl"))
    monkeypatch.setattr(mod, "LAST_TOP_PATH", str(tmp_path / "ndx_last_top.json"))


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


def test_fetch_prices_uses_fresh_cache(monkeypatch):
    """数据源可用时，2 小时内缓存命中则直接返回，不触发任何网络拉取"""
    fake = {"QQQ": FAKE["QQQ"], "PSQ": FAKE["PSQ"]}
    mod._save_cache(fake)
    hits = {"n": 0}

    def boom(*args, **kwargs):
        hits["n"] += 1
        raise AssertionError("缓存命中时不应触发网络拉取")

    monkeypatch.setattr(mod, "_yahoo_probe", lambda: True)
    monkeypatch.setattr(mod, "_fetch_prices_yf", boom)
    monkeypatch.setattr(mod, "_fetch_prices_query2", boom)
    out = mod._fetch_prices(mod.NDX_100)
    assert out == fake
    assert hits["n"] == 0


def test_fetch_prices_writes_cache_and_hits_next_call(monkeypatch):
    """拉取成功后写入缓存；再次调用命中缓存返回相同数据，且只拉取一次"""
    n = {"calls": 0}

    def fake_yf(tickers):
        n["calls"] += 1
        return dict(FAKE)

    monkeypatch.setattr(mod, "_yahoo_probe", lambda: True)
    monkeypatch.setattr(mod, "_fetch_prices_yf", fake_yf)
    monkeypatch.setattr(mod, "_fetch_prices_query2", lambda t: {})
    first = mod._fetch_prices(mod.NDX_100)
    second = mod._fetch_prices(mod.NDX_100)
    assert first == second
    assert n["calls"] == 1  # 第二次命中缓存，未重新拉取
    assert os.path.exists(mod.CACHE_PATH)
    assert first.get("QQQ")  # 缓存内容含 QQQ


def test_changes_persist_to_file(monkeypatch):
    """changes 基于 JSON 文件持久化：预置上次持仓后，报告写入新持仓并计算增删"""
    mod._save_last_top(["NVDA", "MSFT", "GOOGL", "AMZN", "X"])  # 上次持仓含 X，缺 TSLA
    r = run_ndx_momentum_hedge(prices=FAKE)
    assert r["changes"]["added"] == ["TSLA"]
    assert r["changes"]["removed"] == ["X"]
    # 本次持仓已写回文件
    with open(mod.LAST_TOP_PATH, "r", encoding="utf-8") as f:
        assert json.load(f) == r["top_symbols"]
    # 再次运行（模拟服务重启后），changes 基于文件：无新增无移除
    r2 = run_ndx_momentum_hedge(prices=FAKE)
    assert r2["changes"]["added"] == []
    assert r2["changes"]["removed"] == []
    assert r2["changes"]["kept"] == r2["top_symbols"]
