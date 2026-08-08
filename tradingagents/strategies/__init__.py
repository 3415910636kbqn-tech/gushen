"""tradingagents.strategies: 量化策略数据层。

提供 tushare Pro 兼容的数据桥接层（akshare 实现，无需 token），
供龟龟投资框架（Turtle_investment_framework）等外部策略直接复用。
"""
from .akshare_tushare_bridge import ProClient, get_pro_api

__all__ = ["ProClient", "get_pro_api"]
