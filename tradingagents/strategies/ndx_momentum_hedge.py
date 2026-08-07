# -*- coding: utf-8 -*-
"""NDX 动量对冲策略（移植自 wepoets1107/ndx-momentum-hedge，MIT）。

纳斯达克100动量选股 + PSQ 1x 反向 QQQ 对冲，周频调仓。
数据源优先 yfinance；失败时回退 Yahoo query2 直连（requests + crumb），
成功结果缓存到 data/cache/ndx_prices.pkl（2 小时有效）。
所有数据源都不可用时返回 {"error": "数据获取失败"}。
"""
import os
import pickle
import time
from datetime import datetime

import requests
import yfinance as yf

TOP_K = 5
LOOKBACK = 20
CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "cache", "ndx_prices.pkl",
)

NDX_100 = [
    "NVDA", "AAPL", "AVGO", "META", "MU", "MSFT", "AMD", "AMZN", "TSLA", "GOOGL",
    "GOOG", "INTC", "ASML", "CSCO", "COST", "AMAT", "LRCX", "NFLX", "PLTR", "PANW",
    "ARM", "TXN", "KLAC", "LIN", "AMGN", "CRWD", "PEP", "ADBE", "ADI",
    "QCOM", "BKNG", "WDAY", "MRVL", "INTU", "CDNS", "SNPS", "PCAR", "NXPI", "FTNT",
    "MCHP", "ROP", "ODFL", "MAR", "CPRT", "ORLY", "CTAS", "PAYX", "AZN", "MNST",
    "KDP", "DASH", "DDOG", "MDB", "TTD", "TEAM", "KHC", "XEL", "EXC",
    "GEHC", "CSGP", "BKR", "ROST", "LULU", "IDXX", "FAST", "EA", "VRTX", "REGN",
    "GFS", "SBUX", "CMCSA", "ADP", "MELI", "GILD", "MDLZ", "ZS", "WBD", "PDD", "MRNA", "DXCM",
    "CRM", "NOW", "ISRG", "BIIB", "CEG", "CDW", "CHTR", "DLTR", "FANG", "ILMN",
    "MSTR", "ON", "PYPL", "RIVN", "SMCI", "TTWO", "VRSK", "ZM",
]

# 上次调仓的 top_symbols（模块级内存缓存，进程重启后重置）
_LAST_TOP = None


def _series_to_prices(close):
    """把 yfinance Close（DataFrame/Series）转成 {ticker: {date: price}}"""
    out = {}
    if hasattr(close, "columns"):
        cols = list(close.columns)
    else:
        cols = [close.name] if close.name is not None else []
        close = close.to_frame()
    for c in cols:
        t = str(c[-1] if isinstance(c, tuple) else c)
        try:
            out[t] = {d.strftime("%Y-%m-%d"): float(v) for d, v in close[c].dropna().items()}
        except Exception:
            continue
        time.sleep(0.02)
    return out


def _save_cache(data):
    """把 {ticker: {date: price}} 写入本地 pkl 缓存"""
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "wb") as f:
            pickle.dump({"_ts": time.time(), "data": data}, f)
    except Exception:
        pass


def _load_cache(cache_minutes=120):
    """读取本地 pkl 缓存；命中且未过期则返回数据，否则返回 None"""
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "rb") as f:
            cache = pickle.load(f)
        if time.time() - cache.get("_ts", 0) < cache_minutes * 60 and cache.get("data"):
            return cache["data"]
    except Exception:
        pass
    return None


def _fetch_prices_yf(tickers):
    """yfinance 批量下载 60 天日线（adj close），返回 {ticker: {date: price}}"""
    data = yf.download(
        list(tickers) + ["QQQ", "PSQ"],
        period="60d", interval="1d",
        auto_adjust=True, progress=False, threads=True, timeout=15,
    )
    if data is None or data.empty or "Close" not in data:
        return {}
    out = _series_to_prices(data["Close"])
    return out if out.get("QQQ") else {}


def _fetch_prices_query2(tickers):
    """回退：Yahoo query2 直连（requests + crumb）"""
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        sess.get("https://fc.yahoo.com/", timeout=8)
        crumb = sess.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=8).text.strip()
        if not _crumb_ok(crumb):
            return {}  # 拿不到 crumb（限流/反爬），快速失败
    except Exception:
        return {}
    now = time.time()
    ts_end = int(now)
    ts_start = ts_end - 60 * 86400  # 60 天足够动量 + 周线
    all_prices = {}
    for tkr in list(tickers) + ["QQQ", "PSQ"]:
        try:
            url = (
                f"https://query2.finance.yahoo.com/v8/finance/chart/{tkr}"
                f"?period1={ts_start}&period2={ts_end}&interval=1d&crumb={crumb}"
            )
            r = sess.get(url, timeout=8)
            result = r.json()["chart"]["result"][0]
            adj = result["indicators"]["adjclose"][0]["adjclose"]
            ts_arr = result["timestamp"]
            all_prices[tkr] = {
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d"): p
                for ts, p in zip(ts_arr, adj) if p is not None
            }
            time.sleep(0.2)
        except Exception:
            continue
    if all_prices.get("QQQ"):
        _save_cache(all_prices)
    return all_prices


def _crumb_ok(txt):
    """有效 crumb 是短 base64 串；HTML 错误页/限流提示视为无效"""
    txt = (txt or "").strip()
    return bool(txt) and len(txt) < 64 and "<" not in txt and "Too Many" not in txt


def _yahoo_probe():
    """快速探测 Yahoo Finance 是否可用（crumb 获取，约 5s 超时）"""
    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0"})
        sess.get("https://fc.yahoo.com/", timeout=5)
        r = sess.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=5)
        return r.status_code == 200 and _crumb_ok(r.text)
    except Exception:
        return False


def _fetch_prices(tickers):
    """多级获取：yfinance -> query2 直连 -> 本地缓存兜底。

    返回 {ticker: {date: price}}
    """
    try:
        yf.set_config("network.retries", 0)
    except Exception:
        pass
    if _yahoo_probe():
        try:
            out = _fetch_prices_yf(tickers)
            if out:
                _save_cache(out)
                return out
        except Exception:
            pass
    out = _fetch_prices_query2(tickers)
    if out.get("QQQ"):
        return out
    cached = _load_cache(cache_minutes=24 * 60 * 7)  # 过期缓存最后兜底（7 天）
    return cached or {}


def _momentum(prices, ticker, dates):
    """20 日动量（%），返回 (momentum, 最新价)"""
    vals = [prices.get(ticker, {}).get(d) for d in dates[-LOOKBACK:] if prices.get(ticker, {}).get(d)]
    if len(vals) < 2:
        return None, None
    return round((vals[-1] / vals[0] - 1) * 100, 1), vals[-1]


def run_ndx_momentum_hedge(prices=None):
    """运行 NDX 动量对冲策略，返回周度调仓报告 dict。

    字段：date / week_start / pool_size / momentum_top5 / top_symbols /
         changes / performance / qqq_12w / full_momentum

    prices: 可选，{ticker: {date: price}}。不传则自动拉取网络数据。
    """
    global _LAST_TOP
    if prices is None:
        prices = _fetch_prices(NDX_100)
    qqq_dates = sorted(prices.get("QQQ", {}).keys())
    if not qqq_dates:
        return {"error": "数据获取失败"}
    today = qqq_dates[-1]
    last_week = qqq_dates[-5] if len(qqq_dates) >= 5 else qqq_dates[0]
    week_start = qqq_dates[-6] if len(qqq_dates) >= 6 else qqq_dates[0]

    # 动量排名 + 方案B选股（20日动量>0，按5日动量取前5）
    momentum_list = []
    for tkr in NDX_100:
        mom, price = _momentum(prices, tkr, qqq_dates)
        if mom is None or price is None:
            continue
        p_wk, p_now = prices.get(tkr, {}).get(week_start), prices.get(tkr, {}).get(today)
        mom5 = round((p_now / p_wk - 1) * 100, 1) if p_wk and p_now and p_wk > 0 else None
        momentum_list.append({"symbol": tkr, "momentum": mom, "momentum_5d": mom5, "price": round(price, 2)})

    qualified = [m for m in momentum_list if m["momentum"] > 0 and m["momentum_5d"] is not None]
    qualified.sort(key=lambda x: x["momentum_5d"], reverse=True)
    top_k = qualified[:TOP_K]

    qqq_now, qqq_lw = prices.get("QQQ", {}).get(today), prices.get("QQQ", {}).get(last_week)
    psq_now, psq_lw = prices.get("PSQ", {}).get(today), prices.get("PSQ", {}).get(last_week)
    qqq_w = round((qqq_now / qqq_lw - 1) * 100, 1) if qqq_now and qqq_lw else 0
    psq_w = round((psq_now / psq_lw - 1) * 100, 1) if psq_now and psq_lw else 0

    # 对比上次持仓（内存缓存；首次调用视为全部新增）
    top_syms = [m["symbol"] for m in top_k]
    prev_set = set(_LAST_TOP or [])
    cur_set = set(top_syms)
    _LAST_TOP = list(cur_set)
    rank_order = {s: i for i, s in enumerate(top_syms)}
    changes = {
        "added": sorted(cur_set - prev_set, key=lambda s: rank_order.get(s, 99)),
        "removed": sorted(prev_set - cur_set, key=lambda s: rank_order.get(s, 99)),
        "kept": sorted(cur_set & prev_set, key=lambda s: rank_order.get(s, 99)),
    }

    # QQQ 近 12 周走势
    qqq_12w = []
    step = max(1, len(qqq_dates) // 12)
    for d in qqq_dates[-60::step]:
        qqq_12w.append({"date": d, "qqq": prices.get("QQQ", {}).get(d), "psq": prices.get("PSQ", {}).get(d)})

    return {
        "date": today,
        "week_start": week_start,
        "pool_size": len(momentum_list),
        "momentum_top5": top_k,
        "top_symbols": top_syms,
        "changes": changes,
        "performance": {
            "strategy_w": round(
                sum(m.get("momentum_5d", 0) for m in top_k) / max(1, len(top_k)) * 0.5 + psq_w * 0.5, 1
            ),
            "qqq_w": qqq_w,
            "psq_w": psq_w,
        },
        "qqq_12w": qqq_12w,
        "full_momentum": momentum_list[:30],
    }