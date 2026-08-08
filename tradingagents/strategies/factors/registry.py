"""精选因子库：30 个 Alpha 因子 + 注册表。

**数据形态（二选一，推荐第一种）**：
- 面板 dict：``{"close": df, "high": df, "low": df, "vol": df, ...}``，
  每个值都是**同形宽表** ``index=日期, columns=股票代码``；
- 或单个 DataFrame（视为 ``{"close": df}``，即 df 是收盘价宽表）。

``compute_factor(data, name)`` 返回与输入同形的宽表（index=日期, columns=股票代码），
warmup / 缺失数据处为 NaN。**推荐 index=日期、columns=股票代码** 形态，
以便与截面算子（rank/zscore/scale，按行）和时序算子（ts_*，按列）配合。

**因子函数签名**：``f(df: pd.DataFrame, panel: Mapping[str, pd.DataFrame] | None = None)``，
其中 ``df`` 是主序列（close）宽表，``panel`` 可选（提供 high/low/vol/pe_ttm 等
额外字段）。缺额外字段的因子（如 ATR 缺 high/low、基本面因子缺 pe_ttm/roe）返回
**全 NaN 占位**而非抛异常——docstring 均注明。

类别：momentum（动量）/ mean_reversion（均值回复）/ volatility（波动）/
volume_price（量价）/ fundamental（基本面）。

因子出处标注：qlib158 / alpha101（Kakushadze）/ gtja191 / academic。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from .operators import (
    delta,
    rank,
    safe_div,
    signed_power,
    ts_argmax,
    ts_corr,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std,
)


def _get(panel, field):
    """取面板字段宽表；缺失返回 None。"""
    if panel is not None and field in panel and panel[field] is not None:
        return panel[field]
    return None


def _missing_like(df: pd.DataFrame) -> pd.DataFrame:
    """与 df 同形的全 NaN 占位表。"""
    return pd.DataFrame(np.nan, index=df.index, columns=df.columns)


def _ones_like(df: pd.DataFrame) -> pd.DataFrame:
    return df * 0.0 + 1.0


@dataclass(frozen=True)
class Factor:
    """因子元数据 + 计算函数。"""

    name: str
    display_name: str
    category: str  # momentum|mean_reversion|volatility|volume_price|fundamental
    description: str
    func: Callable[..., pd.DataFrame] = field(repr=False)
    requires: tuple[str, ...] = ("close",)


# ==================== 动量类（8） ====================

def mom_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """MOM_20：20 日动量 close_t/close_{t-20} - 1（academic / qlib158 roc20）。"""
    return safe_div(df, df.shift(20)) - 1.0


def roc_10(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """ROC_10：10 日变化率 close_t/close_{t-10} - 1（qlib158 roc10）。"""
    return safe_div(df, df.shift(10)) - 1.0


def rsi_14(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """RSI_14：14 日相对强弱（Wilder 平滑，0-100；全涨→100，全跌→0）。

    纯上升序列接近 100。来源：gtja191 RSI。
    """
    d = df.diff()
    gain = d.clip(lower=0)
    loss = (-d).clip(lower=0)
    ag = gain.ewm(alpha=1.0 / 14, min_periods=14).mean()
    al = loss.ewm(alpha=1.0 / 14, min_periods=14).mean()
    denom = (ag + al).replace(0, np.nan)
    return 100.0 * ag / denom


def alpha_001(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """ALPHA_001：rank(ts_argmax(SignedPower(cond?std20(ret):close, 2), 5)) - 0.5。

    收益与波动条件动量（alpha101 #1，Kakushadze 2015）。
    """
    ret = df.pct_change()
    cond = (ret < 0).astype(float)
    x = ts_std(ret, 20) * cond + df * (1.0 - cond)
    return rank(ts_argmax(signed_power(x, 2.0), 5)) - 0.5


def ts_rank_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """TS_RANK_20：20 日内收盘价百分位（动量强弱，>0.5 强势）。华泰/学术动量。"""
    return ts_rank(df, 20)


def mom_accel(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """MOM_ACCEL：动量加速度 = delta(MOM_20, 5)（动量二阶变化）。academic。"""
    return delta(safe_div(df, df.shift(20)) - 1.0, 5)


def ma_cross_20_60(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """MA_CROSS_20_60：均线乖离 ma20/ma60 - 1（中长期趋势强度）。gtja191 均线类。"""
    return safe_div(ts_mean(df, 20), ts_mean(df, 60)) - 1.0


def max_20_ret(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """MAX_20_RET：close/ts_max(close,20) - 1（距 20 日高点回落幅度）。gtja191 Max 类。"""
    return safe_div(df, ts_max(df, 20)) - 1.0


# ==================== 均值回复类（5） ====================

def bias_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """BIAS_20：乖离率 close/ma20 - 1（价格偏离均线程度）。gtja191 BIAS。"""
    return safe_div(df, ts_mean(df, 20)) - 1.0


def boll_dist(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """BOLL_DIST：布林带内相对位置 (close-mid)/(4*std20)，±0.5 为带宽边界。gtja191。"""
    mid = ts_mean(df, 20)
    std = ts_std(df, 20)
    return safe_div(df - mid, std * 4.0)


def rev_ts_rank_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """REV_TS_RANK_20：20 日反转 0.5 - ts_rank(close, 20)（涨幅大→负，超买回落）。gtja191 反转。"""
    return 0.5 - ts_rank(df, 20)


def rsv_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """RSV_20：KDJ 未成熟随机值 (close - ts_min(low,20)) / (ts_max(high,20)-ts_min(low,20))。

    需 panel["high"]/panel["low"]，缺失→全 NaN。qlib158 rsv20。
    """
    h = _get(panel, "high")
    lo = _get(panel, "low")
    if h is None or lo is None:
        return _missing_like(df)
    return safe_div(df - ts_min(lo, 20), ts_max(h, 20) - ts_min(lo, 20))


def psy_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """PSY_20：心理线——20 日内上涨天数占比（超买超卖，>0.7 超买）。gtja191 PSY。"""
    up = (df.diff() > 0).astype(float)
    return ts_mean(up, 20)


# ==================== 波动类（5） ====================

def vol_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """VOL_20：20 日收益率样本标准差（波动率，per column）。academic。"""
    return ts_std(df.pct_change(), 20)


def atr_14(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """ATR_14：14 日平均真实波幅 / close（ATR%，真波幅=max(H-L,|H-pc|,|L-pc|)）。

    需 panel["high"]/panel["low"]，缺失→全 NaN。gtja191 ATR。
    """
    h = _get(panel, "high")
    lo = _get(panel, "low")
    if h is None or lo is None:
        return _missing_like(df)
    prev = df.shift()
    a = h - lo
    b = (h - prev).abs()
    c = (lo - prev).abs()
    tr = a.where(a >= b, b)
    tr = tr.where(tr >= c, c)
    return safe_div(ts_mean(tr, 14), df)


def vol_chg_5(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """VOL_CHG_5：波动率 5 日变化 delta(std20(ret), 5)（波动率扩张/收缩）。gtja191 STD 类。"""
    return delta(ts_std(df.pct_change(), 20), 5)


def vol_ratio(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """VOL_RATIO：短期/长期波动比 std5(ret)/std20(ret)（>1 波动放大）。academic。"""
    ret = df.pct_change()
    return safe_div(ts_std(ret, 5), ts_std(ret, 20))


def range_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """RANGE_20：20 日振幅 (ts_max(high,20)-ts_min(low,20))/ma20。需 high/low。gtja191。"""
    h = _get(panel, "high")
    lo = _get(panel, "low")
    if h is None or lo is None:
        return _missing_like(df)
    return safe_div(ts_max(h, 20) - ts_min(lo, 20), ts_mean(df, 20))


# ==================== 量价类（6） ====================

def obv_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """OBV_20：OBV 20 日变化 / 20 日均量（量能方向，>0 资金流入）。需 panel["vol"]。academic OBV。"""
    vol = _get(panel, "vol")
    if vol is None:
        return _missing_like(df)
    obv = (np.sign(df.diff()).fillna(0) * vol).cumsum()
    return safe_div(delta(obv, 20), ts_mean(vol, 20))


def vr_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """VR_20：20 日成交量比率（上涨日量/下跌日量，>1 多头活跃）。gtja191 VR。需 vol。"""
    vol = _get(panel, "vol")
    if vol is None:
        return _missing_like(df)
    up = (df.diff() > 0).astype(float)
    down = (df.diff() < 0).astype(float)
    up_sum = (up * vol).rolling(20, min_periods=20).sum()
    down_sum = (down * vol).rolling(20, min_periods=20).sum()
    return safe_div(up_sum, down_sum)


def vol_ratio_5(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """VOL_RATIO_5：量比 vol/ma5(vol)（当日量能相对近 5 日，>1 放量）。gtja191 量比。需 vol。"""
    vol = _get(panel, "vol")
    if vol is None:
        return _missing_like(df)
    return safe_div(vol, ts_mean(vol, 5))


def corr_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """CORR_20：close 与 vol 的 20 日滚动相关（量价共振度）。qlib158 corr20。需 vol。"""
    vol = _get(panel, "vol")
    if vol is None:
        return _missing_like(df)
    return ts_corr(df, vol, 20)


def vma_20(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """VMA_20：成交量动量 vol/ma20(vol) - 1（量能趋势）。qlib158 vma20。需 vol。"""
    vol = _get(panel, "vol")
    if vol is None:
        return _missing_like(df)
    return safe_div(vol, ts_mean(vol, 20)) - 1.0


def vsump_10(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """VSUMP_10：10 日上涨日成交量占比（量能质量）。qlib158 vsump10。需 vol。"""
    vol = _get(panel, "vol")
    if vol is None:
        return _missing_like(df)
    up = (df.diff() > 0).astype(float)
    up_sum = (up * vol).rolling(10, min_periods=10).sum()
    vol_sum = vol.rolling(10, min_periods=10).sum()
    return safe_div(up_sum, vol_sum)


# ==================== 基本面类（6，需外部数据） ====================

def roe_chg_q(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """ROE_CHG_Q：ROE 环比变化（delta 1 期）。

    需 panel["roe"]（财务序列，如 fina_indicator.roe 转宽表）；缺失→全 NaN 占位。
    academic 基本面动量。
    """
    roe = _get(panel, "roe")
    if roe is None:
        return _missing_like(df)
    return delta(roe, 1)


def pe_pct_250(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """PE_PCT_250：pe_ttm 250 日分位（0-1，低估=低分位）。

    需 panel["pe_ttm"]（如 daily_basic.pe_ttm 转宽表）；缺失→全 NaN 占位。academic。
    """
    pe = _get(panel, "pe_ttm")
    if pe is None:
        return _missing_like(df)
    return ts_rank(pe, 250)


def ep_ttm(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """EP_TTM：盈利收益率 1/pe_ttm（高=便宜）。

    需 panel["pe_ttm"]（单日快照即可，pe<=0 → NaN）；缺失→全 NaN 占位。
    academic 价值因子。
    """
    pe = _get(panel, "pe_ttm")
    if pe is None:
        return _missing_like(df)
    return safe_div(_ones_like(df), pe)


def bp(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """BP：账面市值比 1/pb（价值因子，高=便宜）。

    需 panel["pb"]（如 daily_basic.pb 转宽表）；缺失→全 NaN 占位。academic。
    """
    pb = _get(panel, "pb")
    if pb is None:
        return _missing_like(df)
    return safe_div(_ones_like(df), pb)


def peg(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """PEG：市盈率/盈利增速 pe_ttm/profit_yoy（<1 成长性低估）。

    需 panel["pe_ttm"] 与 panel["profit_yoy"]（如 fina_indicator.netprofit_yoy 转宽表）；
    缺任一→全 NaN 占位。gtja191 / academic 成长价值。
    """
    pe = _get(panel, "pe_ttm")
    yoy = _get(panel, "profit_yoy")
    if pe is None or yoy is None:
        return _missing_like(df)
    return safe_div(pe, yoy)


def dv_ttm(df: pd.DataFrame, panel=None) -> pd.DataFrame:
    """DV_TTM：股息率（原样透传，高=高分红）。

    需 panel["dv_ttm"]（如 daily_basic.dv_ttm 转宽表）；缺失→全 NaN 占位。academic。
    """
    dv = _get(panel, "dv_ttm")
    if dv is None:
        return _missing_like(df)
    return dv.astype(np.float64)


# ==================== 注册表 ====================

def _reg(name, display_name, category, description, func, requires=("close",)):
    return Factor(name=name, display_name=display_name, category=category,
                  description=description, requires=requires, func=func)


FACTOR_REGISTRY: dict[str, Factor] = {}


def _register(f: Factor) -> Factor:
    FACTOR_REGISTRY[f.name] = f
    return f


_register(_reg("MOM_20", "20日动量", "momentum",
               "20 日收益率 close_t/close_{t-20}-1，正值为上涨趋势（academic/qlib158）", mom_20))
_register(_reg("ROC_10", "10日变化率", "momentum",
               "10 日变化率 close_t/close_{t-10}-1（qlib158 roc10）", roc_10))
_register(_reg("RSI_14", "相对强弱14日", "momentum",
               "Wilder RSI(14)，0-100，全涨→100、全跌→0（gtja191）", rsi_14))
_register(_reg("ALPHA_001", "Alpha#1条件动量", "momentum",
               "rank(ts_argmax(SignedPower((ret<0?std20:close),2),5))-0.5（alpha101）", alpha_001))
_register(_reg("TS_RANK_20", "20日位置动量", "momentum",
               "20 日内收盘价百分位，>0.5 强势（学术动量）", ts_rank_20))
_register(_reg("MOM_ACCEL", "动量加速度", "momentum",
               "delta(MOM_20,5)，动量二阶变化（academic）", mom_accel))
_register(_reg("MA_CROSS_20_60", "均线乖离20/60", "momentum",
               "ma20/ma60-1，中长期趋势强度（gtja191）", ma_cross_20_60))
_register(_reg("MAX_20_RET", "距20日高点回落", "momentum",
               "close/ts_max(close,20)-1，高位回落/创高动能（gtja191）", max_20_ret))
_register(_reg("BIAS_20", "乖离率20日", "mean_reversion",
               "close/ma20-1，价格偏离均线程度（gtja191 BIAS）", bias_20))
_register(_reg("BOLL_DIST", "布林带位置", "mean_reversion",
               "(close-mid)/(4*std20)，带宽内相对位置（gtja191）", boll_dist))
_register(_reg("REV_TS_RANK_20", "20日反转", "mean_reversion",
               "0.5-ts_rank(close,20)，超买回落/超跌反弹（gtja191 反转）", rev_ts_rank_20))
_register(_reg("RSV_20", "KDJ未成熟随机值", "mean_reversion",
               "(close-ts_min(low,20))/(ts_max(high,20)-ts_min(low,20))，超买>0.8（qlib158）",
               rsv_20, requires=("close", "high", "low")))
_register(_reg("PSY_20", "心理线20日", "mean_reversion",
               "20 日内上涨天数占比，>0.7 超买（gtja191 PSY）", psy_20))
_register(_reg("VOL_20", "20日波动率", "volatility",
               "20 日收益率样本标准差（academic）", vol_20))
_register(_reg("ATR_14", "平均真实波幅14日", "volatility",
               "ATR(14)/close，真波幅 max(H-L,|H-pc|,|L-pc|)（gtja191）",
               atr_14, requires=("close", "high", "low")))
_register(_reg("VOL_CHG_5", "波动率变化5日", "volatility",
               "delta(std20(ret),5)，波动率扩张/收缩（gtja191 STD）", vol_chg_5))
_register(_reg("VOL_RATIO", "短长波动比", "volatility",
               "std5(ret)/std20(ret)，>1 波动放大（academic）", vol_ratio))
_register(_reg("RANGE_20", "20日振幅", "volatility",
               "(ts_max(high,20)-ts_min(low,20))/ma20（gtja191）",
               range_20, requires=("close", "high", "low")))
_register(_reg("OBV_20", "OBV 20日变化", "volume_price",
               "OBV 20 日变化/20日均量，>0 资金流入（academic OBV）",
               obv_20, requires=("close", "vol")))
_register(_reg("VR_20", "成交量比率20日", "volume_price",
               "20 日上涨量/下跌量，>1 多头活跃（gtja191 VR）",
               vr_20, requires=("close", "vol")))
_register(_reg("VOL_RATIO_5", "量比5日", "volume_price",
               "vol/ma5(vol)，>1 放量（gtja191 量比）", vol_ratio_5, requires=("close", "vol")))
_register(_reg("CORR_20", "量价相关20日", "volume_price",
               "close 与 vol 的 20 日滚动相关（qlib158 corr20）",
               corr_20, requires=("close", "vol")))
_register(_reg("VMA_20", "成交量动量20日", "volume_price",
               "vol/ma20(vol)-1，量能趋势（qlib158 vma20）", vma_20, requires=("close", "vol")))
_register(_reg("VSUMP_10", "上涨量占比10日", "volume_price",
               "10 日上涨日成交量占比（qlib158 vsump10）", vsump_10, requires=("close", "vol")))
_register(_reg("ROE_CHG_Q", "ROE环比变化", "fundamental",
               "ROE 环比变化，需 panel[\"roe\"]，缺失→NaN 占位（academic）",
               roe_chg_q, requires=("roe",)))
_register(_reg("PE_PCT_250", "PE 250日分位", "fundamental",
               "pe_ttm 250 日分位，低分位=低估，需 panel[\"pe_ttm\"]（academic）",
               pe_pct_250, requires=("pe_ttm",)))
_register(_reg("EP_TTM", "盈利收益率", "fundamental",
               "1/pe_ttm，高=便宜，需 panel[\"pe_ttm\"]（academic 价值）",
               ep_ttm, requires=("pe_ttm",)))
_register(_reg("BP", "账面市值比", "fundamental",
               "1/pb，价值因子，需 panel[\"pb\"]（academic）", bp, requires=("pb",)))
_register(_reg("PEG", "市盈相对盈利增速", "fundamental",
               "pe_ttm/profit_yoy，<1 成长性低估，需 pe_ttm+profit_yoy（gtja191）",
               peg, requires=("pe_ttm", "profit_yoy")))
_register(_reg("DV_TTM", "股息率TTM", "fundamental",
               "股息率，高=高分红，需 panel[\"dv_ttm\"]（academic）",
               dv_ttm, requires=("dv_ttm",)))

assert len(FACTOR_REGISTRY) == 30, f"期望 30 个因子，实际 {len(FACTOR_REGISTRY)}"


# ==================== 注册表 API ====================

def _coerce(data):
    """把 DataFrame 或面板 dict 规范化为 (panel, close_df)。"""
    if isinstance(data, pd.DataFrame):
        return None, data
    if isinstance(data, dict):
        panel = dict(data)
        df = panel.get("close")
        if df is None:
            for v in panel.values():
                if isinstance(v, pd.DataFrame):
                    df = v
                    break
        if df is None:
            raise ValueError("面板 dict 需包含至少一个 DataFrame（如 'close'）")
        return panel, df
    raise TypeError(f"data 需为 DataFrame 或面板 dict，got {type(data).__name__}")


def compute_factor(data, name: str) -> pd.DataFrame:
    """计算单个因子，返回与输入同形的宽表（index=日期, columns=股票代码）。

    ``data``：close 宽表 DataFrame，或面板 dict ``{"close":..., "high":..., ...}``。
    未知因子名抛 ``KeyError``。
    """
    if not isinstance(name, str) or name not in FACTOR_REGISTRY:
        raise KeyError(f"unknown factor: {name!r}")
    panel, df = _coerce(data)
    return FACTOR_REGISTRY[name].func(df, panel=panel)


def compute_factor_panel(data, names: list[str]) -> dict[str, pd.DataFrame]:
    """批量计算多个因子，返回 ``{name: 同形宽表}``。"""
    return {n: compute_factor(data, n) for n in names}


def list_factors() -> list[dict]:
    """因子列表元数据（端点用）。"""
    return [
        {
            "name": f.name,
            "display_name": f.display_name,
            "category": f.category,
            "description": f.description,
        }
        for f in FACTOR_REGISTRY.values()
    ]
