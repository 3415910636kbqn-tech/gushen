"""akshare→tushare 桥接层测试（龟龟框架兼容性回归）。

补强点（Task 1 审查）：
- 每个财务/行情接口补 len(df)>0 与核心列 notna().any() 断言
- daily_basic 支持 trade_date 参数（列值=传入交易日）
- total_mv 单位=万元、daily.amount=千元
- trade_cal/yc_cb/pledge_stat/fina_audit 补接口列
- 代码后缀 8/4→BJ，NaN 不产生 nan.*
"""
import pytest

from tradingagents.strategies.akshare_tushare_bridge import (
    _suffix,
    _ts_code_with_suffix,
    get_pro_api,
)


@pytest.fixture(scope="module")
def pro():
    return get_pro_api()


# ---------- 基础信息 ----------

def test_stock_basic_columns(pro):
    df = pro.stock_basic()
    assert {"ts_code", "name", "industry", "fullname", "area",
            "exchange", "list_date"}.issubset(df.columns)
    assert len(df) > 3000
    # 上市日期：沪/深/北交易所代码表补全后应覆盖绝大多数个股
    assert df["list_date"].notna().sum() > 3000
    # 交易所口径 SSE/SZSE/BSE
    assert df["exchange"].dropna().isin(["SSE", "SZSE", "BSE"]).all()
    assert df["ts_code"].str.endswith((".SH", ".SZ", ".BJ")).all()


def test_suffix_and_ts_code():
    assert _suffix("920000") == "BJ"
    assert _suffix("430047") == "BJ"
    assert _suffix("600000") == "SH"
    assert _suffix("900901") == "SH"
    assert _suffix("000001") == "SZ"
    assert _suffix("300750") == "SZ"
    assert _suffix(None) is None
    assert _suffix(float("nan")) is None
    assert _ts_code_with_suffix(None) is None
    assert _ts_code_with_suffix("920000") == "920000.BJ"
    assert _ts_code_with_suffix(float("nan")) is None


# ---------- 每日指标 ----------

def test_daily_basic_columns(pro):
    df = pro.daily_basic(ts_code="000001.SZ")
    assert {"ts_code", "trade_date", "pe_ttm", "pb", "total_mv",
            "dv_ttm", "circ_mv", "turnover_rate", "close"}.issubset(df.columns)
    assert len(df) > 0
    # 雪球单只含真实估值：PE/PB/总市值 必须有值
    assert df["pe_ttm"].notna().any()
    assert df["pb"].notna().any()
    assert df["total_mv"].notna().any()
    # total_mv 单位=万元：平安银行总市值约 2170 亿元 ≈ 2.17e7 万元
    mv = df.iloc[0]["total_mv"]
    assert 1e5 < mv < 1e9, f"total_mv 应为单位万元（实际 {mv}）"


def test_daily_basic_trade_date_and_tier1_merge(pro):
    # 龟龟 Tier1 主通道用 daily_basic(trade_date=最新交易日)：列值必须=传入交易日
    df = pro.daily_basic(trade_date="20250103")
    assert len(df) > 0
    assert (df["trade_date"] == "20250103").all()
    # 回归保护：stock_basic 与 daily_basic(trade_date=) 必须能按 ts_code 合并。
    # 腾讯快照 code 带 sh/sz/bj 前缀，桥接层必须归一化为纯数字+后缀。
    sb = pro.stock_basic()
    merged = sb.merge(df, on="ts_code", how="inner")
    assert len(merged) > 3000, "Tier1 merge 不应为空（代码前缀归一化失败）"


# ---------- 财务三表 ----------

def test_fina_indicator_columns(pro):
    df = pro.fina_indicator(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "roe", "roe_waa", "grossprofit_margin",
            "debt_to_assets", "profit_dedt"}.issubset(df.columns)
    assert len(df) > 0
    assert df["roe"].notna().any()
    assert df["roe_waa"].notna().any()
    # end_date 必须为 YYYYMMDD（龟龟用 str.endswith("1231") 筛年报）
    assert df["end_date"].dropna().str.fullmatch(r"\d{8}").all()


def test_income_columns(pro):
    df = pro.income(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "revenue", "n_income",
            "fin_exp", "sell_exp", "admin_exp",
            "non_oper_income", "non_oper_exp", "oth_income"}.issubset(df.columns)
    assert len(df) > 0
    assert df["revenue"].notna().any()


def test_balancesheet_columns(pro):
    df = pro.balancesheet(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "total_assets", "total_liab", "money_cap",
            "trad_asset", "goodwill", "st_borr", "lt_borr", "bond_payable"}.issubset(df.columns)
    assert len(df) > 0
    assert df["total_assets"].notna().any()


def test_cashflow_columns(pro):
    df = pro.cashflow(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "n_cashflow_act",
            "c_pay_acq_const_fiolta"}.issubset(df.columns)
    assert len(df) > 0
    assert df["n_cashflow_act"].notna().any()


def test_dividend_columns(pro):
    df = pro.dividend(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "cash_div_tax", "base_share",
            "record_date", "ex_date", "dv_ttm"}.issubset(df.columns)
    assert len(df) > 0
    # 日期列归一化 YYYYMMDD
    for c in ("record_date", "ex_date"):
        vals = df[c].dropna()
        if not vals.empty:
            assert vals.str.fullmatch(r"\d{8}").all()


# ---------- 历史行情 ----------

def test_weekly_columns(pro):
    df = pro.weekly(ts_code="000001.SZ")
    assert {"ts_code", "trade_date", "close"}.issubset(df.columns)
    assert len(df) > 0
    assert df["close"].notna().any()
    assert df["trade_date"].dropna().str.fullmatch(r"\d{8}").all()


def test_daily_period_with_dates(pro):
    # 龟龟 get_market_data 用 daily(start_date, end_date) 取近一年行情
    df = pro.daily(ts_code="000001.SZ", start_date="20240101", end_date="20240301")
    assert len(df) > 0
    assert (df["trade_date"] >= "20240101").all()
    assert (df["trade_date"] <= "20240301").all()
    # amount 单位=千元（对齐 tushare；新浪口径为元 → /1000）
    assert df["amount"].notna().any()


# ---------- 补充接口 ----------

def test_trade_cal(pro):
    df = pro.trade_cal(exchange="SSE", start_date="20240101", end_date="20240131")
    assert {"cal_date", "is_open"}.issubset(df.columns)
    assert len(df) > 0
    assert (df["is_open"] == 1).all()
    assert (df["cal_date"] >= "20240101").all()
    assert (df["cal_date"] <= "20240131").all()


def test_extra_endpoints(pro):
    yc = pro.yc_cb(ts_code=None, curve_type="0")
    assert {"trade_date", "yield", "end_date", "y1", "y2", "y3", "y5", "y10"}.issubset(yc.columns)
    ps = pro.pledge_stat(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "pledge_count", "pledge_ratio"}.issubset(ps.columns)
    fa = pro.fina_audit(ts_code="000001.SZ")
    assert {"ts_code", "end_date", "audit_result"}.issubset(fa.columns)

