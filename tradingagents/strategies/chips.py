# -*- coding: utf-8 -*-
"""筹码分布 CYQ —— 东方财富算法（stock-sdk src/indicators/chip.ts）的 Python 移植。

模型要点（与 chip.ts 严格一致）:
- 价格档:窗口内 [最低价, 最高价] 均分 150 档,档宽精度下限 0.01 元;
- 每根 K 线:先把存量筹码整体 ×(1 - 换手率),再把当日换手筹码按三角形分布
  (顶点在均价 avg=(O+C+H+L)/4)铺到 [low, high] 区间;一字板(high == low)
  时全部堆入单一价格档(权重 (FACTOR-1)*换手率/2,原版语义);
- 从分布读出:获利比例、平均成本(累计 50% 筹码处的价格,中位数成本,东财口径)、
  90/70 成本区间与集中度 (高-低)/(高+低),以及筹码峰价格与直方图。

换手率缺失(NaN)或为 0 的 bar 按 0 换手处理(纯衰减、不叠加新筹码),与 chip.ts
`((turnoverRate ?? 0) / 100) || 0` 的语义一致;换手率为负/超 100% 时夹逼到
[0,1]。窗口内全部 bar 换手为 0 时分布退化(总筹码为 0),返回全 None 字段
(不抛异常,对应原版 emptyItem)。

对外两个入口:
- `calc_chip_distribution(klines)`:纯函数,只依赖 pandas/numpy,可离线测试;
- `fetch_chip_klines(symbol)`:取含换手率的日 K 线(东财 stock_zh_a_hist 自带
  '换手率' 列;失败回退桥接层 daily() 无换手率 -> 置 NaN,由 calc 按 0 换手处理)。
"""
from __future__ import annotations

import datetime as _dt
import re as _re

import numpy as np
import pandas as pd

# 价格档数量(东财原版 factor = 150)
FACTOR = 150
# 默认分布回看窗口(根),与东财 App/网页筹码分布显示口径一致
DEFAULT_RANGE = 120


def _is_nan(v) -> bool:
    try:
        return v is None or pd.isna(v)
    except (TypeError, ValueError):
        return False


def _to_float(v) -> float:
    """NaN/None -> nan,其余尽力转 float"""
    if _is_nan(v):
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _pick_col(df: pd.DataFrame, names, default=None):
    """取第一个存在的列(候选列名兼容),全部缺失返回 default"""
    for c in names:
        if c in df.columns:
            return df[c]
    return default


def _prec12(v: float) -> float:
    """原版 x.toPrecision(12)/1 的等价写法(压浮点尾数)"""
    return float(f"{v:.12g}")


def _to_price(v: float) -> float:
    """原版 v.toFixed(2)/1 的等价写法(价格输出固定 2 位小数)"""
    return round(float(v), 2)


def _empty_result() -> dict:
    """分布退化 / 无有效 bar 时的输出(全 None,直方图为空)"""
    return {
        "profit_ratio": None,
        "avg_cost": None,
        "cost_90": [None, None],
        "cost_90_concentration": None,
        "cost_70": [None, None],
        "cost_70_concentration": None,
        "peak_price": None,
        "histogram": [],
    }


def calc_chip_distribution(
    klines: pd.DataFrame,
    range_: int = DEFAULT_RANGE,
    decimals: int = 3,
    include_histogram: bool = True,
) -> dict:
    """计算最后一日筹码分布(东财 CYQ,单日单行输出)。

    klines 需含 date/open/high/low/close 列;turnover_rate(换手率 %,可为 NaN
    或缺失)可选,缺失时按 0 换手处理。date 列兼容 date/trade_date,换手率列
    兼容 turnover_rate/turnover/turnoverRate/hsl。

    返回:
        profit_ratio: 获利比例 0..1(收盘价之下的筹码占比;收盘价缺失为 None)
        avg_cost: 平均成本(元,累计 50% 筹码处价格)
        cost_90 / cost_70: [下沿, 上沿] 价格区间
        cost_90_concentration / cost_70_concentration: 集中度 (高-低)/(高+低)
        peak_price: 筹码峰价格(直方图权重最大档位)
        histogram: [[price, weight], ...] 共 150 档,低 → 高,权重 0..1 归一化
    """
    if klines is None or len(klines) == 0:
        return _empty_result()

    df = klines
    date_col = _pick_col(df, ["date", "trade_date"])
    tr_col = _pick_col(df, ["turnover_rate", "turnover", "turnoverRate", "hsl"])
    if tr_col is None:
        tr_col = pd.Series(float("nan"), index=df.index)

    o = pd.to_numeric(df["open"], errors="coerce").to_numpy(dtype=float)
    h = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    l = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    c = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    tr = pd.to_numeric(tr_col, errors="coerce").to_numpy(dtype=float)
    # NaN/缺失 -> 0(源码 hsl/100 || 0 语义);负/超 1 在下方按 bar 夹逼
    tr = np.where(np.isnan(tr), 0.0, tr)

    n = len(df)
    start = max(0, n - range_) if range_ else 0

    # 窗口价格域:窗口内 [min low, max high](±Infinity 初始化;前复权价格可
    # 为 0/负,0 兜底会被下一根覆盖,这是超出原版的安全加固,正价下逐位等价)
    maxprice = -float("inf")
    minprice = float("inf")
    has_valid = False
    for i in range(start, n):
        if np.isnan(o[i]) or np.isnan(h[i]) or np.isnan(l[i]) or np.isnan(c[i]):
            continue
        has_valid = True
        if h[i] > maxprice:
            maxprice = h[i]
        if l[i] < minprice:
            minprice = l[i]
    if not has_valid:
        return _empty_result()

    # 精度不小于 0.01(产品逻辑,与东财一致)
    accuracy = max(0.01, (maxprice - minprice) / (FACTOR - 1))

    # 筹码堆叠:逐 bar 衰减 + 三角形分布叠加
    xdata = [0.0] * FACTOR

    def clamp_bucket(i: int) -> int:
        """档位索引夹逼到 [0, FACTOR-1](脏数据 avg 越界保护)"""
        return min(FACTOR - 1, max(0, int(i)))

    for i in range(start, n):
        if np.isnan(o[i]) or np.isnan(h[i]) or np.isnan(l[i]) or np.isnan(c[i]):
            continue  # 脏行整体跳过,不贡献分布(不中断整段计算)
        high, low = h[i], l[i]
        avg = (o[i] + c[i] + h[i] + l[i]) / 4.0
        # 换手率 % -> 0..1,夹逼到 [0,1](源码 Math.max(0, Math.min(1, ...)))
        t = max(0.0, min(1.0, tr[i] / 100.0))

        H = clamp_bucket((high - minprice) // accuracy)
        L = clamp_bucket(np.ceil((low - minprice) / accuracy))
        # G 点:一字板时 gFactor=FACTOR-1(矩形面积是三角形的 2 倍),否则三角形底
        g_factor = FACTOR - 1 if high == low else 2.0 / (high - low)
        g_index = clamp_bucket((avg - minprice) // accuracy)

        # 衰减:当日换手部分从存量筹码中等比例移除
        decay = 1.0 - t
        if decay != 1.0:
            for j in range(FACTOR):
                xdata[j] *= decay

        if high == low:
            xdata[g_index] += (g_factor * t) / 2.0
        else:
            for j in range(L, H + 1):
                cur = minprice + accuracy * j
                if cur <= avg:
                    if abs(avg - low) < 1e-8:
                        xdata[j] += g_factor * t
                    else:
                        xdata[j] += ((cur - low) / (avg - low)) * g_factor * t
                else:
                    if abs(high - avg) < 1e-8:
                        xdata[j] += g_factor * t
                    else:
                        xdata[j] += ((high - cur) / (high - avg)) * g_factor * t

    # bar 循环结束后 xdata 不再变更;预计算 toPrecision 归一化值,避免多次全档扫描
    xp = [_prec12(v) for v in xdata]
    total = sum(xp)
    if total == 0:
        return _empty_result()

    def get_cost_by_chip(chip: float) -> float:
        """累计到指定筹码量处的成本价(原版 getCostByChip)"""
        cost = 0.0
        s = 0.0
        for i in range(FACTOR):
            x = xp[i]
            if s + x > chip:
                cost = minprice + i * accuracy
                break
            s += x
        return cost

    def get_benefit_part(price: float) -> float:
        """指定价格的获利比例(原版 getBenefitPart):price 之上的档不计入"""
        below = 0.0
        for i in range(FACTOR):
            if price >= minprice + i * accuracy:
                below += xp[i]
        return below / total

    def compute_percent_chips(percent: float):
        """中间 percent 筹码的价格区间与集中度(原版 computePercentChips)"""
        pr_low = get_cost_by_chip(total * ((1 - percent) / 2.0))
        pr_high = get_cost_by_chip(total * ((1 + percent) / 2.0))
        conc = 0.0 if (pr_low + pr_high) == 0 else (pr_high - pr_low) / (pr_low + pr_high)
        return _to_price(pr_low), _to_price(pr_high), conc

    close = c[n - 1]
    p90 = compute_percent_chips(0.9)
    p70 = compute_percent_chips(0.7)

    result = {
        "profit_ratio": float(round(get_benefit_part(close), decimals))
        if not np.isnan(close) else None,
        "avg_cost": _to_price(get_cost_by_chip(total * 0.5)),
        "cost_90": [p90[0], p90[1]],
        "cost_90_concentration": float(round(p90[2], decimals)),
        "cost_70": [p70[0], p70[1]],
        "cost_70_concentration": float(round(p70[2], decimals)),
    }

    if include_histogram:
        prices = [_to_price(minprice + accuracy * i) for i in range(FACTOR)]
        ratios = [round(xp[i] / total, 6) for i in range(FACTOR)]
        peak_idx = max(range(FACTOR), key=lambda i: ratios[i])
        result["peak_price"] = prices[peak_idx]
        result["histogram"] = [[p, r] for p, r in zip(prices, ratios)]

    return result


def _normalize_code(symbol: str) -> str:
    """'600519' / '000001.SZ' / 'sz000001' -> 6 位纯数字(东财接口用)"""
    s = str(symbol).strip().upper()
    m = _re.search(r"(\d{6})", s)
    return m.group(1) if m else s


def fetch_chip_klines(symbol, start_date=None, end_date=None, adjust="qfq"):
    """取含换手率的日 K 线(按日期升序)。

    优先东财 `stock_zh_a_hist`(自带 '换手率' 列,前复权);失败回退桥接层
    `daily()`(新浪日线,无换手率列)。最终若换手率全部缺失,按成交量占比
    估算(换手率 ∝ 当日量/近20日均量,基准 1% 作相对量能),避免分布退化。

    返回列:date/open/high/low/close/turnover_rate(换手率 %)。

    symbol 支持 '600519' / '000001.SZ' / 'sz000001';start_date/end_date 为
    YYYYMMDD,缺省取近一年至今日。
    """
    import akshare as ak

    code = _normalize_code(symbol)
    if start_date is None:
        start_date = (_dt.datetime.now() - _dt.timedelta(days=365)).strftime("%Y%m%d")
    if end_date is None:
        end_date = _dt.datetime.now().strftime("%Y%m%d")

    out = None
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust=adjust,
                                start_date=start_date, end_date=end_date)
        if df is not None and len(df):
            out = df.rename(columns={
                "日期": "date", "开盘": "open", "最高": "high",
                "最低": "low", "收盘": "close", "换手率": "turnover_rate",
                "成交量": "vol",
            })
            out = out[["date", "open", "high", "low", "close", "turnover_rate", "vol"]].copy()
            for col in ("open", "high", "low", "close", "turnover_rate", "vol"):
                out[col] = pd.to_numeric(out[col], errors="coerce")
    except Exception:
        out = None
    if out is None:
        from tradingagents.strategies.akshare_tushare_bridge import get_pro_api
        try:
            pro = get_pro_api()
            d = pro.daily(ts_code=symbol, start_date=start_date, end_date=end_date)
        except Exception:
            d = None
        if d is None or len(d) == 0:
            return d
        out = d.rename(columns={"trade_date": "date"})
        out = out[["date", "open", "high", "low", "close", "vol"]].copy()
        for col in ("open", "high", "low", "close", "vol"):
            out[col] = pd.to_numeric(out[col], errors="coerce")
        out["turnover_rate"] = float("nan")

    out = out.dropna(subset=["date"]).reset_index(drop=True)
    if len(out) == 0:
        return out
    # 换手率全缺失:按成交量占比估算(相对量能,基准 1%)
    if out["turnover_rate"].isna().all():
        if "vol" in out.columns and out["vol"].notna().any():
            vol = out["vol"].astype(float)
            base = vol.rolling(20, min_periods=1).mean()
            denom = base.replace(0, np.nan)
            ratio = (vol / denom).fillna(1.0).clip(0.0, 10.0)
            out["turnover_rate"] = ratio * 1.0
        else:
            out["turnover_rate"] = 1.0
    return out