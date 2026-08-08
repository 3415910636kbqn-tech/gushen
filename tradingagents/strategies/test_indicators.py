"""技术指标库测试（stock-sdk TS 算法 → pandas 移植）。

覆盖：MA(SMA/EMA/WMA) / MACD / BOLL / KDJ / RSI / WR / BIAS / CCI / ATR
/ OBV / ROC / DMI / SAR / KC + 组合入口 calculate_indicators。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tradingagents.strategies.indicators import (
    calc_sma,
    calc_ema,
    calc_wma,
    calc_ma,
    calc_macd,
    calc_boll,
    calc_kdj,
    calc_rsi,
    calc_wr,
    calc_bias,
    calc_cci,
    calc_atr,
    calc_obv,
    calc_roc,
    calc_dmi,
    calc_sar,
    calc_kc,
    calculate_indicators,
)


def make_df(closes, spread=1.0, volume=100.0):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + spread,
            "low": closes - spread,
            "close": closes,
            "volume": float(volume),
        },
        index=pd.RangeIndex(n),
    )


# ---------- MA 族 ----------

def test_sma_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = calc_sma(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert np.allclose(out.iloc[2:].to_numpy(), [2.0, 3.0, 4.0])


def test_ema_basic():
    # period=3 → alpha=0.5；种子 SMA(1,2,3)=2，之后 EMA 递推
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = calc_ema(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert np.allclose(out.iloc[2:].to_numpy(), [2.0, 3.0, 4.0])


def test_wma_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    # TS calcWMA 默认 round(3)，故 14/6 → 2.333
    out = calc_wma(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert np.isclose(out.iloc[2], 2.333)
    assert np.isclose(out.iloc[3], 3.333)  # round(20/6, 3)
    # 高精度下验证 WMA 公式本身
    out6 = calc_wma(s, 3, decimals=6)
    assert np.isclose(out6.iloc[2], (1 * 1 + 2 * 2 + 3 * 3) / 6)
    assert np.isclose(out6.iloc[3], (2 * 1 + 3 * 2 + 4 * 3) / 6)


def test_ma_combined():
    closes = pd.Series(np.arange(1.0, 51.0))
    res = calc_ma(closes, periods=[5, 10])
    assert set(res.keys()) == {"ma5", "ma10"}
    assert np.isclose(res["ma5"].iloc[4], 3.0)  # mean(1..5)=3
    assert np.isclose(res["ma10"].iloc[9], 5.5)  # mean(1..10)=5.5


# ---------- MACD ----------

def test_macd_golden_cross():
    closes = []
    price = 100.0
    for i in range(150):
        if i < 60:
            price -= 0.4
        elif i < 100:
            price -= 0.6
        else:
            price += 1.0
        closes.append(price)
    closes = pd.Series(closes)
    res = calc_macd(closes)
    dif, dea, macd = res["dif"], res["dea"], res["macd"]
    cross_up = (dif > dea) & (dif.shift(1) <= dea.shift(1))
    assert cross_up.any(), "先跌后涨应出现 MACD 金叉"
    idx = cross_up[cross_up].index[0]
    assert dif.loc[idx] > dea.loc[idx]
    assert macd.loc[idx] > 0  # 金叉处差值为正
    # DIF = EMA12 - EMA26
    assert np.allclose(
        dif.dropna(),
        (calc_ema(closes, 12) - calc_ema(closes, 26)).dropna(),
    )


# ---------- RSI ----------

def test_rsi_bounds():
    closes = pd.Series(10.0 + np.cumsum(np.sin(np.arange(120) / 7.0)))
    res = calc_rsi(closes, periods=[6, 14])
    for key, s in res.items():
        valid = s.dropna()
        assert not valid.empty
        assert valid.between(0.0, 100.0).all()


def test_rsi_pure_up_down():
    up = pd.Series(np.arange(1.0, 50.0))
    r_up = calc_rsi(up, periods=[6])["rsi6"].dropna()
    assert (r_up > 99.0).all()  # 纯涨 → RSI 接近/等于 100
    down = pd.Series(np.arange(50.0, 1.0, -1.0))
    r_down = calc_rsi(down, periods=[6])["rsi6"].dropna()
    assert (r_down < 1.0).all()  # 纯跌 → RSI 接近/等于 0


# ---------- 波动/通道类 ----------

def test_boll_bands():
    closes = pd.Series(100.0 + 5.0 * np.sin(np.arange(80) / 5.0))
    res = calc_boll(closes, period=10)
    assert np.allclose(res["mid"].dropna(), calc_sma(closes, 10).dropna())
    valid = res["upper"].notna()
    assert (res["upper"][valid] >= res["mid"][valid]).all()
    assert (res["lower"][valid] <= res["mid"][valid]).all()
    assert (res["bandwidth"][valid] >= 0).all()


def test_kc_bands():
    df = make_df(np.linspace(100.0, 130.0, 80))
    res = calc_kc(df)
    assert np.allclose(res["mid"].dropna(), calc_ema(df["close"], 20).dropna())
    valid = res["upper"].notna()
    assert (res["upper"][valid] >= res["mid"][valid]).all()
    assert (res["lower"][valid] <= res["mid"][valid]).all()


def test_atr_constant_range():
    df = make_df(np.full(40, 10.0), spread=1.0)
    res = calc_atr(df, period=2)
    assert np.isclose(res["atr"].iloc[1:], 2.0).all()
    res14 = calc_atr(df, period=14)
    assert np.isclose(res14["atr"].iloc[13:], 2.0).all()


def test_cci_flat_is_zero():
    df = make_df(np.full(30, 10.0), spread=1.0)
    cci = calc_cci(df, period=14).dropna()
    assert np.isclose(cci, 0.0).all()


# ---------- 超买超卖类 ----------

def test_kdj_uptrend():
    closes = np.concatenate([np.full(30, 100.0), np.linspace(100.0, 120.0, 30)])
    df = make_df(closes, spread=1.0)
    res = calc_kdj(df)
    assert len(res["k"]) == len(df)
    k = res["k"].dropna()
    assert not k.empty
    assert k.between(0.0, 100.0).all()
    assert res["k"].iloc[-1] > 50  # 上涨后 K 进入高位


def test_wr_bounds():
    df = make_df(100.0 + 8.0 * np.sin(np.arange(60) / 4.0), spread=3.0)
    res = calc_wr(df, periods=[6, 10])
    for key, s in res.items():
        valid = s.dropna()
        assert not valid.empty
        assert valid.between(0.0, 100.0).all()


def test_bias_uptrend_positive():
    closes = pd.Series(np.linspace(10.0, 20.0, 60))
    res = calc_bias(closes, periods=[6, 12])
    assert res["bias6"].iloc[-1] > 0
    assert res["bias12"].iloc[-1] > 0


# ---------- 量能/动量类 ----------

def test_obv_add_subtract():
    df = pd.DataFrame(
        {
            "open": [1.0, 2.0, 1.0, 2.0, 1.0, 2.0],
            "high": [2.0, 3.0, 2.0, 3.0, 2.0, 3.0],
            "low": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
            "close": [1.0, 2.0, 1.0, 2.0, 1.0, 2.0],
            "volume": [100.0, 50.0, 60.0, 70.0, 80.0, 90.0],
        }
    )
    res = calc_obv(df)
    assert np.allclose(res["obv"].to_numpy(), [100.0, 150.0, 90.0, 160.0, 80.0, 170.0])


def test_roc_uptrend():
    closes = np.linspace(10.0, 20.0, 50)
    df = make_df(closes)
    res = calc_roc(df, period=5, signal_period=3)
    assert res["roc"].iloc[5] > 0
    assert not res["signal"].dropna().empty


def test_dmi_uptrend():
    closes = np.linspace(10.0, 30.0, 60)
    df = make_df(closes, spread=0.5)
    res = calc_dmi(df, period=14)
    assert res["pdi"].iloc[-1] > res["mdi"].iloc[-1]
    adx = res["adx"].dropna()
    assert (adx >= 0).all()


def test_sar_runs():
    closes = np.linspace(10.0, 25.0, 50)
    df = make_df(closes, spread=0.5)
    res = calc_sar(df)
    assert len(res["sar"]) == len(df)
    sar_valid = res["sar"].dropna()
    assert not sar_valid.empty
    # 上升趋势中 SAR 位于价格下方
    assert res["sar"].iloc[-1] < closes[-1]


# ---------- 组合入口 ----------

def test_calculate_indicators_full():
    n = 100
    closes = np.linspace(50.0, 80.0, n)
    df = make_df(closes, spread=1.0)
    res = calculate_indicators(
        df,
        {
            "ma": [5, 10, 20],
            "macd": {"fast": 12, "slow": 26, "signal": 9},
            "kdj": {},
            "rsi": {"period": 14},
            "boll": {},
            "wr": [6],
            "bias": [6, 12],
            "cci": {},
            "atr": {},
            "obv": {},
            "roc": {"period": 5},
            "dmi": {},
            "sar": {},
            "kc": {},
        },
    )
    assert set(res.keys()) == {
        "ma", "macd", "kdj", "rsi", "boll", "wr", "bias",
        "cci", "atr", "obv", "roc", "dmi", "sar", "kc",
    }
    assert set(res["ma"].keys()) == {"ma5", "ma10", "ma20"}
    assert set(res["rsi"].keys()) == {"rsi14"}
    assert res["macd"]["dif"].notna().any()
    assert res["kdj"]["k"].notna().any()
    assert res["atr"]["atr"].notna().any()
    # 输出 Series 索引与输入对齐
    assert list(res["ma"]["ma5"].index) == list(df.index)


def test_calculate_indicators_missing_columns():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError):
        calculate_indicators(df, {"rsi": {}})
