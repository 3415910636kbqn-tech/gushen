# Task 3 报告：龟龟估值引擎移植

**状态**: DONE_WITH_CONCERNS
**Commit**: `0a39ff1`（17 files changed, 7583 insertions, 1 deletion）

## 一、移植了什么

目标目录 `tradingagents/strategies/turtle/`（龟龟源码副本，保持原相对导入）：
- `config.py`            — 原样复制（`get_token` 可抛 RuntimeError，`validate_stock_code` 保留；默认 .env 无 TUSHARE_API_URL，vip 分支不触发）
- `format_utils.py`      — 原样复制（任务清单未列，但被 tushare_collector/valuation_engine import，必需）
- `cache_utils.py`       — 原样复制（`ScreenerCache`，TTL 缓存基础设施，被 `_get_ttl_cache()` 懒加载）
- `tushare_collector.py` — 复制 + 数据源替换（详见下）
- `tushare_modules/`     — 原样复制（7 个文件：assembly/constants/derived_metrics/financials/infrastructure/other_data/yfinance_integration + __init__）
- `valuation_engine.py`  — 原样复制（保留原版权/docstring；`from config import ...` 同目录相对导入可用）
- `adapter.py`           — 新增入口 `run_turtle_valuation(ts_code) -> dict`
- `__init__.py`          — 包标识

## 二、改了什么（仅 tushare_collector.py，4 处）

1. `import tushare as ts` → `from tradingagents.strategies.akshare_tushare_bridge import get_pro_api`；
   `__init__` 中 `ts.set_token(token)` + `self.pro = ts.pro_api(timeout=30)` → `self.pro = get_pro_api()`；
   `__init__` 签名 `token: str = ""`（桥接层不需要 token）。
2. vip 分支（`self.pro._DataApi__token` 等）：桥接层对象无 `_DataApi` 私有属性，包 try/except AttributeError，失败时 `_vip_mode=False`（默认 .env 无 API_URL 不触发，纯防御）。
3. retry 重建分支同样替换为 `get_pro_api()` + try/except 防御。
4. `_safe_call` 核心三处适配：
   - `getattr(self.pro, effective_name, None)`：桥接层无 top10_holders/fina_mainbz/repurchase/hk_*/us_* 方法时返回带通用列空表（不重试 5 次）。
   - **ts_code 通用过滤**：桥接层部分全市场接口（如 stock_basic）忽略 ts_code 参数，返回后按 `kwargs["ts_code"]` 精确过滤（匹配不到则原样返回，兼容单只接口）。
   - **dividend 补列**：桥接层 dividend 无 div_proc 列，而龟龟 `get_dividends` 依赖 `df["div_proc"]=="实施"` 过滤（巨潮已实施分红，补 `div_proc="实施"` 保持语义），保证分红历史 + DDM 正常。

`adapter.py` 结构按任务模板：
- `_ROOT` 插入 sys.path 使 config/tushare_collector/valuation_engine/tushare_modules 可相对导入；
- `client._cache_enabled` 默认 False（避免写盘），新增环境变量 `TURTLE_TTL_CACHE=1` 开启（测试/开发加速，财务 7 天/行情 24h）；
- `run()` 后带出 `classification`（`engine.classify()` 内存计算）与 `wacc`（`engine.compute_wacc()`），失败置 None；整体异常返回 `{"error", "ts_code"}`。

`app/routers/strategy.py` 追加：
```python
@router.get("/turtle-valuation/{ts_code}")
async def turtle_valuation(ts_code: str):
    from tradingagents.strategies.turtle.adapter import run_turtle_valuation
    return {"success": True, "data": run_turtle_valuation(ts_code)}
```

## 三、测试 / 端点验证

**pytest**：`.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_turtle_valuation.py -v`
→ `1 passed, 3 warnings in 18.37s`（全绿；warnings 为无害的 ConfigManager 弃用提示 / akshare DeprecationWarning / PytestUnknownMarkWarning）。

**端点**：重启后端（`serve_prod.py`，`QUOTES_BACKFILL_ON_STARTUP=false` + `TURTLE_TTL_CACHE=1`）
→ `Invoke-WebRequest http://127.0.0.1:8000/api/strategy/turtle-valuation/000001.SZ`
→ **HTTP 200**, success=True, ts_code=000001.SZ, classification=混合型, wacc=3.76, markdown_len=3059, 含"估值"。

## 四、耗时实测（akshare 数据源，000001.SZ）

| 阶段 | 耗时 |
|---|---|
| 单接口（fina_indicator / income / balancesheet / cashflow / dividend / yc_cb / pledge_stat） | 1~5s 不等 |
| 单接口（stock_basic / daily_basic / daily / weekly） | 3~30s 不等（网络波动大） |
| 完整流程（无缓存，首次） | >120s（多次被 subagent bash 2min 限制打断，最终靠 TTL 缓存预热跑通） |
| 完整流程（TTL 缓存命中，smoke） | **20.2s** |
| pytest（缓存命中） | **18.37s** |
| 端点请求（服务进程，daily_basic/daily 每次拉） | **65.8s** |

## 五、Concerns

1. **网络强依赖/慢**：akshare 各接口 3~30s 不定（东财域名被代理拦截时自动回退），无缓存完整流程可能 >2min。生产建议设 `TURTLE_TTL_CACHE=1` 并接受单次 1~2 分钟延迟；或后续给 daily_basic/daily 加磁盘缓存。
2. **缺失接口降级**：top10_holders/fina_mainbz/repurchase 在桥接层无对应方法，`_safe_call` 返回空表 → 对应板块显示"数据缺失/暂无回购"，不影响估值核心；hk_*/us_* 分支同理（A 股路径不触发）。
3. **测试 flaky**：`@pytest.mark.slow` 未在项目注册（仅 warning 无害）；测试依赖真实网络，首次无缓存可能超时，缓存命中后稳定 ~18-40s。
4. **后端启动阻塞**：`serve_prod.py` 启动时 quotes backfill / 全市场股票列表拉取在受限网络下可能长时间阻塞（本环境用 `QUOTES_BACKFILL_ON_STARTUP=false` 绕过，不影响 API）；subagent 会话结束后后台进程被环境清理，需要时需手动 `.\env\Scripts\python.exe serve_prod.py` 重启。
5. **估值质量**：000001.SZ 分类为"混合型"，markdown 3KB——部分方法（如 PE Band 需 3 年 PE、DDM 需 3 年 DPS）因数据/周期数不足返回"跳过"，属龟龟原逻辑的正常容错。
6. **额外复制文件**：format_utils.py / cache_utils.py 未在任务清单列出，但被 tushare_collector/valuation_engine 顶层 import 强依赖，一并复制（原样、未改）。

## 六、遗留

- `output/.collector_cache/`（stock_basic json 缓存 + ttl parquet 缓存）为运行时产物，未提交（未在 git add 范围）。
- 未改动 `C:\Users\cccbqn\strategies\` 原仓库（只读参考）。
