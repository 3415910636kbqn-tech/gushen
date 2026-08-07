"""龟龟估值引擎移植测试。

注意：会真实调用 akshare 数据源（依赖网络，首次运行较慢）。
- TUSHARE_RATE_DELAY=0 关闭龟龟 rate_limit sleep
- TURTLE_TTL_CACHE=1 启用龟龟 TTL 磁盘缓存（output/.collector_cache/ttl），
  缓存命中后单次约 20-40s
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
