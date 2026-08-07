"""龟龟估值引擎适配入口。

将龟龟 ValuationEngine 封装为独立调用：run_turtle_valuation(ts_code) -> dict。
数据源使用 akshare 桥接层（get_pro_api），无需 tushare token。

环境变量 TURTLE_TTL_CACHE=1 时启用龟龟 TTL 磁盘缓存（output/.collector_cache/ttl，
财务 7 天 / 行情 24 小时），可显著加速重复调用；默认关闭以免写盘。
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))  # 让 config/tushare_collector/valuation_engine 可相对导入


def run_turtle_valuation(ts_code: str) -> dict:
    """对给定股票运行龟龟估值引擎（DCF/DDM/PE Band/PEG/PS）。

    返回:
        {"ts_code", "markdown", "classification", "wacc"}；
        失败时返回 {"error", "ts_code"}。
    """
    from tushare_collector import TushareClient
    from valuation_engine import ValuationEngine

    client = TushareClient(token="")  # 桥接层不需要 token
    # 默认关闭 TTL 磁盘缓存（避免写盘）；TURTLE_TTL_CACHE=1 时开启以加速重复调用
    client._cache_enabled = os.environ.get("TURTLE_TTL_CACHE", "0") == "1"
    try:
        client.assemble_data_pack(ts_code)
        engine = ValuationEngine(ts_code, str(_ROOT / "output"), client)
        md = engine.run()
        # 带出 run() 内的中间结果（纯内存计算，读 _store，开销可忽略）
        try:
            engine.classification = engine.classify()
        except Exception:
            engine.classification = None
        try:
            engine.wacc = engine.compute_wacc()
        except Exception:
            engine.wacc = None
    except Exception as e:
        return {"error": str(e), "ts_code": ts_code}
    return {
        "ts_code": ts_code,
        "markdown": md,
        "classification": getattr(engine, "classification", None),
        "wacc": getattr(engine, "wacc", None),
    }
