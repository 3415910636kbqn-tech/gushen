"""龟龟估值引擎适配入口。

将龟龟 ValuationEngine 封装为独立调用：run_turtle_valuation(ts_code) -> dict。
数据源使用 akshare 桥接层（get_pro_api），无需 tushare token。

ts_code 入口规范化：6 位纯数字自动补 A 股后缀（6/9->.SH、0/3->.SZ、8/4/920->.BJ），
已是 .SH/.SZ/.BJ 后缀则保留（统一大写）；其他输入返回 {"error": "无效股票代码"}。

默认启用龟龟 TTL 磁盘缓存（output/.collector_cache/ttl，财务 7 天 / 行情 24 小时），
可显著加速重复调用；环境变量 TURTLE_TTL_CACHE=0 可关闭。
"""

import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))  # 让 config/tushare_collector/valuation_engine 可相对导入


def _normalize_ts_code(ts_code) -> str:
    """把 A 股代码规范为带后缀的 tushare ts_code（与 inject._ts_code_of / bridge._suffix 规则一致）。

    '000001' -> '000001.SZ'；'600519.SH'/'000001.sz' -> 统一大写保留；
    6/9 开头 -> SH；8/4 或 920 开头 -> BJ；其余（0/3）-> SZ。
    无法识别的输入（如 'abc'）返回 ''（调用方应返回错误）。
    """
    if ts_code is None:
        return ""
    s = str(ts_code).strip()
    m = re.fullmatch(r"(\d{6})(\.(SH|SZ|BJ))?", s.upper())
    if not m:
        return ""
    digits = m.group(1)
    if m.group(3):
        return f"{digits}.{m.group(3)}"
    if digits.startswith(("8", "4")) or digits.startswith("920"):
        return f"{digits}.BJ"
    if digits.startswith(("6", "9")):
        return f"{digits}.SH"
    return f"{digits}.SZ"


def run_turtle_valuation(ts_code: str) -> dict:
    """对给定股票运行龟龟估值引擎（DCF/DDM/PE Band/PEG/PS）。

    ts_code 支持 6 位纯数字（自动补 A 股后缀）或带 .SH/.SZ/.BJ 后缀；
    其他输入返回 {"error": "无效股票代码", "ts_code"}，不抛异常。

    返回:
        {"ts_code", "markdown", "classification", "wacc"}；
        失败时返回 {"error", "ts_code"}。
    """
    code = _normalize_ts_code(ts_code)
    if not code:
        return {"error": "无效股票代码", "ts_code": ts_code}
    ts_code = code

    from tushare_collector import TushareClient
    from valuation_engine import ValuationEngine

    client = TushareClient(token="")  # 桥接层不需要 token
    # TushareClient 默认启用 TTL 磁盘缓存（output/.collector_cache/ttl）；显式关闭可设 TURTLE_TTL_CACHE=0
    if os.environ.get("TURTLE_TTL_CACHE", "1") == "0":
        client._cache_enabled = False
    try:
        client.assemble_data_pack(ts_code)
        engine = ValuationEngine(ts_code, str(_ROOT / "output"), client)
        md = engine.run()
        # run() 内部已计算 classification/wacc 并存到实例属性，这里只读取（纯内存，无重复计算）
        classification = getattr(engine, "classification", None)
        wacc = getattr(engine, "wacc", None)
    except Exception as e:
        return {"error": str(e), "ts_code": ts_code}
    return {
        "ts_code": ts_code,
        "markdown": md,
        "classification": classification,
        "wacc": wacc,
    }