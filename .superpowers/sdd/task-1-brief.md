### Task 1: 数据桥接层 akshare_tushare_bridge

**Files:**
- Create: `tradingagents/strategies/__init__.py`
- Create: `tradingagents/strategies/akshare_tushare_bridge.py`
- Test: `tradingagents/strategies/test_akshare_tushare_bridge.py`

**Interfaces:**
- Produces: `get_pro_api() -> ProClient`；`ProClient.stock_basic(**kw) -> pd.DataFrame`、`daily_basic(**kw)`、`income(**kw)`、`balancesheet(**kw)`、`cashflow(**kw)`、`fina_indicator(**kw)`、`dividend(**kw)`、`weekly(**kw)`、`daily(**kw)`、`close()`。所有返回 DataFrame 列名对齐 tushare（snake_case 英文字段，A股金额单位=元）。

- [ ] **Step 1: 写桥接层骨架 + 单测（先写测试）**

测试文件 `test_akshare_tushare_bridge.py`：
```python
import pytest
from tradingagents.strategies.akshare_tushare_bridge import get_pro_api

@pytest.fixture(scope="module")
def pro():
    return get_pro_api()

def test_stock_basic_columns(pro):
    df = pro.stock_basic()
    assert {"ts_code", "name", "industry"}.issubset(df.columns)
    assert len(df) > 3000

def test_daily_basic_columns(pro):
    df = pro.daily_basic(ts_code="000001.SZ")
    assert {"ts_code", "trade_date", "pe_ttm", "pb", "total_mv", "dv_ttm"}.issubset(df.columns)

def test_fina_indicator_columns(pro):
    df = pro.fina_indicator(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "roe", "grossprofit_margin"}.issubset(df.columns)

def test_income_columns(pro):
    df = pro.income(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "revenue", "n_income"}.issubset(df.columns)

def test_balancesheet_columns(pro):
    df = pro.balancesheet(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "total_assets", "total_liab", "money_cap"}.issubset(df.columns)

def test_cashflow_columns(pro):
    df = pro.cashflow(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "n_cashflow_act"}.issubset(df.columns)

def test_dividend_columns(pro):
    df = pro.dividend(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "cash_div_tax"}.issubset(df.columns)

def test_weekly_columns(pro):
    df = pro.weekly(ts_code="000001.SZ")
    assert {"ts_code", "trade_date", "close"}.issubset(df.columns)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd C:\Users\cccbqn\gushen && .\env\Scripts\python.exe -m pytest tradingagents/strategies/test_akshare_tushare_bridge.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现桥接层**

`tradingagents/strategies/akshare_tushare_bridge.py` 骨架：
```python
"""Tushare Pro API 兼容桥接层（akshare 实现，无 token）。
移植自 Turtle_investment_framework（MIT）数据层适配。
所有接口返回 DataFrame，列名对齐 tushare（英文字段、A股单位=元）。
"""
import pandas as pd
import akshare as ak
import re

def _normalize_ts_code(ts_code):
    """'000001.SZ' -> '000001'"""
    return str(ts_code).split(".")[0] if ts_code else None

def _pick(df, mapping):
    """akshare 中文列 -> tushare 英文字段重命名；缺失列置 None"""
    out = pd.DataFrame(index=df.index)
    for en, zh in mapping.items():
        if zh in df.columns:
            out[en] = df[zh]
        else:
            out[en] = None
    return out

class ProClient:
    def __init__(self):
        self._sina_basic_cache = None

    def _sina_basic(self):
        # 新浪 A股 基础信息（全市场）: ts_code/name/industry
        if self._sina_basic_cache is None:
            df = ak.stock_info_a_code_name()  # code, name
            ind = ak.stock_board_industry_name_em()  # 行业板块
            # 简化：code+name，industry 置空（可后续用 stock_individual_info_em 补）
            df.columns = ["ts_code", "name"]
            df["ts_code"] = df["ts_code"].apply(lambda c: f"{c}.SH" if c.startswith("6") or c.startswith("9") else f"{c}.SZ")
            self._sina_basic_cache = df
        return self._sina_basic_cache

    def stock_basic(self, **kw):
        return self._sina_basic()

    def daily_basic(self, ts_code=None, trade_date=None, **kw):
        code = _normalize_ts_code(ts_code)
        spot = ak.stock_zh_a_spot_em()  # 东方财富实时快照
        spot.columns = [c.strip() for c in spot.columns]
        mapping = {
            "ts_code": "代码", "trade_date": None,
            "pe_ttm": "市盈率-动态", "pb": "市净率", "total_mv": "总市值",
            "turnover_rate": "换手率", "dv_ttm": None,
        }
        df = _pick(spot, mapping)
        df["ts_code"] = df["ts_code"].apply(lambda c: f"{c}.SH" if str(c).startswith("6") else f"{c}.SZ")
        if code:
            df = df[df["ts_code"] == f"{code}.SH" if False else df["ts_code"].str.startswith(code)]
        return df

    def fina_indicator(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        # 新浪财务指标（含 ROE/毛利率等）
        df = ak.stock_financial_analysis_indicator(symbol=code)
        mapping = {"ts_code": None, "end_date": "日期", "roe": "净资产收益率(%)",
                   "grossprofit_margin": "销售毛利率(%)"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def income(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        # 新浪利润表（报告期）
        df = ak.stock_financial_report_sina(stock=code, symbol="利润表")
        mapping = {"ts_code": None, "end_date": "报告日", "revenue": "营业收入",
                   "n_income": "净利润"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def balancesheet(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_financial_report_sina(stock=code, symbol="资产负债表")
        mapping = {"ts_code": None, "end_date": "报告日", "total_assets": "资产总计",
                   "total_liab": "负债合计", "money_cap": "货币资金"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def cashflow(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_financial_report_sina(stock=code, symbol="现金流量表")
        mapping = {"ts_code": None, "end_date": "报告日", "n_cashflow_act": "经营现金流量净额"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def dividend(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_fhps_detail_em(symbol=code)
        mapping = {"ts_code": None, "end_date": "报告期", "cash_div_tax": "派息"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def weekly(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        mapping = {"ts_code": None, "trade_date": "日期", "close": "收盘"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def daily(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        mapping = {"ts_code": None, "trade_date": "日期", "close": "收盘"}
        out = _pick(df, mapping)
        out["ts_code"] = f"{code}.SZ" if str(code).startswith("0") else f"{code}.SH"
        return out

    def close(self):
        pass

def get_pro_api():
    return ProClient()
```

> 注意：akshare 各接口列名可能随版本变化，Step 4 若失败用 `df.columns` 实际值调整 mapping（打印诊断）。股票代码后缀规则：6/9 开头=SH，0/3 开头=SZ（简化版）。

- [ ] **Step 4: 运行测试，按需调整列名映射**

Run: `cd C:\Users\cccbqn\gushen && .\env\Scripts\python.exe -m pytest tradingagents/strategies/test_akshare_tushare_bridge.py -v`
Expected: PASS（若个别接口列名不匹配，按实际 `df.columns` 修正 mapping 后重跑）

- [ ] **Step 5: 提交**

```bash
cd C:\Users\cccbqn\gushen
git add tradingagents/strategies/
git commit -m "feat: 新增 akshare→tushare 数据桥接层（龟龟策略数据适配）"
```

---


