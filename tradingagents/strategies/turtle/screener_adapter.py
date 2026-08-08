"""龟龟选股器适配入口。

将龟龟 TushareScreener 封装为独立调用：run_turtle_screener(tier1_only, tier2_limit) -> dict。
数据源使用 akshare 桥接层（get_pro_api），无需 tushare token。
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))  # 让 config/screener_config/cache_utils 可相对导入


def _clean_nan_inf(df):
    """把 NaN/inf 转 None，保证 JSON 可序列化（Starlette allow_nan=False）。

    注意：DataFrame.where(cond, None) 会把 None 转回 NaN，必须用
    astype(object) + 布尔掩码直接赋值 None。
    """
    import pandas as pd
    df = df.copy()
    df = df.replace([float("inf"), float("-inf")], float("nan"))
    df = df.astype(object)
    df[pd.isnull(df)] = None
    return df


def run_turtle_screener(tier1_only: bool = True, tier2_limit: int | None = None) -> dict:
    """运行龟龟选股器。

    Args:
        tier1_only: True 只跑 Tier1 全市场筛选（akshare 全市场拉取，可能数分钟）；
                    False 额外跑 Tier2 逐股深度分析（默认很慢）。
        tier2_limit: Tier2 股票数上限（默认取配置 tier2_max_stocks）。

    返回:
        {"candidates": [...]}；失败时返回 {"error"}。
    """
    from screener_core import TushareScreener
    s = TushareScreener(token="")
    try:
        df = s.run(tier1_only=tier1_only, tier2_limit=tier2_limit)
    except Exception as e:
        return {"error": str(e)}
    records = _clean_nan_inf(df).to_dict("records") if df is not None and not df.empty else []
    return {"candidates": records, "count": len(records)}
