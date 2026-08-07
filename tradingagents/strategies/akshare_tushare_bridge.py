"""Tushare Pro API 兼容桥接层（akshare 实现，无 token）。

移植自 Turtle_investment_framework（MIT）数据层适配。
所有接口返回 DataFrame，列名对齐 tushare（snake_case 英文字段、A股金额单位=元，
total_mv/circ_mv=万元、daily.amount=千元、vol=手、trade_date/cal_date/end_date=YYYYMMDD）。

数据源与容错（akshare 1.18.x，2026-08 实测；东财域名在当前网络被代理拦截时自动回退）：
- stock_basic       : 沪/深/北交所代码表直拼（code/name/list_date/industry/exchange），
                       北交所域名不可达时 15s 超时保护，不阻塞
- daily_basic       : 单只→雪球快照（含 pe_ttm/pb/total_mv/circ_mv/dv_ttm）；
                      全市场→东方财富 spot_em，失败回退腾讯 spot_tx；
                      支持 trade_date 参数（列值=传入交易日，默认今天）
- fina_indicator    : 新浪财务指标（stock_financial_analysis_indicator）
- income/balancesheet/cashflow : 新浪财务三大表（stock_financial_report_sina）
- dividend          : 巨潮分红（stock_dividend_cninfo，东财接口不可用时兜底）
- weekly/daily      : 东方财富前复权历史（stock_zh_a_hist）→ 失败回退新浪日线
                      （stock_zh_a_daily，周线时重采样 W-FRI）；支持 start_date/end_date
- trade_cal         : 新浪交易日历（tool_trade_date_hist_sina），支持 start_date/end_date
- yc_cb             : 新浪中国国债收益率（bond_gb_zh_sina，10Y 近似）
- pledge_stat       : 巨潮股权质押（stock_cg_equity_mortgage_cninfo，进程级缓存）
- fina_audit        : 无免费批量源，返回带列的空表（龟龟对空表容错）

已知限制（报告已说明）：
1. 全市场 dv_ttm 无低成本免费源（东财无股息率、雪球仅单只、腾讯/新浪快照无）；
   全市场 daily_basic 的 dv_ttm 恒为 None，单只（ts_code=）路径为雪球真值。
   龟龟 Tier1 主通道的 dv_ttm>0 过滤会因此全空，必须在龟龟侧适配（Task 4）对
   dv_ttm 全 None 做降级（例如"dv_ttm 缺失时按 0 参与排名、仅用 pe/pb 主通道"）。
2. 沪市个股 industry 无低成本免费源（东财/同花顺板块接口不可用或过慢），
   深市/北交所 industry 来自交易所代码表，沪市置 None。
3. 东财接口（spot_em/hist/fhps_detail_em）在当前网络被代理拦截时自动回退到
   腾讯/新浪/巨潮数据源，列语义保持一致。

股票代码后缀规则：8/4 开头→BJ，6/9 开头→SH，其余（0/3）→SZ。
"""
import re
import threading
from datetime import datetime

import pandas as pd
import akshare as ak


def _strip_prefix(s):
    """剥离交易所前缀/后缀：'sz000001'->'000001'，'600000.SH'->'600000'"""
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    s = re.sub(r"^(sh|sz|bj)", "", s, flags=re.I)
    s = re.sub(r"\.(sh|sz|bj)$", "", s, flags=re.I)
    return s


def _normalize_ts_code(ts_code):
    """'000001.SZ' / 'sz000001' -> '000001'（ts_code 为空/NaN 时返回 None）"""
    if ts_code is None:
        return None
    s = str(ts_code).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    return _strip_prefix(s.split(".")[0])


def _suffix(code):
    """代码后缀：8/4 开头或 920 段=BJ，6/9 开头=SH，其余（0/3）=SZ；NaN→None"""
    s = _strip_prefix(code)
    if s is None:
        return None
    if s.startswith(("8", "4")) or s.startswith("920"):
        return "BJ"
    if s.startswith(("6", "9")):
        return "SH"
    return "SZ"


def _ts_code_with_suffix(code):
    """'000001'/'sz000001' -> '000001.SZ'（NaN/空返回 None）"""
    s = _strip_prefix(code)
    if s is None:
        return None
    s = s.split(".")[0].zfill(6)
    return f"{s}.{_suffix(s)}"


def _exchange_of(code):
    """tushare 口径交易所：SSE/SZSE/BSE"""
    return {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}.get(_suffix(code))


def _pick(df, mapping):
    """akshare 中文列 -> tushare 英文字段重命名；缺失列置 None。

    mapping 值可为 str（单个列名）或 list[str]（候选列名，取第一个存在的），
    用于兼容新浪对银行/非银企业报表的列名差异。
    """
    out = pd.DataFrame(index=df.index)
    for en, zh in mapping.items():
        if zh is None:
            out[en] = None
        elif isinstance(zh, (list, tuple)):
            col = next((c for c in zh if c in df.columns), None)
            out[en] = df[col] if col is not None else None
        elif zh in df.columns:
            out[en] = df[zh]
        else:
            out[en] = None
    return out


def _trade_date_to_yyyymmdd(s):
    """'2024-01-05' / datetime / '2024-01-05 00:00:00' / '20240105' -> '20240105'（对齐 tushare）"""
    if s is None:
        return None
    if isinstance(s, (pd.Timestamp, datetime)) or hasattr(s, "strftime"):
        return s.strftime("%Y%m%d")
    s = str(s).strip()
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    if re.fullmatch(r"\d{8}", s):
        return s
    return s


def _report_period_to_end_date(s):
    """'2021年报' -> '20211231'，'2021中报'->'20210630' 等；无法解析返回 None"""
    if s is None:
        return None
    m = re.match(r"(\d{4})\s*年(.+)?$", str(s).strip())
    if not m:
        return None
    y = m.group(1)
    q = m.group(2) or ""
    if "中报" in q:
        return y + "0630"
    if "一季报" in q:
        return y + "0331"
    if "三季报" in q:
        return y + "0930"
    return y + "1231"


def _as_num(x):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        f = float(x)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _call_timeout(fn, timeout=20.0):
    """线程超时保护：个别数据源域名（如北交所 bse.cn）在网络受限时阻塞 100s+。

    用 daemon 线程限制等待时长，超时返回 None，由调用方容错（缺失部分数据而非卡死）。
    """
    box = {}

    def runner():
        try:
            box["df"] = fn()
        except Exception:
            pass

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout)
    return box.get("df")


class ProClient:
    """伪装成 ts.pro_api() 的 client（仅 A 股接口，龟龟框架所需子集）。"""

    def __init__(self):
        self._basic_cache = None
        self._cal_cache = None
        self._pledge_cache = None

    # ---------- 基础信息 ----------

    def _stock_basic_df(self):
        if self._basic_cache is not None:
            return self._basic_cache.copy()

        # 代码/名称/list_date/industry 直接取自沪/深/北交易所代码表：
        # 不依赖 ak.stock_info_a_code_name()（其内部固定调用北交所接口，在网络
        # 屏蔽 www.bse.cn 时整表阻塞 100s+）。北交所单独加线程超时保护。
        code2name: dict = {}
        code2listdate: dict = {}
        code2industry: dict = {}
        code2fullname: dict = {}
        # 上交所（主板+科创板）：证券代码/证券简称/证券全称/上市日期（无行业列）
        try:
            sh = ak.stock_info_sh_name_code()
            for c, n, f, d in zip(sh["证券代码"], sh["证券简称"],
                                 sh["证券全称"], sh["上市日期"]):
                c = str(c).strip().zfill(6)
                code2name[c] = str(n)
                code2listdate[c] = _trade_date_to_yyyymmdd(d)
                if str(f) not in ("", "nan"):
                    code2fullname[c] = str(f)
        except Exception:
            pass
        # 深交所：A股代码/A股简称/A股上市日期/所属行业（字母大类，如 "J 金融业"）
        try:
            sz = ak.stock_info_sz_name_code()
            for c, n, d, ind in zip(sz["A股代码"], sz["A股简称"],
                                    sz["A股上市日期"], sz["所属行业"]):
                c = str(c).strip().zfill(6)
                code2name[c] = str(n)
                code2listdate[c] = _trade_date_to_yyyymmdd(d)
                if str(ind) not in ("", "nan"):
                    code2industry[c] = str(ind)
        except Exception:
            pass
        # 北交所：线程超时保护（bse.cn 不可达时 15s 内放弃，仅缺失北交所数据）
        bj = _call_timeout(lambda: ak.stock_info_bj_name_code(), timeout=15.0)
        if bj is not None:
            try:
                for c, n, d, ind in zip(bj["证券代码"], bj["证券简称"],
                                        bj["上市日期"], bj["所属行业"]):
                    c = str(c).strip().zfill(6)
                    code2name[c] = str(n)
                    code2listdate[c] = _trade_date_to_yyyymmdd(d)
                    if str(ind) not in ("", "nan"):
                        code2industry[c] = str(ind)
            except Exception:
                pass

        df = pd.DataFrame({
            "raw_code": list(code2name.keys()),
            "name": list(code2name.values()),
        })
        df["ts_code"] = df["raw_code"].apply(_ts_code_with_suffix)
        df["industry"] = df["raw_code"].map(code2industry)
        df["fullname"] = df["raw_code"].map(code2fullname)
        df["area"] = None
        df["list_date"] = df["raw_code"].map(code2listdate)
        df["exchange"] = df["ts_code"].apply(_exchange_of)
        self._basic_cache = df[
            ["ts_code", "name", "industry", "fullname", "area", "exchange", "list_date"]
        ].reset_index(drop=True)
        return self._basic_cache.copy()

    def stock_basic(self, **kw):
        return self._stock_basic_df()

    # ---------- 交易日历 ----------

    def trade_cal(self, exchange=None, start_date=None, end_date=None, **kw):
        """新浪全市场交易日历；cal_date=YYYYMMDD，is_open=1。exchange 仅接受不报错。"""
        if self._cal_cache is None:
            cal = ak.tool_trade_date_hist_sina()
            self._cal_cache = pd.DataFrame({
                "cal_date": cal["trade_date"].apply(_trade_date_to_yyyymmdd),
                "is_open": 1,
            })
        out = self._cal_cache
        if start_date is not None:
            out = out[out["cal_date"] >= str(start_date)]
        if end_date is not None:
            out = out[out["cal_date"] <= str(end_date)]
        return out.reset_index(drop=True)

    # ---------- 每日指标（估值） ----------

    def daily_basic(self, ts_code=None, trade_date=None, **kw):
        code = _normalize_ts_code(ts_code)
        # 核心要求：trade_date 参数不再被忽略，列值 = 传入交易日（默认今天）
        td = _trade_date_to_yyyymmdd(trade_date) if trade_date is not None \
            else datetime.now().strftime("%Y%m%d")
        if code:
            single = self._daily_basic_single(code, td)
            if single is not None:
                return single
        df = self._daily_basic_market(td)
        if code and not df.empty:
            df = df[df["ts_code"] == _ts_code_with_suffix(code)].reset_index(drop=True)
        return df

    def _daily_basic_single(self, code, trade_date):
        """雪球单只快照：含 pe_ttm/pb/total_mv/circ_mv/dv_ttm/turnover_rate（快、免费）"""
        try:
            raw = ak.stock_individual_spot_xq(symbol=f"{_suffix(code)}{code}")
            d = dict(zip(raw["item"], raw["value"]))
            row = {
                "ts_code": _ts_code_with_suffix(code),
                "trade_date": trade_date or _trade_date_to_yyyymmdd(
                    d.get("时间") or datetime.now()),
                "pe_ttm": _as_num(d.get("市盈率(TTM)")),
                "pb": _as_num(d.get("市净率")),
                # 雪球单位=元 -> tushare 万元
                "total_mv": _as_num(d.get("资产净值/总市值")) / 10000
                if _as_num(d.get("资产净值/总市值")) is not None else None,
                "circ_mv": _as_num(d.get("流通值")) / 10000
                if _as_num(d.get("流通值")) is not None else None,
                "dv_ttm": _as_num(d.get("股息率(TTM)")),
                "turnover_rate": _as_num(d.get("周转率")),
                "close": _as_num(d.get("现价")),
            }
            return pd.DataFrame([row])
        except Exception:
            return None

    def _daily_basic_market(self, trade_date):
        # 1) 东方财富全市场快照（快，含行业等；网络不可用时回退）
        try:
            spot = ak.stock_zh_a_spot_em()
            spot.columns = [str(c).strip() for c in spot.columns]
            out = _pick(spot, {
                "ts_code": "代码", "pe_ttm": "市盈率-动态", "pb": "市净率",
                "total_mv": "总市值", "circ_mv": "流通市值",
                "turnover_rate": "换手率", "close": "最新价",
            })
            out["trade_date"] = trade_date
            out["dv_ttm"] = None
            out["ts_code"] = out["ts_code"].apply(_ts_code_with_suffix)
            # 东财总市值单位=元 -> tushare 万元
            for c in ("total_mv", "circ_mv"):
                out[c] = pd.to_numeric(out[c], errors="coerce") / 10000
            return out
        except Exception:
            pass
        # 2) 腾讯全市场快照（慢但稳定）：pe_ttm/pn(市净率)/zsz(总市值,亿元)/ltsz(流通市值,亿元)
        spot = ak.stock_zh_a_spot_tx()
        out = _pick(spot, {
            "ts_code": "code", "pe_ttm": "pe_ttm", "pb": "pn",
            "total_mv": "zsz", "circ_mv": "ltsz",
            "turnover_rate": "hsl", "close": "zxj",
        })
        out["trade_date"] = trade_date
        out["dv_ttm"] = None
        out["ts_code"] = out["ts_code"].apply(_ts_code_with_suffix)
        # 腾讯总市值单位=亿元 -> tushare 万元（×10000）
        for c in ("total_mv", "circ_mv"):
            out[c] = pd.to_numeric(out[c], errors="coerce") * 10000
        return out

    # ---------- 财务指标 ----------

    def fina_indicator(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "end_date", "roe", "roe_waa", "grossprofit_margin"]
        if not code:
            return pd.DataFrame(columns=cols)
        df = ak.stock_financial_analysis_indicator(symbol=code)
        out = _pick(df, {
            "end_date": "日期",
            "roe": "净资产收益率(%)",
            "roe_waa": "净资产收益率(%)",   # 新浪口径=加权平均净资产收益率
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
            "profit_dedt": "扣除非经常性损益后的净利润(元)",
            # 以下新浪无对应列 -> 置 None（列存在，避免龟龟 KeyError）
            "ebitda": None, "fcff": None, "netdebt": None, "interestdebt": None,
        })
        out["ts_code"] = _ts_code_with_suffix(code)
        out["end_date"] = out["end_date"].apply(_trade_date_to_yyyymmdd)
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
            "revenue": ["营业总收入", "营业收入"],
            "oper_cost": "营业成本",
            "biz_tax_surchg": "营业税金及附加",
            "rd_exp": "研发费用",
            "sell_exp": "销售费用",
            "admin_exp": "管理费用",
            "fin_exp": "财务费用",
            "assets_impair_loss": "资产减值损失",
            "credit_impa_loss": "信用减值损失",
            "invest_income": "投资收益",
            "fv_value_chg_gain": ["公允价值变动收益/(损失)", "公允价值变动收益"],
            "asset_disp_income": "资产处置收益",
            "oth_income": "其他收益",
            "operate_profit": "营业利润",
            "non_oper_income": ["加:营业外收入", "营业外收入"],
            "non_oper_exp": ["减:营业外支出", "营业外支出"],
            "total_profit": "利润总额",
            "income_tax": ["减:所得税", "所得税费用"],
            "n_income": "净利润",
            "n_income_attr_p": ["归属于母公司的净利润", "归属于母公司所有者的净利润"],
            "minority_gain": ["少数股东权益", "少数股东损益"],
            "basic_eps": "基本每股收益",
            "diluted_eps": "稀释每股收益",
        })
        out["ts_code"] = _ts_code_with_suffix(code)
        out["end_date"] = out["end_date"].apply(_trade_date_to_yyyymmdd)
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
            "money_cap": ["货币资金", "现金及存放中央银行款项"],
            "trad_asset": "交易性金融资产",
            "goodwill": "商誉",
            "st_borr": "短期借款",
            "lt_borr": "长期借款",
            "bond_payable": "应付债券",
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
            # 新浪无此列 -> None（龟龟净负债计算会跳过）
            "non_cur_liab_due_1y": None,
        })
        out["ts_code"] = _ts_code_with_suffix(code)
        out["end_date"] = out["end_date"].apply(_trade_date_to_yyyymmdd)
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
            "c_pay_acq_const_fiolta": "购建固定资产、无形资产和其他长期资产支付的现金",
            "c_fr_sale_sg": "销售商品、提供劳务收到的现金",
            "c_pay_goods_sg": "购买商品、接受劳务支付的现金",
            "c_pay_employee": "支付给职工以及为职工支付的现金",
            "c_pay_tax": "支付的各项税费",
            "n_cashflow_inv_act": "投资活动产生的现金流量净额",
            "n_cash_flow_fnc_act": "筹资活动产生的现金流量净额",
            "cash_and_equ_begin": "现金的期初余额",
            "cash_and_equ_end": "现金的期末余额",
            # 新浪现金流量表无折旧摊销拆分 -> None
            "depr_fa_coga_dpba": None,
            "amort_intang_assets": None,
            "lt_amort_deferred_exp": None,
        })
        out["ts_code"] = _ts_code_with_suffix(code)
        out["end_date"] = out["end_date"].apply(_trade_date_to_yyyymmdd)
        return out

    # ---------- 分红送配 ----------

    def dividend(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "end_date", "cash_div_tax", "base_share",
                "record_date", "ex_date", "dv_ttm"]
        if not code:
            return pd.DataFrame(columns=cols)
        try:
            df = ak.stock_dividend_cninfo(symbol=code)
            out = pd.DataFrame(index=df.index)
            out["end_date"] = df["报告时间"].apply(_report_period_to_end_date)
            # 巨潮"派息比例"=每10股派现(元) -> 每股现金分红
            out["cash_div_tax"] = pd.to_numeric(df["派息比例"], errors="coerce") / 10.0
            out["record_date"] = df["股权登记日"].apply(_trade_date_to_yyyymmdd)
            out["ex_date"] = df["除权日"].apply(_trade_date_to_yyyymmdd)
            out["dv_ttm"] = None
            # base_share：雪球总股本(股) -> 万股（对齐 tushare）
            try:
                raw = ak.stock_individual_spot_xq(symbol=f"{_suffix(code)}{code}")
                d = dict(zip(raw["item"], raw["value"]))
                total_share = _as_num(d.get("基金份额/总股本"))
                out["base_share"] = total_share / 10000.0 if total_share else None
            except Exception:
                out["base_share"] = None
            out["ts_code"] = _ts_code_with_suffix(code)
            return out[cols]
        except Exception:
            # 分红数据源偶发不可用：返回空表（保留列），不阻塞策略
            return pd.DataFrame(columns=cols)

    # ---------- 股权质押 / 审计 ----------

    def pledge_stat(self, ts_code=None, **kw):
        """巨潮股权质押（按最近交易日全市场快照，进程内缓存）。

        东财 gpzy 接口在当前网络不可用，故用巨潮接口；无免费的单只质押接口。
        """
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "end_date", "pledge_count", "pledge_ratio"]
        if not code:
            return pd.DataFrame(columns=cols)
        if self._pledge_cache is None:
            try:
                today = datetime.now().strftime("%Y%m%d")
                cal = self.trade_cal(end_date=today)
                date = cal["cal_date"].max() if not cal.empty else today
                df = ak.stock_cg_equity_mortgage_cninfo(date=date)
                out = pd.DataFrame(index=df.index)
                out["ts_code"] = df["股票代码"].apply(_ts_code_with_suffix)
                out["end_date"] = date
                out["pledge_count"] = df["质押数量"]
                out["pledge_ratio"] = pd.to_numeric(
                    df["累计质押占总股本比例"], errors="coerce")
                self._pledge_cache = out[cols]
            except Exception:
                self._pledge_cache = pd.DataFrame(columns=cols)
        out = self._pledge_cache
        if not out.empty:
            out = out[out["ts_code"] == _ts_code_with_suffix(code)].reset_index(drop=True)
        return out

    def fina_audit(self, ts_code=None, **kw):
        """审计意见：无免费批量源 -> 返回带列空表（龟龟对空表容错，不触发重试）。"""
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "end_date", "audit_result"]
        if not code:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(columns=cols)

    # ---------- 国债收益率（无风险利率） ----------

    def yc_cb(self, ts_code=None, curve_type=None, **kw):
        """新浪中国国债收益率（10Y 近似），yield 列=百分数，对齐 tushare yc_cb schema。

        龟龟读取 trade_date/yield 两列；end_date/y1..y10 列存在但置 None。
        """
        cols = ["trade_date", "yield", "end_date", "y1", "y2", "y3", "y5", "y10"]
        try:
            df = ak.bond_gb_zh_sina()
            out = pd.DataFrame({
                "trade_date": df["date"].apply(_trade_date_to_yyyymmdd),
                "yield": pd.to_numeric(df["close"], errors="coerce"),
            })
            for c in ("end_date", "y1", "y2", "y3", "y5", "y10"):
                out[c] = None
            return out[cols]
        except Exception:
            return pd.DataFrame(columns=cols)

    # ---------- 历史行情 ----------

    def _hist(self, code, period, start_date=None, end_date=None):
        """日/周线：优先东方财富前复权，失败回退新浪日线（周线时重采样）。

        单位对齐 tushare：vol=手、amount=千元。
        """
        if start_date is not None:
            start_date = str(start_date)
        if end_date is not None:
            end_date = str(end_date)
        vol_from_shares = False
        try:
            df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq",
                                    start_date=start_date, end_date=end_date)
            out = _pick(df, {
                "trade_date": "日期", "open": "开盘", "high": "最高",
                "low": "最低", "close": "收盘", "vol": "成交量", "amount": "成交额",
            })
            # 东财 vol 已是手，amount 元 -> 千元
        except Exception:
            daily = ak.stock_zh_a_daily(
                symbol=f"{_suffix(code).lower()}{code}",
                start_date=start_date or "19900101",
                end_date=end_date or "21000118",
                adjust="qfq",
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
            vol_from_shares = True  # 新浪 volume 单位=股，需 /100 转手
        if vol_from_shares:
            out["vol"] = pd.to_numeric(out["vol"], errors="coerce") / 100.0
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce") / 1000.0
        out["trade_date"] = out["trade_date"].apply(_trade_date_to_yyyymmdd)
        out["ts_code"] = _ts_code_with_suffix(code)
        out = out.dropna(subset=["trade_date"]).reset_index(drop=True)
        return out

    def weekly(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "trade_date", "close"]
        if not code:
            return pd.DataFrame(columns=cols)
        return self._hist(code, "weekly",
                          start_date=kw.get("start_date"), end_date=kw.get("end_date"))

    def daily(self, ts_code=None, **kw):
        code = _normalize_ts_code(ts_code)
        cols = ["ts_code", "trade_date", "close"]
        if not code:
            return pd.DataFrame(columns=cols)
        return self._hist(code, "daily",
                          start_date=kw.get("start_date"), end_date=kw.get("end_date"))

    def close(self):
        pass


def get_pro_api():
    """返回 tushare pro_api 兼容 client（akshare 实现，无需 token）。"""
    return ProClient()

