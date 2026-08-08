# -*- coding: utf-8 -*-
"""筹码分布 CYQ 单元测试(chips.py)"""
import numpy as np
import pandas as pd

from tradingagents.strategies.chips import calc_chip_distribution, FACTOR


def _row(date, o, h, l, c, tr=None):
    row = {"date": date, "open": o, "high": h, "low": l, "close": c}
    if tr is not None:
        row["turnover_rate"] = tr
    return row


def _df(rows):
    return pd.DataFrame(rows)


def _single_peak_df():
    """构造单峰筹码序列:底部 ~9 元低换手温区 + 主峰 10 元高换手密集成交"""
    rows = []
    for i in range(10):
        rows.append(_row(f"2024-01-{i + 1:02d}", 9.0, 9.3, 8.9, 9.1, 1.0))
    for i in range(20):
        rows.append(_row(f"2024-02-{i + 1:02d}", 10.0, 10.02, 9.98, 10.01, 8.0))
    rows.append(_row("2024-03-01", 10.02, 10.05, 9.98, 10.03, 3.0))
    return _df(rows)


def test_single_peak_basic():
    """单峰筹码:获利比例 0..1、平均成本≈10、90/70 成本区间包含峰、peak≈10"""
    r = calc_chip_distribution(_single_peak_df())
    assert 0.0 <= r["profit_ratio"] <= 1.0
    assert 9.5 <= r["avg_cost"] <= 10.5, r["avg_cost"]
    lo90, hi90 = r["cost_90"]
    assert lo90 <= 10.0 <= hi90, r["cost_90"]
    lo70, hi70 = r["cost_70"]
    assert lo70 <= 10.0 <= hi70, r["cost_70"]
    assert 9.8 <= r["peak_price"] <= 10.2, r["peak_price"]
    # 直方图:150 档、价格升序、权重归一化
    hist = r["histogram"]
    assert len(hist) == FACTOR
    assert abs(sum(w for _, w in hist) - 1.0) < 1e-4
    prices = [p for p, _ in hist]
    assert all(a <= b for a, b in zip(prices, prices[1:]))


def test_single_peak_high_close_profit_ratio():
    """收盘在峰之上时获利比例接近 1;收盘在峰之下时接近 0"""
    base = _single_peak_df()
    up = base.copy()
    up.loc[up.index[-1], "close"] = 11.0
    r = calc_chip_distribution(up)
    assert r["profit_ratio"] >= 0.99, r["profit_ratio"]
    down = base.copy()
    down.loc[down.index[-1], "close"] = 8.5
    r = calc_chip_distribution(down)
    assert r["profit_ratio"] <= 0.01, r["profit_ratio"]


def test_limit_up_sequence():
    """一字板序列(high==low)不抛异常,筹码堆在单一价格档"""
    rows = [_row(f"2024-01-{i + 1:02d}", 10.0, 10.0, 10.0, 10.0, 5.0)
            for i in range(30)]
    r = calc_chip_distribution(_df(rows))
    assert r["avg_cost"] == 10.0
    assert r["cost_90"] == [10.0, 10.0]
    assert r["cost_70"] == [10.0, 10.0]
    assert 0.0 <= r["profit_ratio"] <= 1.0
    assert r["peak_price"] == 10.0
    assert abs(sum(w for _, w in r["histogram"]) - 1.0) < 1e-4


def test_nan_turnover_rate():
    """换手率全 NaN:按 0 换手(纯衰减不叠加),分布退化返回全 None 而非抛异常"""
    rows = [_row(f"2024-01-{i + 1:02d}", 9.0, 9.5, 8.8, 9.2, np.nan)
            for i in range(30)]
    r = calc_chip_distribution(_df(rows))
    assert r["avg_cost"] is None
    assert r["profit_ratio"] is None
    assert r["peak_price"] is None
    assert r["cost_90"] == [None, None]
    assert r["histogram"] == []


def test_partial_nan_turnover_ok():
    """部分换手率为 NaN(停牌/缺失)不抛异常,正常输出"""
    rows = _single_peak_df().to_dict("records")
    rows[5]["turnover_rate"] = np.nan
    rows[15]["turnover_rate"] = np.nan
    r = calc_chip_distribution(_df(rows))
    assert r["avg_cost"] is not None
    assert 0.0 <= r["profit_ratio"] <= 1.0


def test_empty_input():
    """空输入不抛异常,返回全 None"""
    r = calc_chip_distribution(pd.DataFrame())
    assert r["avg_cost"] is None
    assert r["histogram"] == []


def test_all_nan_ohlc():
    """OHLC 全 NaN(无有效 bar)不抛异常,返回全 None"""
    rows = [{"date": "2024-01-01", "open": np.nan, "high": np.nan,
             "low": np.nan, "close": np.nan, "turnover_rate": 2.0}
            for _ in range(10)]
    r = calc_chip_distribution(_df(rows))
    assert r["avg_cost"] is None
    assert r["histogram"] == []


def test_dirty_row_skipped():
    """中间混入 OHLC 脏行不中断整段计算(源码 isValidBar 语义)"""
    rows = _single_peak_df().to_dict("records")
    rows.insert(15, {"date": "2024-01-15", "open": np.nan, "high": np.nan,
                     "low": np.nan, "close": np.nan, "turnover_rate": 9.0})
    r = calc_chip_distribution(_df(rows))
    assert r["avg_cost"] is not None
    assert 9.5 <= r["avg_cost"] <= 10.5


def test_missing_turnover_column():
    """缺 turnover_rate 列(如新浪回退路径)不抛异常,按 0 换手 -> 退化"""
    rows = [_row(f"2024-01-{i + 1:02d}", 9.0, 9.5, 8.8, 9.2) for i in range(30)]
    r = calc_chip_distribution(_df(rows))
    assert r["avg_cost"] is None
    assert r["histogram"] == []


def test_trade_date_column_alias():
    """trade_date 列名(桥接层 tushare 口径)兼容"""
    rows = []
    for i in range(20):
        rows.append({"trade_date": f"2024-01-{i + 1:02d}", "open": 10.0,
                     "high": 10.0, "low": 10.0, "close": 10.0, "turnover_rate": 5.0})
    r = calc_chip_distribution(_df(rows))
    assert r["avg_cost"] == 10.0
