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