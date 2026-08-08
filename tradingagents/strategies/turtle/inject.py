"""龟龟估值引擎摘要注入。

供基本面分析师（Toolkit.get_stock_fundamentals_unified 的 A 股分支）调用：
把龟龟估值引擎的估值摘要追加到基本面文本末尾。

独立成模块以便直接单测（不联网：monkeypatch adapter.run_turtle_valuation 即可覆盖）。
任何失败（import 失败、估值返回 error、估值抛异常）都原样返回 result_data，
绝不阻塞基本面主流程。
"""

import re
import logging

logger = logging.getLogger('turtle_inject')

def _ts_code_of(ticker: str) -> str:
    """把 A 股代码规范为 tushare ts_code（'600519'/'600519.SH' -> '600519.SH'）。

    后缀规则与 akshare_tushare_bridge._suffix 保持一致：
    6/9 开头 -> SH；8/4 或 920 开头 -> BJ；其余（0/3）-> SZ。
    非 6 位纯数字代码返回 ''（由估值引擎自行处理/返回错误）。
    """
    s = str(ticker).strip()
    s = re.sub(r"^(sh|sz|bj)", "", s, flags=re.I)
    s = re.sub(r"\.(sh|sz|bj)$", "", s, flags=re.I)
    if not re.fullmatch(r"\d{6}", s):
        return ""
    if s.startswith(("8", "4")) or s.startswith("920"):
        return f"{s}.BJ"
    if s.startswith(("6", "9")):
        return f"{s}.SH"
    return f"{s}.SZ"


def inject_turtle_valuation(ticker: str, result_data: str) -> str:
    """向 A 股基本面文本追加龟龟估值摘要。

    成功（估值返回 dict 且不含 error 键）返回 result_data + 估值摘要；
    任何失败（估值报错/返回 error/抛异常）原样返回 result_data。
    """
    try:
        from tradingagents.strategies.turtle import adapter

        val = adapter.run_turtle_valuation(_ts_code_of(ticker))
        if not isinstance(val, dict) or "error" in val:
            return result_data

        classification = val.get("classification")
        company_type = "未知"
        if isinstance(classification, dict) and classification.get("type"):
            company_type = classification["type"]

        wacc = val.get("wacc")
        wacc_val = "N/A"
        if isinstance(wacc, dict) and wacc.get("wacc") is not None:
            wacc_val = wacc["wacc"]

        summary = "\n\n## 估值引擎摘要\n"
        summary += f"- 公司类型: {company_type}\n"
        summary += f"- WACC: {wacc_val}\n\n"
        summary += str(val.get("markdown") or "")[:2000]

        return result_data + summary
    except Exception as e:
        logger.warning(f"龟龟估值注入失败(忽略): {e}")
        return result_data
