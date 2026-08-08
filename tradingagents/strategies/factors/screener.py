"""受限因子选股：桥接层 daily() 历史 → OHLCV 面板 → 因子计算 → 截面排序。

**取舍说明**：全市场逐只算因子在实时 API 下不可行（数千只 × 单只日线 =
数千次网络请求）。本实现为**受限/示例版**：
- body 必须传 ``symbols``（股票代码列表），上限 ``MAX_SYMBOLS = 50``；
- 每只股票经桥接层 ``daily()`` 拉最近 ~420 自然日历史，拼成同形宽表面板
  （index=YYYYMMDD 字符串, columns=股票代码），计算所选因子；
- 对每列取各自**最后一期非 NaN** 因子值，按 ``condition`` 排序取前 ``top_n``；
- 需要历史序列的面板字段之外的字段（基本面 pe_ttm/roe 等）缺失时，
  对应因子返回 NaN 并被剔除，响应带 ``note`` 说明。
- 行情拉取失败返回 ``last_date=None``，端点映射为 503（需要预计算）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .registry import FACTOR_REGISTRY, compute_factor

MAX_SYMBOLS = 50
LOOKBACK_DAYS = 420  # 自然日 ≈ 280 交易日，覆盖 ts_rank(250) 等长窗口

log = logging.getLogger(__name__)

_FIELDS = ("open", "high", "low", "close", "vol", "amount")


def _daily_panel(pro, symbols, end_date=None):
    """逐只拉 daily() 历史，构建 OHLCV 宽表面板。返回 (panel, last_date)。"""
    end_date = end_date or datetime.now().strftime("%Y%m%d")
    start_date = (datetime.strptime(str(end_date), "%Y%m%d")
                  - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    frames = {}
    for code in symbols:
        try:
            df = pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
        except Exception as exc:  # noqa: BLE001 数据源偶发失败，跳过该股
            log.warning("factor-screen: daily(%s) 失败: %s", code, exc)
            df = None
        if df is None or df.empty or "trade_date" not in df.columns:
            continue
        df = df.sort_values("trade_date").drop_duplicates("trade_date")
        frames[code] = df
    if not frames:
        return None, None

    panel = {}
    for field in _FIELDS:
        cols = {}
        for code, df in frames.items():
            if field in df.columns:
                cols[code] = pd.to_numeric(df.set_index("trade_date")[field],
                                           errors="coerce")
        if cols:
            panel[field] = pd.DataFrame(cols).sort_index()
    last_date = None
    for df in frames.values():
        last_date = max(df["trade_date"].iloc[-1], last_date or "")
    return (panel or None), (last_date or None)


def screen_by_factor(pro, factor, condition="top", top_n=20,
                     symbols=None, trade_date=None):
    """受限因子选股主入口。

    - ``symbols``：股票代码列表（≤50，如 ["600519.SH", "000001.SZ"]）
    - ``condition``：top=因子值最大，bottom=最小
    - 返回 dict：{factor, condition, top_n, last_date, results, note}
    """
    if factor not in FACTOR_REGISTRY:
        raise KeyError(factor)
    if condition not in ("top", "bottom"):
        raise ValueError(f"condition 需为 'top' | 'bottom'，got {condition!r}")
    if not isinstance(top_n, int) or not 1 <= top_n <= 500:
        raise ValueError("top_n 需为 1-500 的整数")
    if not symbols:
        raise ValueError("受限实现要求 body 传 symbols（股票代码列表，≤50 只）")
    symbols = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if len(symbols) > MAX_SYMBOLS:
        raise ValueError(f"受限实现最多支持 {MAX_SYMBOLS} 只股票，got {len(symbols)}")
    if trade_date is not None and not str(trade_date).isdigit():
        raise ValueError("trade_date 需为 YYYYMMDD 格式（如 20260807）")

    panel, last_date = _daily_panel(pro, symbols, trade_date)
    if panel is None or last_date is None:
        return {"factor": factor, "last_date": None, "results": [],
                "note": "行情数据拉取失败（数据源不可用/网络受限），该端点需要历史截面数据，建议预计算"}

    meta = FACTOR_REGISTRY[factor]
    factor_df = compute_factor(panel, factor)
    # 每列取各自最后一期非 NaN 值（各股停牌/上市日期不同，不强制同截面）
    last_row = factor_df.apply(
        lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan)

    note = None
    missing = [f for f in meta.requires if f not in panel]
    if missing:
        note = (f"因子依赖但面板缺失的字段: {', '.join(missing)}——"
                f"这些股票返回 NaN 已被剔除；基本面因子需预计算的截面数据")
    if last_row.dropna().empty:
        note = (note + "；" if note else "") + "所有股票因子值均为 NaN（warmup 不足或数据缺失），无排序结果"

    ascending = condition == "bottom"
    ranked = last_row.dropna().sort_values(ascending=ascending).head(top_n)
    results = [{"ts_code": code, "value": round(float(v), 6)}
               for code, v in ranked.items()]
    return {"factor": factor, "condition": condition, "top_n": len(results),
            "last_date": last_date, "results": results, "note": note}
