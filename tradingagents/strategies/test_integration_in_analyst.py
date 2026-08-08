"""基本面分析师注入龟龟估值摘要 —— 集成测试。

无需联网：
- inject_turtle_valuation 单测直接 monkeypatch adapter.run_turtle_valuation。
- Toolkit.get_stock_fundamentals_unified 的 A 股路径集成测试
  monkeypatch 数据层（价格/基本面）与估值层，验证"估值引擎摘要"进入最终文本。

注意：测试文件在 import tradingagents 之前关闭 MongoDB 存储，
避免测试环境连接本机 MongoDB 造成 5s 超时（与功能无关）。
"""

import os

os.environ.setdefault("USE_MONGODB_STORAGE", "false")


def _fake_valuation(ts_code):
    return {
        "ts_code": ts_code,
        "markdown": "## 估值摘要 DCF\nDCF 内在价值 12.34 元",
        "classification": {"type": "混合型"},
        "wacc": {"wacc": 3.76},
    }


class TestInjectTurtleValuation:
    """inject_turtle_valuation 直接单测（不联网）"""

    def test_success_appends_summary(self, monkeypatch):
        from tradingagents.strategies.turtle import adapter
        from tradingagents.strategies.turtle.inject import inject_turtle_valuation

        calls = []

        def fake_run(ts_code):
            calls.append(ts_code)
            return _fake_valuation(ts_code)

        monkeypatch.setattr(adapter, "run_turtle_valuation", fake_run)

        original = "## A股基本面数据\n核心财务数据"
        result = inject_turtle_valuation("600519", original)

        assert "估值引擎摘要" in result
        assert "混合型" in result
        assert "3.76" in result
        assert "DCF" in result
        assert original in result  # 原文本完整保留
        assert calls == ["600519.SH"]  # 6 开头 -> .SH

    def test_sz_suffix(self, monkeypatch):
        from tradingagents.strategies.turtle import adapter
        from tradingagents.strategies.turtle.inject import inject_turtle_valuation

        calls = []
        monkeypatch.setattr(
            adapter, "run_turtle_valuation",
            lambda ts_code: calls.append(ts_code) or _fake_valuation(ts_code),
        )
        inject_turtle_valuation("000001", "x")
        assert calls == ["000001.SZ"]  # 0 开头 -> .SZ

    def test_error_result_returns_original(self, monkeypatch):
        from tradingagents.strategies.turtle import adapter
        from tradingagents.strategies.turtle.inject import inject_turtle_valuation

        monkeypatch.setattr(
            adapter, "run_turtle_valuation",
            lambda ts_code: {"error": "no data", "ts_code": ts_code},
        )
        original = "基本面原文"
        assert inject_turtle_valuation("600519", original) == original

    def test_exception_returns_original(self, monkeypatch):
        from tradingagents.strategies.turtle import adapter
        from tradingagents.strategies.turtle.inject import inject_turtle_valuation

        def boom(ts_code):
            raise RuntimeError("估值引擎崩溃")

        monkeypatch.setattr(adapter, "run_turtle_valuation", boom)
        original = "基本面原文"
        assert inject_turtle_valuation("600519", original) == original

    def test_none_classification_and_wacc(self, monkeypatch):
        """classification/wacc 为 None 时不崩溃，仍注入摘要。"""
        from tradingagents.strategies.turtle import adapter
        from tradingagents.strategies.turtle.inject import inject_turtle_valuation

        monkeypatch.setattr(
            adapter, "run_turtle_valuation",
            lambda ts_code: {
                "ts_code": ts_code,
                "markdown": "## 估值",
                "classification": None,
                "wacc": None,
            },
        )
        result = inject_turtle_valuation("600519", "原文")
        assert "估值引擎摘要" in result
        assert "未知" in result
        assert "N/A" in result


class TestToolkitChinaFundamentals:
    """Toolkit.get_stock_fundamentals_unified 的 A 股路径集成测试。"""

    def test_valuation_injected_in_china_fundamentals(self, monkeypatch):
        from tradingagents.strategies.turtle import adapter as ta
        from tradingagents.agents.utils.agent_utils import Toolkit

        calls = []

        def fake_run(ts_code):
            calls.append(ts_code)
            return _fake_valuation(ts_code)

        monkeypatch.setattr(ta, "run_turtle_valuation", fake_run)

        # mock 数据层，避免联网
        import tradingagents.dataflows.interface as interface
        monkeypatch.setattr(interface, "get_china_stock_data_unified",
                            lambda *a, **k: "最新价 10.00 元")

        import tradingagents.dataflows.optimized_china_data as ocd
        monkeypatch.setattr(
            ocd.OptimizedChinaDataProvider, "_generate_fundamentals_report",
            lambda self, *a, **k: "核心财务指标数据",
        )

        from tradingagents.utils.stock_utils import StockUtils
        monkeypatch.setattr(
            StockUtils, "get_market_info",
            lambda ticker: {
                "ticker": ticker,
                "market": "china_a",
                "market_name": "中国A股",
                "currency_name": "人民币",
                "currency_symbol": "¥",
                "data_source": "china_unified",
                "is_china": True,
                "is_hk": False,
                "is_us": False,
            },
        )

        result = Toolkit.get_stock_fundamentals_unified.invoke({"ticker": "600519", "curr_date": "2025-01-02"})

        assert isinstance(result, str)
        assert "估值引擎摘要" in result
        assert "混合型" in result
        assert calls == ["600519.SH"]  # 确认注入被触发且 ts_code 正确

    def test_hk_not_injected(self, monkeypatch):
        """港股分支不应出现估值摘要、不应触发估值调用。"""
        from tradingagents.strategies.turtle import adapter as ta
        from tradingagents.agents.utils.agent_utils import Toolkit

        calls = []
        monkeypatch.setattr(
            ta, "run_turtle_valuation",
            lambda ts_code: calls.append(ts_code) or _fake_valuation(ts_code),
        )

        import tradingagents.dataflows.interface as interface
        monkeypatch.setattr(interface, "get_hk_stock_data_unified",
                            lambda *a, **k: "港股行情与财务摘要数据（长度需超过阈值 100 字符才会被采用，这里给出足够长的详细数据用于测试兜底逻辑）" * 3)
        monkeypatch.setattr(interface, "get_hk_stock_info_unified",
                            lambda *a, **k: {"name": "测试港股", "source": "mock"})

        from tradingagents.utils.stock_utils import StockUtils
        monkeypatch.setattr(
            StockUtils, "get_market_info",
            lambda ticker: {
                "ticker": ticker,
                "market": "hong_kong",
                "market_name": "港股",
                "currency_name": "港币",
                "currency_symbol": "HK$",
                "data_source": "hk",
                "is_china": False,
                "is_hk": True,
                "is_us": False,
            },
        )

        result = Toolkit.get_stock_fundamentals_unified.invoke({"ticker": "00700.HK", "curr_date": "2025-01-02"})

        assert isinstance(result, str)
        assert "估值引擎摘要" not in result
        assert calls == []  # 未触发估值注入

# ---- 收尾补充：.BJ 后缀规则 + 输入容错（Task 6 Minor） ----
import pytest
from tradingagents.strategies.turtle.inject import _ts_code_of

@pytest.mark.parametrize("inp,expected", [
    ("920001", "920001.BJ"),
    ("830001", "830001.BJ"),
    ("430001", "430001.BJ"),
    ("bj920001", "920001.BJ"),
    ("600519", "600519.SH"),
    ("600519.SH", "600519.SH"),
    ("sh600519", "600519.SH"),
    ("000001", "000001.SZ"),
    ("000001.SZ", "000001.SZ"),
    ("sz000001", "000001.SZ"),
    ("abc", ""),
    ("12345", ""),
])
def test_ts_code_of(inp, expected):
    assert _ts_code_of(inp) == expected
