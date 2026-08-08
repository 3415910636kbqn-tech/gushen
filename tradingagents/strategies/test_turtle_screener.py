"""龟龟选股器移植测试（Task 4）。

- test_tier1_runs：真实全市场 Tier1（akshare 数据，耗时较长，标 slow）
- test_tier1_filter_logic_*：monkeypatch 注入 fake daily_basic，验证
  过滤/排名逻辑、dv_ttm 全 None 降级、list_date NaN 掩码
"""
import pandas as pd
import pytest

from tradingagents.strategies.turtle.screener_adapter import run_turtle_screener
from tradingagents.strategies.turtle import screener_core as sc


def _make_fake_bulk():
    """构造 Tier1 bulk 数据（模拟 stock_basic + daily_basic 合并结果）。"""
    return pd.DataFrame({
        "ts_code": ["600001.SH", "600002.SH", "600003.SH", "000004.SZ",
                    "000005.SZ", "000006.SZ", "000007.SZ", "000008.SZ"],
        "name": ["正常甲", "*ST退市", "银行丙", "无上市日丁", "次新戊",
                 "亏损己", "零pb庚", "低换手辛"],
        "industry": ["工业", "工业", "银行", "工业", "工业", "工业", "工业", "工业"],
        "area": ["上海", "上海", "上海", "深圳", "深圳", "深圳", "深圳", "深圳"],
        "market": ["主板", "主板", "主板", "主板", "主板", "主板", "主板", "主板"],
        "list_date": ["20150101", "20100101", "20100101", None,
                      "20990101", "20100101", "20100101", "20100101"],
        "close": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
        "pe_ttm": [10.0, 15.0, 20.0, 12.0, 18.0, None, 14.0, 16.0],
        "pb": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 0.0, 7.0],
        "total_mv": [1e6, 2e6, 3e6, 4e6, 5e6, 6e6, 7e6, 8e6],   # 万元
        "circ_mv": [1e6, 2e6, 3e6, 4e6, 5e6, 6e6, 7e6, 8e6],
        "dv_ttm": [None] * 8,  # 全 None：模拟 akshare 全市场无股息率
        "turnover_rate": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 0.05],
    })


def _run_tier1_with_bulk(monkeypatch, bulk_df):
    s = sc.TushareScreener(token="")
    monkeypatch.setattr(s, "_tier1_bulk_data", lambda force_refresh=False: bulk_df)
    return s.run(tier1_only=True)


def test_tier1_filter_logic_dvttm_degrade(monkeypatch):
    """dv_ttm 全 None 时主通道不被过滤空；ST/银行/上市不足/零PB/低换手被滤。"""
    df = _run_tier1_with_bulk(monkeypatch, _make_fake_bulk())
    assert not df.empty
    mains = df[df["channel"] == "main"]
    assert not mains.empty  # 降级生效：全 None dv_ttm 不再滤掉主通道
    ts = set(df["ts_code"])
    assert "600002.SH" not in ts  # *ST
    assert "600003.SH" not in ts  # 银行（include_bank=False）
    assert "000005.SZ" not in ts  # 上市不足 3 年（2099 年上市）
    assert "000007.SZ" not in ts  # pb=0
    assert "000008.SZ" not in ts  # 换手率过低
    assert "000004.SZ" in ts      # list_date=None 保留（NaN 掩码）
    assert "000006.SZ" in set(df[df["channel"] == "observation"]["ts_code"])  # pe NaN→obs


def test_tier1_filter_logic_dvttm_normal(monkeypatch):
    """dv_ttm 部分有效时按原逻辑过滤（dv=0 被滤出主通道）。"""
    bulk = _make_fake_bulk()
    bulk.loc[bulk["ts_code"] == "600001.SH", "dv_ttm"] = 2.0
    bulk.loc[bulk["ts_code"] == "000004.SZ", "dv_ttm"] = 0.0
    df = _run_tier1_with_bulk(monkeypatch, bulk)
    assert not df.empty
    mains = df[df["channel"] == "main"]
    assert "600001.SH" in set(mains["ts_code"])
    assert "000004.SZ" not in set(mains["ts_code"])  # dv_ttm=0 被主通道滤出


@pytest.mark.slow
def test_tier1_runs():
    """真实全市场 Tier1（akshare 拉取，首次较慢；磁盘缓存后加速）。"""
    r = run_turtle_screener(tier1_only=True, tier2_limit=5)
    assert "error" not in r, r.get("error")
    assert "candidates" in r
    assert isinstance(r["candidates"], list)
    # 候选必须可 JSON 序列化（不能含 NaN/inf，否则 API 返回 500）
    import json
    json.dumps(r, ensure_ascii=False)
