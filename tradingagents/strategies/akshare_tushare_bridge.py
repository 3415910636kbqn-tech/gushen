"""Tushare Pro API 兼容桥接层（akshare 实现，无 token）。

移植自 Turtle_investment_framework（MIT）数据层适配。
所有接口返回 DataFrame，列名对齐 tushare（snake_case 英文字段、A股金额单位=元）。

数据源与容错（akshare 1.18.x，2026-08 实测）：
- stock_basic       : 新浪全市场 A 股代码/名称（stock_info_a_code_name）
- daily_basic       : 单只→雪球快照（含 pe_ttm/pb/total_mv/dv_ttm）；
                      全市场→东方财富 spot_em，失败回退腾讯 spot_tx
- fina_indicator    : 新浪财务指标（stock_financial_analysis_indicator）
- income/balancesheet/cashflow : 新浪财务三大表（stock_financial_report_sina）
- dividend          : 东方财富分红送配（stock_fhps_detail_em，偶发不可用→空表）
- weekly/daily      : 东方财富前复权历史（stock_zh_a_hist），失败回退新浪日线
                      （stock_zh_a_daily，周线时重采样）
股票代码后缀规则（简化）：6/9 开头→SH，其余（0/3）→SZ。
"""
import re
from datetime import datetime

import pandas as pd
import akshare as ak


def _normalize_ts_code(ts_code):
    """'000001.SZ' -> '000001'（ts_code 为空时返回 None）"""
    if not ts_code:
        return None
    return str(ts_code).split(".")[0]


def _suffix(code):
    """简化后缀规则：6/9 开头=SH，0/3 开头=SZ"""
    code = str(code)
    if code.startswith(("6", "9")):
        return "SH"
    return "SZ"


def _ts_code_with_suffix(code):
    code = str(code).zfill(6)
    return f"{code}.{_suffix(code)}"


def _pick(df, mapping):
    """akshare 中文列 -> tushare 英文字段重命名；缺失列置 None"""
    out = pd.DataFrame(index=df.index)
    for en, zh in mapping.items():
        if zh is None:
            out[en] = None
        elif zh in df.columns:
            out[en] = df[zh]
        else:
            out[en] = None
    return out


def _trade_date_to_yyyymmdd(s):
    """'2024-01-05' / datetime / '2024-01-05 00:00:00' -> '20240105'（对齐 tushare）"""
    if s is None:
        return None
    if isinstance(s, pd.Timestamp) or hasattr(s, "strftime"):
        return s.strftime("%Y%m%d")
    s = str(s).strip()
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    return s


def _as_num(x):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        f = float(x)
        return f
    except (TypeError, ValueError):
        return None


class ProClient:
    """伪装成 ts.pro_api() 的 client（仅 A 股接口，龟龟框架所需子集）。"""

    def __init__(self):
        self._basic_cache = None

    # ---------- 基础信息 ----------

    def _stock_basic_df(self):
        if self._basic_cache is None:
            df = ak.stock_info_a_code_name()
            df = df.rename(columns={"code": "raw_code", "name": "name"})
            df["ts_code"] = df["raw_code"].apply(_ts_code_with_suffix)
            df["name"] = df["name"].astype(str)
            # 新浪代码表不含行业/全称/上市日期：置空列以对齐 tushare schema
            df["industry"] = None
            df["fullname"] = None
            df["area"] = None
            df["list_date"] = None
            df["exchange"] = df["ts_code"].apply(lambda c: c.split(".")[1])
            self._basic_cache = df[
                ["ts_code", "name", "industry", "fullname", "area", "exchange", "list_date"]
            ].reset_index(drop=True)
        return self._basic_cache.copy()

    def stock_basic(self, **kw):
        return self._stock_basic_df()

    # ---------- 每日指标（估值） ----------

    def daily_basic(self, ts_code=None, trade_date=None, **kw):
        code = _normalize_ts_code(ts_code)
        if code:
            single = self._daily_basic_single(code)
            if single is not None:
                return single
        df = self._daily_basic_market()
        if code and not df.empty:
            df = df[df["ts_code"] == _ts_code_with_suffix(code)].reset_index(drop=True)
        return df

    def _daily_basic_single(self, code):
        """雪球单只快照：含 pe_ttm/pb/total_mv/dv_ttm/turnover_rate（快、免费）"""
        try:
            raw = ak.stock_individual_spot_xq(symbol=f"{_suffix(code)}{code}")
            d = dict(zip(raw["item"], raw["value"]))
            row = {
                "ts_code": _ts_code_with_suffix(code),
                "trade_date": _trade_date_to_yyyymmdd(d.get("时间") or datetime.now()),
                "pe_ttm": _as_num(d.get("市盈率(TTM)")),
                "pb": _as_num(d.get("市净率")),
                "total_mv": _as_num(d.get("资产净值/总市值")),
                "dv_ttm": _as_num(d.get("股息率(TTM)")),
                "turnover_rate": _as_num(d.get("周转率")),
                "close": _as_num(d.get("现价")),
            }
            return pd.DataFrame([row])
        except Exception:
            return None

    def _daily_basic_market(self):
        today = datetime.now().strftime("%Y%m%d")
        # 1) 东方财富全市场快照（快）
        try:
            spot = ak.stock_zh_a_spot_em()
            spot.columns = [str(c).strip() for c in spot.columns]
            out = _pick(spot, {
                "ts_code": "代码", "pe_ttm": "市盈率-动态", "pb": "市净率",
                "total_mv": "总市值", "turnover_rate": "换手率", "close": "最新价",
            })
            out["trade_date"] = today
            out["dv_ttm"] = None
            out["ts_code"] = out["ts_code"].apply(_ts_code_with_suffix)
            return out
        except Exception:
            pass
        # 2) 腾讯全市场快照（慢但稳定）：pe_ttm/pn(市净率)/zsz(总市值)
        spot = ak.stock_zh_a_spot_tx()
        out = _pick(spot, {
            "ts_code": "code", "pe_ttm": "pe_ttm", "pb": "pn",
            "total_mv": "zsz", "turnover_rate": "hsl", "close": "zxj",
        })
        out["trade_date"] = today
        out["dv_ttm"] = None
        out["ts_code"] = out["ts_code"].apply(_ts_code_with_suffix)
        return out

    # ---------- 财务指标 ----------

    def fina_indicator(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "end_date", "roe", "grossprofit_margin"]
        if not code:
            return pd.DataFrame(columns=cols)
        df = ak.stock_financial_analysis_indicator(symbol=code)
        out = _pick(df, {
            "end_date": "日期",
            "roe": "净资产收益率(%)",
            "grossprofit_margin": "销售毛利率(%)",
            "netprofit_margin": "销售净利率(%)",
            "debt_to_assets": "资产负债率(%)",
            "or_yoy": "主营业务收入增长率(%)",
            "netprofit_yoy": "净利润增长率(%)",
            "assets_turn": "总资产周转率(次)",
            "ocfps": "每股经营性现金流(元)",
            "basic_eps": "加权每股收益(元)",
            "bps": "每股净资产_调整前(元)",
            "total_assets": "总资产(元)",
        })
        out["ts_code"] = _ts_code_with_suffix(code)
        return out

    # ---------- 利润表 ----------

    def income(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "end_date", "revenue", "n_income"]
        if not code:
            return pd.DataFrame(columns=cols)
        df = ak.stock_financial_report_sina(stock=code, symbol="利润表")
        out = _pick(df, {
            "end_date": "报告日",
            "revenue": "营业收入",
            "oper_cost": "营业成本",
            "biz_tax_surchg": "营业税金及附加",
            "rd_exp": "研发费用",
            "assets_impair_loss": "资产减值损失",
            "credit_impa_loss": "信用减值损失",
            "invest_income": "投资收益",
            "fv_value_chg_gain": "公允价值变动收益/(损失)",
            "asset_disp_income": "资产处置收益",
            "operate_profit": "营业利润",
            "total_profit": "利润总额",
            "income_tax": "减:所得税",
            "n_income": "净利润",
            "n_income_attr_p": "归属于母公司的净利润",
            "minority_gain": "少数股东权益",
            "basic_eps": "基本每股收益",
            "diluted_eps": "稀释每股收益",
        })
        out["ts_code"] = _ts_code_with_suffix(code)
        return out

    # ---------- 资产负债表 ----------

    def balancesheet(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "end_date", "total_assets", "total_liab", "money_cap"]
        if not code:
            return pd.DataFrame(columns=cols)
        df = ak.stock_financial_report_sina(stock=code, symbol="资产负债表")
        out = _pick(df, {
            "end_date": "报告日",
            "total_assets": "资产总计",
            "total_liab": "负债合计",
            "money_cap": "货币资金",
            "inventory": "存货",
            "accounts_receiv": "应收账款",
            "notes_receiv": "应收票据",
            "prepayment": "预付账款",
            "fix_assets": "固定资产净额",
            "total_share": "股本",
            "cap_rese": "资本公积",
            "surplus_rese": "盈余公积",
            "undistr_porfit": "未分配利润",
            "oth_eq_inc": "其他综合收益",
            "total_hldr_eqy_exc_min_int": "归属于母公司股东的权益",
            "minority_int": "少数股东权益",
            "total_hldr_eqy": "股东权益",
            "liab_and_hldr_eqy": "负债及股东权益总计",
        })
        out["ts_code"] = _ts_code_with_suffix(code)
        return out

    # ---------- 现金流量表 ----------

    def cashflow(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "end_date", "n_cashflow_act"]
        if not code:
            return pd.DataFrame(columns=cols)
        df = ak.stock_financial_report_sina(stock=code, symbol="现金流量表")
        out = _pick(df, {
            "end_date": "报告日",
            "n_cashflow_act": "经营活动产生的现金流量净额",
            "c_fr_sale_sg": "销售商品、提供劳务收到的现金",
            "c_pay_goods_sg": "购买商品、接受劳务支付的现金",
            "c_pay_employee": "支付给职工以及为职工支付的现金",
            "c_pay_tax": "支付的各项税费",
            "n_cashflow_inv_act": "投资活动产生的现金流量净额",
            "n_cash_flow_fnc_act": "筹资活动产生的现金流量净额",
            "cash_and_equ_begin": "现金的期初余额",
            "cash_and_equ_end": "现金的期末余额",
        })
        out["ts_code"] = _ts_code_with_suffix(code)
        return out

    # ---------- 分红送配 ----------

    def dividend(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "end_date", "cash_div_tax"]
        if not code:
            return pd.DataFrame(columns=cols)
        try:
            df = ak.stock_fhps_detail_em(symbol=code)
            out = _pick(df, {
                "end_date": "报告期",
                "cash_div_tax": "现金分红-现金分红比例",
                "dv_ttm": "现金分红-股息率",
                "record_date": "股权登记日",
                "ex_date": "除权除息日",
            })
            out["ts_code"] = _ts_code_with_suffix(code)
            return out
        except Exception:
            # 东财分红接口偶发不可用：返回空表（保留列），不阻塞策略
            return pd.DataFrame(columns=cols)

    # ---------- 历史行情 ----------

    def _hist(self, code, period):
        """日/周线：优先东方财富前复权，失败回退新浪日线（周线时重采样）"""
        try:
            df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
            out = _pick(df, {
                "trade_date": "日期", "open": "开盘", "high": "最高",
                "low": "最低", "close": "收盘", "vol": "成交量", "amount": "成交额",
            })
        except Exception:
            daily = ak.stock_zh_a_daily(
                symbol=f"{_suffix(code).lower()}{code}", adjust="qfq"
            )
            daily["date"] = pd.to_datetime(daily["date"])
            if period == "weekly":
                daily = daily.set_index("date").resample("W-FRI").agg({
                    "open": "first", "high": "max", "low": "min",
                    "close": "last", "volume": "sum", "amount": "sum",
                }).dropna().reset_index()
            out = _pick(daily, {
                "trade_date": "date", "open": "open", "high": "high",
                "low": "low", "close": "close", "vol": "volume", "amount": "amount",
            })
            if "vol" in out.columns:
                out["vol"] = out["vol"] / 100.0  # 股 -> 手（对齐 tushare 单位）
        out["trade_date"] = out["trade_date"].apply(_trade_date_to_yyyymmdd)
        out["ts_code"] = _ts_code_with_suffix(code)
        out = out.dropna(subset=["trade_date"]).reset_index(drop=True)
        return out

    def weekly(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "trade_date", "close"]
        if not code:
            return pd.DataFrame(columns=cols)
        return self._hist(code, "weekly")

    def daily(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "trade_date", "close"]
        if not code:
            return pd.DataFrame(columns=cols)
        return self._hist(code, "daily")

    def close(self):
        pass


def get_pro_api():
    """返回 tushare pro_api 兼容 client（akshare 实现，无需 token）。"""
    return ProClient()