# Task 4 报告：龟龟选股器移植 + 前置修复

**状态：DONE_WITH_CONCERNS**　**Commit：0e7f4bf**（`feat: 整合龟龟选股器（Tier1/Tier2，akshare 数据）+ 桥接层兜底`）

---

## 一、移植内容

### 1. 文件
| 文件 | 说明 |
|---|---|
| `tradingagents/strategies/turtle/screener_core.py` | 龟龟选股器核心（原 `scripts/screener_core.py` 复制，保留版权与架构，两阶段 Tier1 批量筛选 + Tier2 逐股深度分析） |
| `tradingagents/strategies/turtle/screener_config.py` | `ScreenerConfig` 配置（复制，未改动） |
| `tradingagents/strategies/turtle/screener_adapter.py` | 适配入口 `run_turtle_screener(tier1_only, tier2_limit) -> dict` |
| `tradingagents/strategies/test_turtle_screener.py` | 3 个测试（2 monkeypatch 逻辑 + 1 真实 Tier1，slow） |
| `app/routers/strategy.py` | 追加 `GET /api/strategy/turtle-screener?tier1_only=true&tier2_limit=10` |
| `tradingagents/strategies/akshare_tushare_bridge.py` | 兜底 + 数值化 + 超时保护（见前置修复） |
| `tradingagents/strategies/__init__.py` | 补文件尾换行 |

### 2. screener_core.py 移植点（数据源从 tushare 官方切到 akshare 桥接层）
- `from config import get_token` 沿用 turtle/ 的 sys.path 方案（config.py 在 turtle/ 下）。
- `__init__`：`self._token = token if token is not None else get_token()` —— 适配器传 `token=""` 时不再触发 `get_token()` 的 RuntimeError。
- `_get_pro()`：`import tushare as ts / ts.pro_api(...)` → `from tradingagents.strategies.akshare_tushare_bridge import get_pro_api; self._pro = get_pro_api()`。
- `_safe_call` 重试分支：`ts.pro_api(timeout=30)` → 重新 `get_pro_api()`。
- Tier1 接口（trade_cal/stock_basic/daily_basic）与 Tier2 接口（pledge_stat/fina_audit/fina_indicator/cashflow/income/yc_cb/dividend/balancesheet/weekly）全部由桥接层覆盖，列名对齐 tushare。

### 3. 适配器
```python
def run_turtle_screener(tier1_only: bool = True, tier2_limit: int | None = None) -> dict:
    from screener_core import TushareScreener
    s = TushareScreener(token="")
    try:
        df = s.run(tier1_only=tier1_only, tier2_limit=tier2_limit)
    except Exception as e:
        return {"error": str(e)}
    records = _clean_nan_inf(df).to_dict("records") if df is not None and not df.empty else []
    return {"candidates": records, "count": len(records)}
```
- `run()` 返回 DataFrame（确认过签名），适配为 `{candidates, count}`；失败 `{error}`。
- 额外加了 `_clean_nan_inf()`：Starlette `JSONResponse` 用 `allow_nan=False`，候选里 object 列的 NaN（沪市 industry/fullname 缺失）和 inf 会导致 `Out of range float values are not JSON compliant` → 500。必须用 `astype(object)` + `df[pd.isnull(df)] = None`（`DataFrame.where(cond, None)` 会把 None 转回 NaN，是坑）。

---

## 二、前置修复（Task 1/3 审查遗留）

### A1. dv_ttm 全 None 降级（screener_core._tier1_filter）
akshare 全市场 daily_basic 无股息率（桥接层 dv_ttm 恒 None）。原逻辑 `dv_ttm.notna() & (dv_ttm > 0)` 会把主通道全部滤空。改为：
```python
dv_series = main_df["dv_ttm"]
if dv_series.notna().any():
    main_df = main_df[dv_series.notna() & (dv_series > 0)].copy()
else:
    print("  [tier1] dv_ttm 全市场缺失（全 None/NaN），跳过股息率>0 过滤")
main_df["channel"] = "main"
```
排名逻辑本身对全 None 安全（`dv_max` 为 NaN → `_dv_norm=0`）。实测真实数据：主通道 1812 只全保留，排名正常。

### A2. 桥接层兜底
- `_daily_basic_market` 腾讯路径：补 try/except，失败返回带列名空表（ts_code/trade_date/close/pe_ttm/pb/total_mv/circ_mv/dv_ttm/turnover_rate）。
- `_hist` 新浪路径：补 try/except，失败返回带列名空表（ts_code/trade_date/open/high/low/close/vol/amount）。
- **额外修复（真实运行发现）**：
  1. 东财/腾讯全市场快照的 pe_ttm/pb/turnover_rate/close 列未转数值（akshare 返回 object/str），导致龟龟 `_tier1_filter` 比较时报 `Invalid comparison between dtype=str and float` → 两条路径统一 `pd.to_numeric(errors="coerce")`。
  2. 东财 `spot_em` 在当前网络被代理拦截时会阻塞挂起、不抛异常（回退失效），腾讯 `spot_tx` 网络波动时也会长时间挂起 → 两条路径都加 `_call_timeout`（EM 20s / TX 100s），超时抛异常走下一路径/空表兜底。

### A3. strategies/__init__.py
补文件尾换行。桥接层 `cols` 变量经核查**全部被使用**（用于空表 `pd.DataFrame(columns=cols)` 与列裁剪），无需删除。

### A4. list_date NaN 掩码（screener_core._tier1_filter）
上市年限过滤改为：
```python
listed = df["list_date"].isna() | (df["list_date"].astype(str) <= cutoff)
df = df[listed].copy()
```
list_date 缺失（NaN/None）的行跳过上市年限条件，不会因 NaN 把股票全滤掉。

---

## 三、测试与端点结果

### 测试
```
cd C:\Users\cccbqn\gushen
.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_turtle_screener.py tradingagents/strategies/test_akshare_tushare_bridge.py -v
```
**16 passed, 2 warnings in 24.68s**（test_turtle_screener 3 个 + test_akshare_tushare_bridge 13 个全绿）。

- `test_tier1_filter_logic_dvttm_degrade`：fake 数据注入 `_tier1_bulk_data`，验证 dv_ttm 全 None 时主通道非空、ST/银行/上市不足/零PB/低换手被滤、list_date=None 行保留、pe NaN 进 observation 通道。
- `test_tier1_filter_logic_dvttm_normal`：dv_ttm 部分有效时按原逻辑过滤（dv=0 被滤出主通道）。
- `test_tier1_runs`（@pytest.mark.slow）：真实全市场 Tier1，断言无 error、candidates 为 list、且 `json.dumps(r, allow_nan=False)` 不抛（防 500）。

### 端点
- 真实 HTTP server（uvicorn app.main:app）**本环境无法启动**：`lifespan` 的 `init_db()` 连不上 MongoDB（本机无 mongod/docker/redis，MongoDB 27017 拒绝连接）会 raise → `Application startup failed`。这是环境前置条件，与本次改动无关。
- 用 `httpx.ASGITransport(app=app)` 驱动完整 FastAPI 路由（不触发 lifespan）验证：
  `GET /api/strategy/turtle-screener?tier1_only=true` → **STATUS=200**，body `{"success":true,"data":{"candidates":[...],"count":150}}`，处理 1.6s。
- 有 MongoDB 的环境启动后端后，`Invoke-WebRequest http://127.0.0.1:8000/api/strategy/turtle-screener?tier1_only=true` 应返回 200（路由/逻辑/序列化均已验证）。

### 真实 Tier1 耗时（开发期实测，TUSHARE_RATE_DELAY=0）
| 阶段 | 耗时 | 说明 |
|---|---|---|
| stock_basic 全市场（交易所代码表） | 33s | 4594 只，写入磁盘缓存（7 天 TTL） |
| daily_basic 全市场（腾讯 spot_tx，东财被拦截） | 55.9s | 5539 只，写入磁盘缓存（当日 TTL）；网络差时曾两次 >2min 超时 |
| run 全流程（缓存命中） | 7.8s | Universe 4594 → filters 1812（main 1812 / obs 0）→ rank&cut 150 |
| ASGI 端点（缓存命中） | 1.6s | 200 |
- 首次完整 Tier1（拉取+筛选）网络好时 ~1.5-2min；网络差时 >5min（标 @pytest.mark.slow 的理由）。缓存后秒级。
- 运行产物 `output/.screener_cache` 未纳入提交。

---

## 四、Concerns
1. **后端启动依赖 MongoDB/Redis**：本环境无法启动真实 HTTP server，端点用 ASGITransport 验证 200（等效验证路由/逻辑/序列化）。请在具备 MongoDB 的环境用 `start_dev.ps1 backend` 启动后做最终 HTTP 确认。
2. **dv_ttm 降级后的排名语义**：主通道实际只用 pe/pb 排名（dv_weight 失效，`_dv_norm=0`），等效权重 pe/pb=0.5/0.5。Tier2 因子（R/EV/floor）仍按原配置权重；若需要股息率维度，需接入单只雪球股息率（成本高，未做）。
3. **全市场 daily_basic 数据源脆弱**：东财被代理拦截、腾讯网络波动时可能空表（候选为空但不报错）。已加 20s/100s 超时兜底。建议后续考虑东财回退源的备选（如 baostock 全市场）。
4. **沪市 industry 部分为 None**（桥接层已知限制）：`include_bank=False` 时沪市银行股（industry=None）不会被"银行"过滤命中——沿用 Task 1/3 已记录的桥接层限制，非本任务引入。
5. **Tier2 未在本次真实跑**：逐股深度分析（financial/obs 质量门 + R/EV/floor）依赖桥接层单只财务接口，adapter 已支持（tier1_only=False），但真实 Tier2 200 只 × 每只数秒会非常慢，建议后续单独验证或加进度回调。
6. `screener_core.py` 保留原 CLI（`python -m screener_core`），直接跑会走 `get_token()`（无 token 报错）；适配器传 `token=""` 不受影响。
