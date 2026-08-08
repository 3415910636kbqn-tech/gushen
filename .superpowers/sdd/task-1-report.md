# Task 1 报告：akshare→tushare 数据桥接层

## 状态
DONE

## 交付物（commit 399b536c35269c8da13508fcfd32d208aa3a5846）
- `tradingagents/strategies/__init__.py` — 策略包导出 `ProClient` / `get_pro_api`
- `tradingagents/strategies/akshare_tushare_bridge.py` — 桥接层主体
- `tradingagents/strategies/test_akshare_tushare_bridge.py` — 8 个列存在性测试

## 做了什么
按 TDD 流程：先写测试 → 确认红态（ModuleNotFoundError）→ 实现 → 全绿 → 提交。

实现前先对 akshare 1.18.83 各接口做了实际列名诊断，据此设计接口与列映射：

| tushare 接口 | akshare 数据源 | 关键字段映射 | 容错 |
|---|---|---|---|
| stock_basic | 新浪 `stock_info_a_code_name` | code→ts_code（6/9→SH，0/3→SZ），name；industry/fullname/area/list_date 置空列 | 无 |
| daily_basic | 雪球单只 `stock_individual_spot_xq` → 东财 `stock_zh_a_spot_em` → 腾讯 `stock_zh_a_spot_tx` | 市盈率(TTM)/pe_ttm、市净率→pb、资产净值/总市值→total_mv、股息率(TTM)→dv_ttm、周转率→turnover_rate | 三级 fallback |
| fina_indicator | 新浪 `stock_financial_analysis_indicator` | 日期→end_date、净资产收益率(%)→roe、销售毛利率(%)→grossprofit_margin | — |
| income | 新浪 `stock_financial_report_sina`(利润表) | 报告日→end_date、营业收入→revenue、净利润→n_income，另映射 17 个龟龟所需字段 | — |
| balancesheet | 新浪（资产负债表） | 资产总计→total_assets、负债合计→total_liab、货币资金→money_cap（银行股缺失置 None） | — |
| cashflow | 新浪（现金流量表） | 经营活动产生的现金流量净额→n_cashflow_act | — |
| dividend | 东财 `stock_fhps_detail_em` | 报告期→end_date、现金分红-现金分红比例→cash_div_tax、股息率→dv_ttm | 接口失败返回空表（保留列） |
| weekly/daily | 东财 `stock_zh_a_hist`(qfq) → 新浪 `stock_zh_a_daily`(qfq) | 日期→trade_date(YYYYMMDD)、开盘/收盘/最高/最低、成交量→vol(手)、成交额→amount | 东财失败回退新浪，周线重采样 |

统一约定：`trade_date` 转 tushare 的 `YYYYMMDD` 格式；金额单位=元（total_mv 直接取雪球/东财元值）；`ts_code` 带 .SH/.SZ 后缀。

## 测试命令与结果
```
cd C:\Users\cccbqn\gushen && .\env\Scripts\python.exe -m pytest tradingagents/strategies/test_akshare_tushare_bridge.py -v
```
结果：**8 passed in 42.48s**（真实联网调用 akshare，无失败、无需二次调整 mapping）。

补充验证：daily_basic 返回真实估值（pe_ttm=5.043 / pb=0.468 / total_mv≈2171.5亿 / dv_ttm=5.326）；weekly 返回 1258 行且 trade_date 可排序；daily 含 high/low/vol/amount（龟龟 `financials.py` 依赖）；新浪 fallback 周线重采样逻辑验证正确。

## 偏差与说明
1. **venv 缺 pytest**：已 `pip install pytest`（9.1.1），仅环境准备，未改项目文件。
2. **daily_basic 数据源与原骨架不同**：骨架用东财 `stock_zh_a_spot_em` 全市场快照；实测当前代理环境下东财接口时好时坏（ProxyError），且东财无股息率列。故单只查询优先雪球（含 `dv_ttm`，快），失败依次回退东财/腾讯全市场。
3. **weekly/daily 增加新浪回退**：东财 `stock_zh_a_hist` 在当前网络偶发 ProxyError；新浪 `stock_zh_a_daily` 稳定，作为回退源（周线时对日线做 W-FRI 重采样；新浪成交量单位股，已 ÷100 转手对齐 tushare）。
4. **stock_basic 的 industry 等列置 None**：新浪代码表仅含 code/name，无行业/全称/上市日期；逐只拉行业不现实。测试仅断言列存在。龟龟代码用 `row.get(...)` 访问，None 安全。
5. **trade_date 统一为 YYYYMMDD**：tushare 原生格式，保证龟龟 `sort_values("trade_date")` 排序正确（东财返回 "2024-01-05"、新浪返回 datetime，均已归一化）。
6. **雪球 item/value 形态**：`stock_individual_spot_xq` 返回 (37,2) item/value 表，已转 dict 后取值。
7. 仅修改了 `tradingagents/strategies/` 下 3 个文件；未跟踪部署文件（serve_prod.py、start_gushen.ps1 等）未提交；`.gitignore` 已忽略 `__pycache__`。

## 后续任务衔接
桥接层是龟龟数据层的 drop-in 替代：`get_pro_api()` 返回的 client 可传给龟龟的 TushareDataCollector 等数据收集器（若其内部是 `ts.pro_api()` 则需在龟龟侧改为传入本 client，见后续 task）。

---

## Task 1 审查修复记录（2026-08-08）

审查发现桥接层会让龟龟选股器/估值器输出错误或崩溃，本轮逐项修复。测试从 8 个补强到 13 个（含列 notna 与数据语义断言），**13 passed**。

### 数据源环境实测结论（决定修复方案的前提）
当前网络环境下：东财全部域名被代理拦截（`stock_zh_a_spot_em`/`stock_zh_a_hist`/`stock_fhps_detail_em`/`stock_individual_info_em` 全部 ProxyError）；**北交所官网 www.bse.cn 读取超时 ~103s**（`ak.stock_info_a_code_name` 内嵌北交所调用，会整表阻塞——已重构为沪深代码表直拼 + 北交所线程 15s 超时保护）；新浪 finance.sina.com.cn 连续请求被服务端限速（第 3 次起 6s→20s+）。腾讯/雪球/巨潮可用。
- 全市场估值快照：仅腾讯 `stock_zh_a_spot_tx` 可用（含 pe_ttm/pn/zsz/ltsz/hsl，**无股息率**）；新浪全市场 spot 无 PE/PB；雪球仅单只。
- akshare 1.18.83 无 `stock_zh_a_spot_xq`、无 `stock_a_indicator_lg`（任务文本提到的接口不存在）。
- 全市场个股股息率（dv_ttm）在免费 akshare 接口中**无低成本来源**。

### 【Critical】修复明细
1. **测试补强**：每个财务/行情接口测试补 `len(df)>0` 与核心列 `df[col].notna().any()` 断言——income.revenue、balancesheet.total_assets、cashflow.n_cashflow_act、fina_indicator.roe/roe_waa、daily_basic.pe_ttm/pb/total_mv、weekly.close 均真实有值。另补 end_date 必须为 `YYYYMMDD`（龟龟用 `str.endswith("1231")` 筛年报，原实现 fina_indicator 的 end_date 是 `2026-03-31` 格式导致年报筛选失效）。
2. **daily_basic 支持 trade_date**：`trade_date` 参数不再被忽略，返回列 `trade_date`=传入交易日（默认今天）。龟龟 `_tier1_bulk_data` 用 `daily_basic(trade_date=最新交易日)` 拿全市场快照，列值对齐传入日。若传入过去交易日，仍返回当日实时快照近似值（任务允许的务实方案），列上标注该交易日。
3. **dv_ttm**：全市场无低成本股息率源（东财无、腾讯/新浪快照无、雪球仅单只、乐咕接口不存在），全市场 `dv_ttm` 如实置 None；单只（ts_code=）路径从雪球取真值（如 600519 dv_ttm=3.974）。**必须在龟龟侧（Task 4）对主通道 dv_ttm 过滤降级**：`_tier1_filter` 第 308 行 `main_df["dv_ttm"].notna() & (dv_ttm>0)` 会因全 None 而把主通道清空 → 改为"dv_ttm 全 None 时跳过该过滤、仅用 pe/pb 主通道"（原则：Tier1 主通道不能全空）。本任务在模块 docstring 已注明该约束与建议。
4. **stock_basic 补 list_date/industry**：list_date 用沪/深/北交易所代码表批量补全（`stock_info_sh_name_code`+`stock_info_sz_name_code`+`stock_info_bj_name_code`），覆盖 4927/5539；industry 用深交所（字母大类）与北交所（细分行业）代码表，沪市无低成本源置 None。`exchange` 改为 tushare 口径 SSE/SZSE/BSE。
5. **total_mv 单位=万元**：雪球（元→÷10000）、腾讯（亿元→×10000）、东财（元→÷10000）统一为 tushare 万元口径；补 `circ_mv`（流通市值，龟龟 fields 请求含它，原实现缺失）。测试断言平安银行 total_mv≈21715200 万元（≈2171 亿）。

### 【Important】修复明细
6. **补接口**：
   - `trade_cal`：新浪 `tool_trade_date_hist_sina`，返回 `cal_date`(YYYYMMDD)/`is_open=1`，支持 exchange（忽略）/start_date/end_date 过滤；龟龟 `_get_latest_trade_date` 正常取到最新交易日。
   - `yc_cb`：新浪 `bond_gb_zh_sina`（10Y 国债收益率），返回 `trade_date`/`yield`（百分数）+ end_date/y1..y10 None 列；龟龟 Rf/II 计算有真实值（当前 ≈1.70%）。
   - `pledge_stat`：巨潮 `stock_cg_equity_mortgage_cninfo(date=最近交易日)` 全市场快照（进程内缓存），按 ts_code 过滤，`pledge_ratio`=累计质押占总股本比例、`end_date`=交易日；失败返回空表。
   - `fina_audit`：无免费源，返回带列空表（ts_code/end_date/audit_result），龟龟 `_check_hard_vetoes` 对空表容错，不崩溃不重试。
7. **财务字段补充**：cashflow 补 `c_pay_acq_const_fiolta`（购建固定资产…支付的现金，龟龟 FCF 计算核心）；income 补 `fin_exp/sell_exp/admin_exp/non_oper_income/non_oper_exp/oth_income`；balancesheet 补 `trad_asset/goodwill/st_borr/lt_borr/bond_payable`；fina_indicator 补 `roe_waa`（=新浪净资产收益率(加权口径)）、`profit_dedt`（扣非净利润）、`netdebt/ebitda/fcff/interestdebt`（无源置 None，列存在避免 KeyError）。同时修复银行/非银报表列名差异：用候选列名列表映射（如 归属于母公司的净利润/归属于母公司所有者的净利润、加:营业外收入/营业外收入、减:所得税/所得税费用）。
8. **daily/weekly 尊重 start_date/end_date**：透传给东财 `stock_zh_a_hist` 与新浪 `stock_zh_a_daily`（YYYYMMDD）。
9. **单位/格式归一**：daily.amount=千元（新浪元÷1000、东财元÷1000）、vol=手（新浪股÷100、东财已是手）；dividend 的 record_date/ex_date 归一 YYYYMMDD、end_date 由"报告时间"（如 `2021年报`）解析为 `20211231`；stock_basic.exchange 用 SSE/SZSE。

### Minor 修复
- `_suffix`：8/4 开头与 **920 段**归 BJ（北交所新代码段以 9 开头，需先于 SH 判断）；NaN/空输入返回 None，不产生 `nan.SZ`。
- 文件末尾补换行。
- **代码前缀归一化（测试发现的崩溃级 bug）**：腾讯快照 code 带 `sh/sz/bj` 前缀（如 `sz000001`），原实现会生成 `sz000001.SZ`，导致 stock_basic 与 daily_basic 按 ts_code merge 后 **0 行**（龟龟 Tier1 直接空结果）。新增 `_strip_prefix` 统一剥离前缀，并加 `test_daily_basic_trade_date_and_tier1_merge` 回归测试（merge >3000 行）。

### 测试策略（应对网络限制）
受 bse.cn 不可达与新浪连续请求限速影响，以下数据源的**映射逻辑测试**改用假数据（monkeypatch）验证，真实数据在实现阶段已探测确认：北交所/沪深交易所代码表补全（真实覆盖率 4927/5539）、腾讯全市场快照（真实 5539 只含 PE/PB/市值）、巨潮质押映射、新浪日线的 start/end 过滤与单位换算、巨潮分红映射（真实 000001 共 28 条）。
**六个核心接口保留真实数据断言**（任务要求）：income.revenue、balancesheet.total_assets、cashflow.n_cashflow_act、fina_indicator.roe/roe_waa、daily_basic.pe_ttm/pb/total_mv（雪球）、weekly.close（新浪日线）；另有真实新浪国债收益率（yc_cb）、新浪日历（trade_cal）。

### 测试结果
```
.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_akshare_tushare_bridge.py -v
13 passed in 79.70s（EXIT=0，2026-08-08 实测）
```
全量完整运行通过（墙钟 82s）。此前完整运行记录：13 passed 112.86s / 8 passed 42.48s。

### 龟龟侧 Task 4 必须处理（本任务已尽桥接层之责）
1. `_tier1_filter` dv_ttm 主通道过滤降级（见 Critical 3）。
2. `_tier1_filter` `df[df["list_date"] <= cutoff]`：list_date 缺失（NaN）时 pandas 布尔掩码会抛错，需 `fillna("99991231")` 或 dropna。
3. 沪市 industry=None：`df[df["industry"] != "银行"]` 对 NaN 保留该行，include_bank=False 时沪市银行无法排除（可接受或由 Task 4 用行业补全）。
4. `dividend.base_share` 已从雪球总股本(股→万股)填充；若雪球失败为 None，龟龟 `_extract_factor2_metrics` 会跳过该年（不崩溃，因子 2 的 M 可能为 None）。
