"""龟龟估值引擎移植测试。

注意：会真实调用 akshare 数据源（依赖网络，首次运行较慢）。
- TUSHARE_RATE_DELAY=0 关闭龟龟 rate_limit sleep
- 龟龟 TTL 磁盘缓存（output/.collector_cache/ttl）默认启用，缓存命中后单次约 20-40s；
  如需强制刷新可设 TURTLE_TTL_CACHE=0 关闭
"""
import os

os.environ.setdefault("TUSHARE_RATE_DELAY", "0")
os.environ.setdefault("TURTLE_TTL_CACHE", "1")

import pytest


@pytest.mark.slow
def test_valuation_runs():
    from tradingagents.strategies.turtle.adapter import run_turtle_valuation

    r = run_turtle_valuation("000001.SZ")
    assert "error" not in r, r.get("error")
    assert r.get("ts_code") == "000001.SZ"
    md = r.get("markdown") or ""
    assert md and "估值" in md


@pytest.mark.slow
def test_valuation_normalizes_ts_code():
    """无后缀 6 位纯数字在入口被规范化为 A 股 ts_code（000001 -> 000001.SZ）"""
    from tradingagents.strategies.turtle.adapter import run_turtle_valuation

    r = run_turtle_valuation("000001")
    assert "error" not in r, r.get("error")
    assert r.get("ts_code") == "000001.SZ"


def test_valuation_rejects_invalid():
    """非法 ts_code 返回 {"error"} 而非抛异常"""
    from tradingagents.strategies.turtle.adapter import run_turtle_valuation

    r = run_turtle_valuation("abc")
    assert isinstance(r, dict)
    assert "error" in r
    assert r.get("ts_code") == "abc"
