"""技术指标库（stock-sdk TS 算法 → pandas 移植）。

算法严格对照 C:/Users/cccbqn/strategies/stock-sdk/src/indicators/*.ts：

- 舍入：JS ``Math.round`` 语义（round-half-away-from-zero 的 floor(x+0.5) 变体），
  默认 3 位小数，与 TS 的 ``round(value, decimals=3)`` 一致；OBV/ROC/DMI/SAR/KC
  保持裸浮点不舍入（与 TS 一致）。
- null 语义：TS 里窗口含任一 null → 该位输出 null（不更新递推状态）；
  pandas 输入缺失用 NaN 表示，本实现将 NaN 视作 TS 的 null 处理。
- 输出 Series 索引与输入对齐（头部 NaN 填充暖机）。

指标公式均为标准算法：
SMA=简单平均 / EMA=以 SMA 播种的指数平均(alpha=2/(n+1)) / WMA=线性加权平均 /
MACD=DIF(EMA12-EMA26)+DEA(DIF 的 EMA)+柱((DIF-DEA)*2) / BOLL=中轨(SMA)±k*std /
KDJ=RSV 平滑(K/D 初值 50) / RSI=Wilder 平滑 / WR=威廉 / BIAS=乖离率 /
CCI=典型价通道 / ATR=TR 的 Wilder 平滑 / OBV=能量潮累计 / ROC=变动率 /
DMI=+DI/-DI/ADX/ADXR / SAR=抛物线 / KC=EMA±k*ATR。
"""
from __future__ import annotations

import math
from collections import deque
from typing import Optional, Union

import numpy as np
import pandas as pd

__all__ = [
    "calc_sma", "calc_ema", "calc_wma", "calc_ma", "calc_macd", "calc_boll",
    "calc_kdj", "calc_rsi", "calc_wr", "calc_bias", "calc_cci", "calc_atr",
    "calc_obv", "calc_roc", "calc_dmi", "calc_sar", "calc_kc",
    "calculate_indicators", "DEFAULT_DECIMALS",
]

DEFAULT_DECIMALS = 3


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _as_series(data, col: str = "close") -> pd.Series:
    """统一输入为 pd.Series（Series / DataFrame[col] / list / ndarray）。"""
    if isinstance(data, pd.Series):
        return data
    if isinstance(data, pd.DataFrame):
        if col not in data.columns:
            raise ValueError(f"数据缺少列 '{col}'")
        return data[col]
    if isinstance(data, (list, tuple, np.ndarray)):
        return pd.Series(np.asarray(data, dtype=float))
    raise TypeError(f"不支持的数据类型: {type(data)!r}")


def _as_df(data) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    raise TypeError("该指标需要 DataFrame（含 high/low/close/volume 列）")


def _as_period(value: Union[int, float, None], default: int) -> int:
    """周期归一为 int（None→默认；兼容 np.integer）。"""
    if value is None:
        return default
    return int(value)


def _js_round(value: float, decimals: int = DEFAULT_DECIMALS) -> float:
    """JS Math.round 语义的标量舍入：floor(v*10^d + 0.5)/10^d。"""
    factor = 10.0 ** decimals
    return math.floor(value * factor + 0.5) / factor


def _round_arr(arr, decimals: int = DEFAULT_DECIMALS) -> np.ndarray:
    """对 numpy 数组逐元素 JS-Math.round（NaN/Inf 原样保留）。"""
    arr = np.asarray(arr, dtype=float)
    factor = 10.0 ** decimals
    return np.floor(arr * factor + 0.5) / factor


def _round_series(series: pd.Series, decimals: int = DEFAULT_DECIMALS) -> pd.Series:
    return pd.Series(_round_arr(series.to_numpy(dtype=float), decimals), index=series.index)


def _rolling_count_nan_free(values: np.ndarray, period: int) -> np.ndarray:
    """窗口内非 NaN 计数（rolling min_periods=period）。"""
    s = pd.Series(values)
    return (~s.isna()).rolling(period, min_periods=period).sum().to_numpy(dtype=float)


# ---------------------------------------------------------------------------
# MA 族：SMA / EMA / WMA / MA
# ---------------------------------------------------------------------------

def calc_sma(
    data, period: int, decimals: int = DEFAULT_DECIMALS
) -> pd.Series:
    """简单移动平均（TS calcSMA）：窗口内任一 null → null；输出 round。"""
    s = _as_series(data)
    period = _as_period(period, 0)
    if period <= 0:
        return pd.Series(np.nan, index=s.index)
    mean = s.rolling(period, min_periods=period).mean()
    return _round_series(mean, decimals)


def calc_ema(
    data, period: int, decimals: int = DEFAULT_DECIMALS
) -> pd.Series:
    """指数移动平均（TS calcEMA）：前 period-1 根 null，以 SMA 播种，
    之后 ema = alpha*v + (1-alpha)*ema；空值保持上一值；每步输出 round。"""
    s = _as_series(data)
    period = _as_period(period, 0)
    n = len(s)
    out = np.full(n, np.nan)
    if period >= 1:
        arr = s.to_numpy(dtype=float)
        alpha = 2.0 / (period + 1)
        ema: Optional[float] = None
        for i in range(n):
            if i < period - 1:
                continue
            if ema is None:
                window = arr[i - period + 1 : i + 1]
                valid = window[~np.isnan(window)]
                if valid.size == period:
                    ema = float(valid.sum()) / period
                    out[i] = _js_round(ema, decimals)
                continue  # 未集齐种子则保持 null，下一根重试
            v = arr[i]
            if np.isnan(v):
                out[i] = _js_round(ema, decimals)
            else:
                ema = alpha * v + (1.0 - alpha) * ema
                out[i] = _js_round(ema, decimals)
    return pd.Series(out, index=s.index)


def calc_wma(
    data, period: int, decimals: int = DEFAULT_DECIMALS
) -> pd.Series:
    """加权移动平均（TS calcWMA）：权重 1..period；窗口内任一 null → null。"""
    s = _as_series(data)
    period = _as_period(period, 0)
    n = len(s)
    out = np.full(n, np.nan)
    if period >= 1:
        arr = s.to_numpy(dtype=float)
        weights = np.arange(1.0, period + 1.0)
        weight_sum = weights.sum()
        for i in range(period - 1, n):
            window = arr[i - period + 1 : i + 1]
            if np.isnan(window).any():
                continue
            out[i] = _js_round(float((window * weights).sum()) / weight_sum, decimals)
    return pd.Series(out, index=s.index)


def calc_ma(
    data,
    periods: Optional[Union[int, list, tuple]] = None,
    ma_type: str = "sma",
    decimals: int = DEFAULT_DECIMALS,
) -> dict:
    """批量均线（TS calcMA）：返回 {"ma5": Series, ...}。

    ma_type: 'sma' | 'ema' | 'wma'，默认 'sma'；periods 默认 [5,10,20,30,60,120,250]。
    """
    s = _as_series(data)
    if periods is None:
        periods = [5, 10, 20, 30, 60, 120, 250]
    if isinstance(periods, (int, np.integer)):
        periods = [int(periods)]
    fn = {"sma": calc_sma, "ema": calc_ema, "wma": calc_wma}.get(ma_type)
    if fn is None:
        raise ValueError(f"ma_type 必须为 'sma'/'ema'/'wma'，得到 {ma_type!r}")
    return {f"ma{p}": fn(s, int(p), decimals) for p in periods}


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def calc_macd(
    data,
    short: int = 12,
    long: int = 26,
    signal: int = 9,
    decimals: int = DEFAULT_DECIMALS,
) -> dict:
    """MACD（TS calcMACD）：dif = EMA(short)-EMA(long)（已各自 round），
    dea = EMA(dif, signal)，macd = round((dif-dea)*2)。"""
    s = _as_series(data)
    ema_short = calc_ema(s, short, decimals)
    ema_long = calc_ema(s, long, decimals)
    dif_raw = ema_short - ema_long
    dif = _round_series(dif_raw, decimals)
    dea = calc_ema(dif_raw, signal, decimals)
    macd = _round_series((dif_raw - dea) * 2.0, decimals)
    return {"dif": dif, "dea": dea, "macd": macd}


# ---------------------------------------------------------------------------
# BOLL
# ---------------------------------------------------------------------------

def calc_boll(
    data,
    period: int = 20,
    std_dev: float = 2.0,
    decimals: int = DEFAULT_DECIMALS,
) -> dict:
    """布林带（TS calcBOLL）：mid=SMA(period)；std 按 Σ(x-m)² 展开式
    （m 为已 round 的 mid，与 TS 口径一致），clamp 到 0 防负方差；
    bandwidth = round((upper-lower)/mid*100)（upper/lower 用未 round 值）。"""
    s = _as_series(data)
    period = _as_period(period, 20)
    mid = calc_sma(s, period, decimals)
    if period <= 0:
        nan = pd.Series(np.nan, index=s.index)
        return {"mid": nan, "upper": nan, "lower": nan, "bandwidth": nan}
    arr = s.to_numpy(dtype=float)
    sum_win = pd.Series(arr, index=s.index).rolling(period, min_periods=period).sum().to_numpy(dtype=float)
    sq_win = pd.Series(arr * arr, index=s.index).rolling(period, min_periods=period).sum().to_numpy(dtype=float)
    m = mid.to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        var = sq_win - 2.0 * m * sum_win + period * m * m
        std = np.sqrt(np.maximum(0.0, var) / period)
        std = np.where(np.isnan(m), np.nan, std)
        upper_raw = m + std_dev * std
        lower_raw = m - std_dev * std
        bandwidth = np.where(
            (m != 0) & ~np.isnan(m),
            _round_arr((upper_raw - lower_raw) / m * 100.0, decimals),
            np.nan,
        )
    return {
        "mid": mid,
        "upper": _round_series(pd.Series(upper_raw, index=s.index), decimals),
        "lower": _round_series(pd.Series(lower_raw, index=s.index), decimals),
        "bandwidth": pd.Series(bandwidth, index=s.index),
    }


# ---------------------------------------------------------------------------
# KDJ
# ---------------------------------------------------------------------------

def calc_kdj(
    df,
    period: int = 9,
    k_period: int = 3,
    d_period: int = 3,
    decimals: int = DEFAULT_DECIMALS,
) -> dict:
    """KDJ（TS calcKDJ）：单调队列滑动 N 日高低点；K/D 初值 50，
    窗口内 high/low 任一 null 或 highN==lowN → 输出 null 且不更新状态。"""
    frame = _as_df(df)
    n = len(frame)
    k_out = np.full(n, np.nan)
    d_out = np.full(n, np.nan)
    j_out = np.full(n, np.nan)
    if n == 0 or period <= 0:
        return {"k": pd.Series(k_out, index=frame.index),
                "d": pd.Series(d_out, index=frame.index),
                "j": pd.Series(j_out, index=frame.index)}
    high = frame["high"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    k = 50.0
    d = 50.0
    max_idx = deque()
    min_idx = deque()
    invalid_in_window = 0
    for i in range(n):
        h, l = high[i], low[i]
        if np.isnan(h) or np.isnan(l):
            invalid_in_window += 1
        else:
            while max_idx and high[max_idx[-1]] <= h:
                max_idx.pop()
            max_idx.append(i)
            while min_idx and low[min_idx[-1]] >= l:
                min_idx.pop()
            min_idx.append(i)
        if i >= period:
            gh, gl = high[i - period], low[i - period]
            if np.isnan(gh) or np.isnan(gl):
                invalid_in_window -= 1
        window_start = i - period + 1
        while max_idx and max_idx[0] < window_start:
            max_idx.popleft()
        while min_idx and min_idx[0] < window_start:
            min_idx.popleft()
        if i < period - 1:
            continue
        high_n = high[max_idx[0]] if max_idx else -np.inf
        low_n = low[min_idx[0]] if min_idx else np.inf
        c = close[i]
        if invalid_in_window > 0 or np.isnan(c) or high_n == low_n:
            continue
        rsv = (c - low_n) / (high_n - low_n) * 100.0
        k = (k_period - 1) / k_period * k + (1.0 / k_period) * rsv
        d = (d_period - 1) / d_period * d + (1.0 / d_period) * k
        j = 3.0 * k - 2.0 * d
        k_out[i] = _js_round(k, decimals)
        d_out[i] = _js_round(d, decimals)
        j_out[i] = _js_round(j, decimals)
    return {
        "k": pd.Series(k_out, index=frame.index),
        "d": pd.Series(d_out, index=frame.index),
        "j": pd.Series(j_out, index=frame.index),
    }

# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def calc_rsi(
    data,
    periods: Optional[Union[int, list, tuple]] = None,
    decimals: int = DEFAULT_DECIMALS,
) -> dict:
    """RSI（TS calcRSI，Wilder 平滑）：种子窗口取 changes[1..period] 简单平均，
    avgLoss==0 → 100，avgGain==0 → 0，否则 round(100-100/(1+RS))。
    返回 {"rsi6": Series, ...}；periods 默认 [6,12,24]。"""
    s = _as_series(data)
    if periods is None:
        periods = [6, 12, 24]
    if isinstance(periods, (int, np.integer)):
        periods = [int(periods)]
    arr = s.to_numpy(dtype=float)
    n = len(arr)
    changes = np.full(n, np.nan)
    for i in range(1, n):
        if not np.isnan(arr[i]) and not np.isnan(arr[i - 1]):
            changes[i] = arr[i] - arr[i - 1]
    out: dict = {}
    for period in periods:
        period = int(period)
        rsi = np.full(n, np.nan)
        if period < 1:
            out[f"rsi{period}"] = pd.Series(rsi, index=s.index)
            continue
        avg_gain = 0.0
        avg_loss = 0.0
        for i in range(n):
            if i < period:
                c = changes[i]
                if not np.isnan(c):
                    if c > 0:
                        avg_gain += c
                    else:
                        avg_loss += abs(c)
                continue
            if i == period:
                c = changes[i]
                if not np.isnan(c):
                    if c > 0:
                        avg_gain += c
                    else:
                        avg_loss += abs(c)
                avg_gain /= period
                avg_loss /= period
            else:
                c = changes[i]
                if np.isnan(c):
                    c = 0.0
                gain = c if c > 0 else 0.0
                loss = -c if c < 0 else 0.0
                avg_gain = (avg_gain * (period - 1) + gain) / period
                avg_loss = (avg_loss * (period - 1) + loss) / period
            if avg_loss == 0:
                rsi[i] = 100.0
            elif avg_gain == 0:
                rsi[i] = 0.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = _js_round(100.0 - 100.0 / (1.0 + rs), decimals)
        out[f"rsi{period}"] = pd.Series(rsi, index=s.index)
    return out


# ---------------------------------------------------------------------------
# WR / BIAS / CCI
# ---------------------------------------------------------------------------

def calc_wr(
    df,
    periods: Optional[Union[int, list, tuple]] = None,
    decimals: int = DEFAULT_DECIMALS,
) -> dict:
    """威廉指标 WR（TS calcWR）：wr=(highN-close)/(highN-lowN)*100；
    窗口含 null / close null / highN==lowN → null。返回 {"wr6": Series, ...}。"""
    frame = _as_df(df)
    if periods is None:
        periods = [6, 10]
    if isinstance(periods, (int, np.integer)):
        periods = [int(periods)]
    n = len(frame)
    high = frame["high"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    out: dict = {}
    for period in periods:
        period = int(period)
        wr = np.full(n, np.nan)
        if period < 1:
            out[f"wr{period}"] = pd.Series(wr, index=frame.index)
            continue
        h_clean = np.where(np.isnan(high), -np.inf, high)
        l_clean = np.where(np.isnan(low), np.inf, low)
        hmax = pd.Series(h_clean, index=frame.index).rolling(period, min_periods=period).max().to_numpy(dtype=float)
        lmin = pd.Series(l_clean, index=frame.index).rolling(period, min_periods=period).min().to_numpy(dtype=float)
        hcnt = _rolling_count_nan_free(high, period)
        lcnt = _rolling_count_nan_free(low, period)
        valid = (hcnt == period) & (lcnt == period) & ~np.isnan(close)
        with np.errstate(invalid="ignore", divide="ignore"):
            denom = hmax - lmin
            val = (hmax - close) / denom * 100.0
            wr = np.where(valid & (denom != 0), _round_arr(val, decimals), np.nan)
        out[f"wr{period}"] = pd.Series(wr, index=frame.index)
    return out


def calc_bias(
    data,
    periods: Optional[Union[int, list, tuple]] = None,
    decimals: int = DEFAULT_DECIMALS,
) -> dict:
    """乖离率 BIAS（TS calcBIAS）：bias=(close-ma)/ma*100，ma 为已 round 的 SMA；
    close/ma null 或 ma==0 → null。返回 {"bias6": Series, ...}。"""
    s = _as_series(data)
    if periods is None:
        periods = [6, 12, 24]
    if isinstance(periods, (int, np.integer)):
        periods = [int(periods)]
    arr = s.to_numpy(dtype=float)
    n = len(arr)
    out: dict = {}
    for period in periods:
        period = int(period)
        bias = np.full(n, np.nan)
        if period >= 1:
            ma = calc_sma(s, period, decimals).to_numpy(dtype=float)
            valid = ~np.isnan(arr) & ~np.isnan(ma) & (ma != 0)
            with np.errstate(invalid="ignore", divide="ignore"):
                bias[valid] = _round_arr((arr[valid] - ma[valid]) / ma[valid] * 100.0, decimals)
        out[f"bias{period}"] = pd.Series(bias, index=s.index)
    return out


def calc_cci(
    df, period: int = 14, decimals: int = DEFAULT_DECIMALS
) -> pd.Series:
    """商品通道指数 CCI（TS calcCCI）：TP=(h+l+c)/3，MA=TP 的 SMA，
    MD=平均绝对偏差，cci=(TP-MA)/(0.015*MD)；md==0 → 0。"""
    frame = _as_df(df)
    period = _as_period(period, 14)
    n = len(frame)
    cci = np.full(n, np.nan)
    if period < 1:
        return pd.Series(cci, index=frame.index)
    high = frame["high"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    tp = np.full(n, np.nan)
    for i in range(n):
        h, l, c = high[i], low[i], close[i]
        if np.isnan(h) or np.isnan(l) or np.isnan(c):
            continue
        tp[i] = (h + l + c) / 3.0
    for i in range(period - 1, n):
        window = tp[i - period + 1 : i + 1]
        valid = window[~np.isnan(window)]
        if valid.size != period or np.isnan(tp[i]):
            continue
        ma = float(valid.sum()) / period
        md = float(np.abs(valid - ma).sum()) / period
        if md == 0:
            cci[i] = 0.0
        else:
            cci[i] = _js_round((tp[i] - ma) / (0.015 * md), decimals)
    return pd.Series(cci, index=frame.index)


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def calc_atr(
    df, period: int = 14, decimals: int = DEFAULT_DECIMALS
) -> dict:
    """平均真实波幅 ATR（TS calcATR）：TR=max(H-L,|H-昨收|,|L-昨收|)，
    首根 TR=H-L；ATR 以近 period 根 TR 简单平均播种，之后 Wilder 平滑；
    tr null 时保持上一 ATR；非法周期 → ATR 全 null（TR 仍计算）。
    返回 {"tr": Series, "atr": Series}。"""
    frame = _as_df(df)
    period = _as_period(period, 14)
    n = len(frame)
    high = frame["high"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    tr = np.full(n, np.nan)
    for i in range(n):
        h, l, c = high[i], low[i], close[i]
        if np.isnan(h) or np.isnan(l) or np.isnan(c):
            continue
        if i == 0:
            tr[i] = h - l
        else:
            pc = close[i - 1]
            if np.isnan(pc):
                tr[i] = h - l
            else:
                hl = h - l
                hpc = abs(h - pc)
                lpc = abs(l - pc)
                tr[i] = max(hl, hpc, lpc)
    valid_period = (
        isinstance(period, (int, np.integer)) and not isinstance(period, bool) and period >= 1
    )
    atr = np.full(n, np.nan)
    if valid_period:
        atr_val: Optional[float] = None
        for i in range(n):
            if i < period - 1:
                continue
            if atr_val is None:
                window = tr[i - period + 1 : i + 1]
                valid = window[~np.isnan(window)]
                if valid.size == period:
                    atr_val = float(valid.sum()) / period
            elif not np.isnan(tr[i]):
                atr_val = (atr_val * (period - 1) + tr[i]) / period
            if atr_val is not None:
                atr[i] = atr_val
    return {
        "tr": pd.Series(_round_arr(tr, decimals), index=frame.index),
        "atr": pd.Series(_round_arr(atr, decimals), index=frame.index),
    }


# ---------------------------------------------------------------------------
# OBV / ROC
# ---------------------------------------------------------------------------

def calc_obv(df, ma_period: Optional[int] = None) -> dict:
    """能量潮 OBV（TS calcOBV）：首根 OBV=volume（缺失→0），
    涨加/跌减/平不变；任一根 close/volume null → 该位 null（累计值不变）。
    ma_period>0 时计算 OBV 均线（滑窗均值，不 round）。
    返回 {"obv": Series, "obv_ma": Series}。"""
    frame = _as_df(df)
    n = len(frame)
    close = frame["close"].to_numpy(dtype=float)
    volume = frame["volume"].to_numpy(dtype=float)
    obv = np.full(n, np.nan)
    if n > 0:
        obv[0] = volume[0] if not pd.isna(volume[0]) else 0.0
        obv_val = obv[0]
        for i in range(1, n):
            cc, pc, vv = close[i], close[i - 1], volume[i]
            if pd.isna(cc) or pd.isna(pc) or pd.isna(vv):
                obv[i] = np.nan
                continue
            if cc > pc:
                obv_val += vv
            elif cc < pc:
                obv_val -= vv
            obv[i] = obv_val
    obv_ma = np.full(n, np.nan)
    if ma_period is not None and ma_period > 0:
        s = pd.Series(obv, index=frame.index)
        cnt = (~s.isna()).rolling(ma_period, min_periods=ma_period).sum().to_numpy(dtype=float)
        sm = s.rolling(ma_period, min_periods=ma_period).sum().to_numpy(dtype=float)
        obv_ma = np.where(cnt == ma_period, sm / ma_period, np.nan)
    return {
        "obv": pd.Series(obv, index=frame.index),
        "obv_ma": pd.Series(obv_ma, index=frame.index),
    }


def calc_roc(df, period: int = 12, signal_period: Optional[int] = None) -> dict:
    """变动率 ROC（TS calcROC）：roc=(close-close[N日前])/close[N日前]*100，
    prev==0 → null；signal 为 roc 的滑窗均线（不 round）。
    返回 {"roc": Series, "signal": Series}。"""
    frame = _as_df(df)
    period = _as_period(period, 12)
    n = len(frame)
    close = frame["close"].to_numpy(dtype=float)
    roc = np.full(n, np.nan)
    for i in range(period, n):
        cur, prev = close[i], close[i - period]
        if np.isnan(cur) or np.isnan(prev) or prev == 0:
            continue
        roc[i] = (cur - prev) / prev * 100.0
    signal = np.full(n, np.nan)
    if signal_period is not None and signal_period > 0:
        s = pd.Series(roc, index=frame.index)
        cnt = (~s.isna()).rolling(signal_period, min_periods=signal_period).sum().to_numpy(dtype=float)
        sm = s.rolling(signal_period, min_periods=signal_period).sum().to_numpy(dtype=float)
        signal = np.where(cnt == signal_period, sm / signal_period, np.nan)
    return {
        "roc": pd.Series(roc, index=frame.index),
        "signal": pd.Series(signal, index=frame.index),
    }

# ---------------------------------------------------------------------------
# DMI
# ---------------------------------------------------------------------------

def calc_dmi(
    df, period: int = 14, adx_period: Optional[int] = None
) -> dict:
    """DMI/ADX（TS calcDMI）：+DM/-DM/TR 逐根；Wilder 平滑得 +DI/-DI 与 DX；
    ADX 以 adxPeriod 个真实 DX 简单平均播种后 Wilder 平滑；ADXR 为 ADX 的
    滞后平均。pdi/mdi 从 i>=period 起有效；不做舍入。
    返回 {"pdi","mdi","adx","adxr"}。"""
    frame = _as_df(df)
    period = _as_period(period, 14)
    if adx_period is None:
        adx_period = period
    adx_period = int(adx_period)
    n = len(frame)
    pdi = np.full(n, np.nan)
    mdi = np.full(n, np.nan)
    adx = np.full(n, np.nan)
    adxr = np.full(n, np.nan)
    if n >= 2 and period >= 1 and adx_period >= 1:
        high = frame["high"].to_numpy(dtype=float)
        low = frame["low"].to_numpy(dtype=float)
        close = frame["close"].to_numpy(dtype=float)
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        tr = np.zeros(n)
        for i in range(1, n):
            h, l, c = high[i], low[i], close[i]
            ph, pl, pc = high[i - 1], low[i - 1], close[i - 1]
            if np.isnan(h) or np.isnan(l) or np.isnan(c) or np.isnan(ph) or np.isnan(pl) or np.isnan(pc):
                continue
            hl = h - l
            hpc = abs(h - pc)
            lpc = abs(l - pc)
            tr[i] = max(hl, hpc, lpc)
            up_move = h - ph
            down_move = pl - l
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
        s_tr = 0.0
        s_plus = 0.0
        s_minus = 0.0
        dx = np.zeros(n)
        for i in range(1, n):
            if i < period:
                s_tr += tr[i]
                s_plus += plus_dm[i]
                s_minus += minus_dm[i]
                continue
            if i == period:
                s_tr += tr[i]
                s_plus += plus_dm[i]
                s_minus += minus_dm[i]
            else:
                s_tr = s_tr - s_tr / period + tr[i]
                s_plus = s_plus - s_plus / period + plus_dm[i]
                s_minus = s_minus - s_minus / period + minus_dm[i]
            p = s_plus / s_tr * 100.0 if s_tr > 0 else 0.0
            m = s_minus / s_tr * 100.0 if s_tr > 0 else 0.0
            pdi[i] = p
            mdi[i] = m
            di_sum = p + m
            dx[i] = abs(p - m) / di_sum * 100.0 if di_sum > 0 else 0.0
        seed_index = period + adx_period - 1
        adx_sum = 0.0
        prev_adx = 0.0
        for i in range(period, n):
            if i < seed_index:
                adx_sum += dx[i]
                continue
            if i == seed_index:
                adx_sum += dx[i]
                prev_adx = adx_sum / adx_period
                adx[i] = prev_adx
            else:
                prev_adx = (prev_adx * (adx_period - 1) + dx[i]) / adx_period
                adx[i] = prev_adx
        for i in range(seed_index + adx_period, n):
            cur = adx[i]
            prev = adx[i - adx_period]
            if not np.isnan(cur) and not np.isnan(prev):
                adxr[i] = (cur + prev) / 2.0
    return {
        "pdi": pd.Series(pdi, index=frame.index),
        "mdi": pd.Series(mdi, index=frame.index),
        "adx": pd.Series(adx, index=frame.index),
        "adxr": pd.Series(adxr, index=frame.index),
    }


# ---------------------------------------------------------------------------
# SAR
# ---------------------------------------------------------------------------

def calc_sar(
    df,
    af_start: float = 0.02,
    af_increment: float = 0.02,
    af_max: float = 0.2,
) -> dict:
    """抛物线 SAR（TS calcSAR）：跳过前导无效 bar 播种（seed），以
    seed 的 high/low 与初始趋势初始化；SAR 更新 + 加速因子递增，
    反转时重置 af 并取 EP。种子前输出 null；不做舍入。
    返回 {"sar","trend","ep","af"}（trend: 1 上升 / -1 下降）。"""
    frame = _as_df(df)
    n = len(frame)
    sar = np.full(n, np.nan)
    trend = np.full(n, np.nan)
    ep = np.full(n, np.nan)
    af = np.full(n, np.nan)
    if n >= 2:
        high = frame["high"].to_numpy(dtype=float)
        low = frame["low"].to_numpy(dtype=float)
        close = frame["close"].to_numpy(dtype=float)
        seed = 0
        while seed < n and (np.isnan(high[seed]) or np.isnan(low[seed])):
            seed += 1
        if seed < n - 1:
            t = 1
            accel = af_start
            ep_val = high[seed]
            sar_val = low[seed]
            if (
                not np.isnan(close[seed])
                and not np.isnan(close[seed + 1])
                and close[seed + 1] < close[seed]
            ):
                t = -1
                ep_val = low[seed]
                sar_val = high[seed]
            for i in range(seed + 1, n):
                h, l = high[i], low[i]
                ph, pl = high[i - 1], low[i - 1]
                if np.isnan(h) or np.isnan(l) or np.isnan(ph) or np.isnan(pl):
                    continue
                new_sar = sar_val + accel * (ep_val - sar_val)
                if t == 1:
                    lookback = max(seed, i - 2)
                    prev2_low = low[lookback]
                    if np.isnan(prev2_low):
                        prev2_low = pl
                    new_sar = min(new_sar, pl, prev2_low)
                    if l < new_sar:
                        t = -1
                        new_sar = ep_val
                        ep_val = l
                        accel = af_start
                    elif h > ep_val:
                        ep_val = h
                        accel = min(accel + af_increment, af_max)
                else:
                    lookback = max(seed, i - 2)
                    prev2_high = high[lookback]
                    if np.isnan(prev2_high):
                        prev2_high = ph
                    new_sar = max(new_sar, ph, prev2_high)
                    if h > new_sar:
                        t = 1
                        new_sar = ep_val
                        ep_val = h
                        accel = af_start
                    elif l < ep_val:
                        ep_val = l
                        accel = min(accel + af_increment, af_max)
                sar_val = new_sar
                sar[i] = sar_val
                trend[i] = t
                ep[i] = ep_val
                af[i] = accel
    return {
        "sar": pd.Series(sar, index=frame.index),
        "trend": pd.Series(trend, index=frame.index),
        "ep": pd.Series(ep, index=frame.index),
        "af": pd.Series(af, index=frame.index),
    }


# ---------------------------------------------------------------------------
# KC
# ---------------------------------------------------------------------------

def calc_kc(
    df,
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: float = 2.0,
) -> dict:
    """肯特纳通道 KC（TS calcKC）：mid=EMA(close, ema_period)，
    upper/lower = mid ± multiplier*ATR(atr_period)，width=(upper-lower)/mid*100；
    不做舍入。返回 {"mid","upper","lower","width"}。"""
    frame = _as_df(df)
    mid = calc_ema(frame["close"], ema_period)
    atr_s = calc_atr(frame, atr_period)["atr"]
    m = mid.to_numpy(dtype=float)
    a = atr_s.to_numpy(dtype=float)
    n = len(m)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    width = np.full(n, np.nan)
    valid = ~np.isnan(m) & ~np.isnan(a)
    with np.errstate(invalid="ignore", divide="ignore"):
        u = m + multiplier * a
        l = m - multiplier * a
        upper = np.where(valid, u, np.nan)
        lower = np.where(valid, l, np.nan)
        width = np.where(valid & (m > 0), (u - l) / m * 100.0, np.nan)
    return {
        "mid": mid,
        "upper": pd.Series(upper, index=frame.index),
        "lower": pd.Series(lower, index=frame.index),
        "width": pd.Series(width, index=frame.index),
    }


# ---------------------------------------------------------------------------
# 组合入口
# ---------------------------------------------------------------------------

_PERIODS_PLURAL_KEYS = ("ma", "rsi", "wr", "bias")


def _normalize_options(key: str, opts) -> Optional[dict]:
    """归一化单指标配置（对照 registry.normalizeIndicatorOptions）：
    True → {}；list → {periods}（仅 periods 复数指标）；{period: n} →
    {periods: [n]}；False/None → 跳过。另处理 macd 的 fast/slow 别名
    与 ma 的 type→ma_type。"""
    if opts is None or opts is False:
        return None
    if opts is True:
        return {}
    if isinstance(opts, (list, tuple, np.ndarray)):
        if key not in _PERIODS_PLURAL_KEYS:
            raise ValueError(f"指标 '{key}' 不支持数组简写，请传 dict 配置")
        return {"periods": [int(p) for p in opts]}
    if isinstance(opts, dict):
        o = dict(opts)
        if key in _PERIODS_PLURAL_KEYS:
            if "periods" not in o and isinstance(o.get("period"), (int, float, np.integer)):
                o["periods"] = [int(o.pop("period"))]
        if key == "macd":
            if "fast" in o and "short" not in o:
                o["short"] = o.pop("fast")
            if "slow" in o and "long" not in o:
                o["long"] = o.pop("slow")
        if key == "ma" and "type" in o:
            o["ma_type"] = o.pop("type")
        return o
    raise TypeError(f"指标 '{key}' 配置格式不支持: {type(opts)!r}")


def calculate_indicators(df: pd.DataFrame, indicators: dict) -> dict:
    """为 K 线 DataFrame 批量计算技术指标（对照 addIndicators + registry）。

    参数
    ----
    df : pd.DataFrame，需含 open/high/low/close/volume 列（open 暂未使用）。
    indicators : dict，键为指标名，值为配置（True/{} → 默认参数）：
        {"ma": [5,10,20], "macd": {"fast":12,"slow":26,"signal":9}, "kdj": {},
         "rsi": {"period":14}, "boll": {}, "atr": {}, ...}

    返回
    ----
    {"ma": {"ma5": Series,...}, "macd": {"dif","dea","macd": Series}, ...}
    各 Series 索引与 df 对齐。
    """
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    missing = {"high", "low", "close", "volume"} - set(df.columns)
    if missing:
        raise ValueError(f"df 缺少必需列: {sorted(missing)}")
    result: dict = {}
    for key, raw in indicators.items():
        opts = _normalize_options(key, raw)
        if opts is None:
            continue
        if key == "ma":
            result["ma"] = calc_ma(df["close"], **opts)
        elif key == "macd":
            result["macd"] = calc_macd(df["close"], **opts)
        elif key == "boll":
            result["boll"] = calc_boll(df["close"], **opts)
        elif key == "kdj":
            result["kdj"] = calc_kdj(df, **opts)
        elif key == "rsi":
            result["rsi"] = calc_rsi(df["close"], **opts)
        elif key == "wr":
            result["wr"] = calc_wr(df, **opts)
        elif key == "bias":
            result["bias"] = calc_bias(df["close"], **opts)
        elif key == "cci":
            result["cci"] = calc_cci(df, **opts)
        elif key == "atr":
            result["atr"] = calc_atr(df, **opts)
        elif key == "obv":
            result["obv"] = calc_obv(df, **opts)
        elif key == "roc":
            result["roc"] = calc_roc(df, **opts)
        elif key == "dmi":
            result["dmi"] = calc_dmi(df, **opts)
        elif key == "sar":
            result["sar"] = calc_sar(df, **opts)
        elif key == "kc":
            result["kc"] = calc_kc(df, **opts)
        else:
            raise ValueError(f"未知指标: {key!r}（可选: ma/macd/boll/kdj/rsi/wr/bias/cci/atr/obv/roc/dmi/sar/kc）")
    return result
