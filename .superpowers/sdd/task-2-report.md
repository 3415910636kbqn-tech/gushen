# Task 2 报告：NDX 动量对冲策略模块 + REST API

**状态：DONE_WITH_CONCERNS**
**Commit：`8d6668f9f29ea9c3101bd638f3809a2bfb16043a`**（"feat: 整合 NDX 动量对冲策略（yfinance 数据 + REST API）"，4 files changed, 373 insertions）

## 1. 实现说明

### 新建/修改文件
| 文件 | 类型 | 说明 |
|---|---|---|
| `tradingagents/strategies/ndx_momentum_hedge.py` | 新建 | 策略核心：`run_ndx_momentum_hedge(prices=None)`，输出 `date/week_start/pool_size/momentum_top5/top_symbols/changes/performance/qqq_12w/full_momentum` |
| `tradingagents/strategies/test_ndx_momentum_hedge.py` | 新建 | 4 个测试（见 §3） |
| `app/routers/strategy.py` | 新建 | `GET /api/strategy/ndx-momentum`（数据失败返回 502 + detail）、`GET /api/strategy/health` |
| `app/main.py` | 修改 | import 区（L72）注册 `strategy_router`；include_router 区（L723）`prefix="/api/strategy", tags=["strategy"]` |

### 策略逻辑（移植自原仓库 server.py 的 build_report + NDX_100）
- 数据源：yfinance 批量下载 60 天日线（adj close，含 QQQ/PSQ）；失败回退 Yahoo query2 直连（requests+crumb）；再兜底读本地 `data/cache/ndx_prices.pkl` 缓存（2 小时正常缓存 / 7 天过期兜底）。
- 20 日动量过滤（>0）+ 按 5 日动量降序取前 5（方案 B）。
- 对冲收益：`strategy_w = 持仓股平均 5 日动量 × 0.5 + PSQ 周涨跌 × 0.5`；同时输出 QQQ 周涨跌、近 12 周走势、与上次持仓的 changes。
- **降级**：所有数据源不可用时返回 `{"error": "数据获取失败"}`（REST 转 502），带 Yahoo 连通性快速探测（~5s），避免长时间挂起。

## 2. 测试结果（Step 2 / Step 4）

```
pytest tradingagents/strategies/test_ndx_momentum_hedge.py -v
4 passed, 1 warning in ~1s
  ✓ test_report_shape          —— 报告结构（top_symbols/performance/momentum_top5/changes/qqq_12w 等）
  ✓ test_selection_rules       —— 20日动量>0 过滤 + 5日动量降序 top5 == [NVDA,MSFT,GOOGL,AMZN,TSLA]
  ✓ test_performance_shape     —— strategy_w = 平均5日动量×0.5 + psq_w×0.5
  ✓ test_data_failure_returns_error —— 数据源失败返回 {"error":...} 不抛异常
```

无参调用（真实网络）在 7s 内快速返回 `{"error":"数据获取失败"}`。

## 3. 端点验证结果（Step 6）

后端已重启（`serve_prod.py`，端口 8000，PID 见下）并验证：

- `GET http://127.0.0.1:8000/api/strategy/health` → **200** `{"success":true,"data":{"strategies":["ndx-momentum"]}}`
- `GET http://127.0.0.1:8000/api/strategy/ndx-momentum`（真实网络，Yahoo 不可用）→ **502** `{"detail":"数据获取失败"}` —— 路由存在且错误处理正确
- `GET http://127.0.0.1:8000/openapi.json` → 已注册 `/api/strategy/ndx-momentum`、`/api/strategy/health`
- **成功路径验证**：向 `data/cache/ndx_prices.pkl` 注入测试价格数据后调用 `/api/strategy/ndx-momentum` → **200**，`top_symbols=[NVDA,MSFT,GOOGL,AMZN,TSLA]`、`performance={strategy_w:1.4, qqq_w:2, psq_w:-2.4}`、`momentum_top5` 5 项、`pool_size=7`（验证后已删除该缓存文件）

## 4. 偏差（CONCERNS）

1. **⚠️ 美股历史数据源在当前网络环境完全不可用**（已系统性排查）：
   - Yahoo Finance（yfinance/query1/query2，requests 与 curl_cffi impersonate chrome）→ 全部 403 反爬页（lang=zh）/ 429 限流，持续约 1 小时未恢复；
   - 东方财富 push2his（akshare `stock_us_hist` 底层）→ 连接被断；腾讯 ifzq 美股日K → 仅返回 2 行（A股正常，美股被限制）；新浪美股接口 → "Invalid service name"；网易 → 502；雪球 → 需登录；stooq → JS PoW 验证后仍 "Access denied"；同花顺 → 404。
   - **因此测试改为注入本地构造的价格序列**（`run_ndx_momentum_hedge(prices=...)` 可注入，为 brief 未提的可选参数）验证核心逻辑；数据失败降级行为单独测试。**这是对 brief 测试用法的必要偏离**——brief 假设网络可用。策略模块在数据源恢复后无需改动即可正常工作。
2. **后端启动**：serve_prod 的 lifespan 中有 akshare 实时行情回填/同步任务，在该网络下会长时间阻塞启动，且 Start-Process 子进程随会话被回收；已用 `QUOTES_BACKFILL_ON_STARTUP=false` 环境变量 + WMI 方式启动持久进程（现 PID 11068 监听 8000）。这是部署环境问题，非代码缺陷，`app/main.py` 业务逻辑未改动。
3. 首次调用 `/api/strategy/ndx-momentum` 在数据源不可用时耗时约 7s（探测+回退）；数据源可用时预计 30-60s（101 ticker 批量下载）。
4. 未提交未跟踪部署文件（serve_prod.py、启动脚本等）；`data/cache/` 为空目录未提交。

## 5. 测试摘要（一行）

`pytest tradingagents/strategies/test_ndx_momentum_hedge.py` → **4 passed**；REST `/api/strategy/health` 200、`/api/strategy/ndx-momentum` 502（数据源降级）/ 200（注入数据成功路径）。
---

## 2.1 审查修复：缓存生效 + changes 文件持久化

**Commit：`ab9ec44`**（"fix: NDX 策略缓存生效 + changes 文件持久化"，2 files changed, 115 insertions, 17 deletions）

### 修复 1（Important）— pkl 缓存成功路径生效
- `_fetch_prices` 现在**拉取前先检查** `data/cache/ndx_prices.pkl`：`_load_cache()` 命中（< 2 小时且含 QQQ 键）直接返回，**数据源可用时也走缓存**，不再每次全量拉 103 个 ticker（原 30-60s → 命中时 <1s）。
- 拉取成功路径写缓存保持（yfinance 成功 → `_save_cache(out)`；query2 成功 → 内部 `_save_cache`），`_save_cache` 已含时间戳 `_ts`。
- `_load_cache` 增加 **QQQ 键校验**（无 QQQ 键的残缺缓存视为未命中）。
- `_load_cache` 默认 `cache_minutes=120` 从"误导性死代码"变为实际使用：主检查 `_load_cache()` 用默认 120 分钟；网络全失败时的过期兜底仍显式传 7 天。

### 修复 2（Minor）— changes 持久化到 JSON 文件
- 新增 `LAST_TOP_PATH = data/cache/ndx_last_top.json`（目录不存在自动创建）。
- 新增 `_load_last_top()` / `_save_last_top()`；`run_ndx_momentum_hedge` 改为每次运行后把本次 `top_symbols` 写回文件，changes 基于文件计算（删除模块级内存 `_LAST_TOP`，直接用文件更简单）。
- 文件缺失/损坏视为空列表（首次运行全部新增）；服务重启后 changes 仍基于文件生效。

### 新增测试（3 个，共 7 个）
- `test_fetch_prices_uses_fresh_cache`：预写新鲜缓存 + monkeypatch 网络函数抛错计数，`_fetch_prices` 命中缓存直接返回，网络调用 0 次。
- `test_fetch_prices_writes_cache_and_hits_next_call`：注入 fake_yf（计数），首次拉取写入缓存，二次调用命中缓存返回相同数据，网络只调 1 次。
- `test_changes_persist_to_file`：预置上次持仓文件 → changes 增删正确、本次持仓写回文件、再运行（模拟重启）无增删。
- 另加 autouse fixture 把 `CACHE_PATH`/`LAST_TOP_PATH` 隔离到 pytest tmp 目录，避免污染真实 `data/cache/`。

### 测试结果
```
tradingagents/strategies/test_ndx_momentum_hedge.py: 7 passed in 1.00s（原有 4 + 新增 3 全绿）
tradingagents/strategies/ 全量: 20 passed（含桥接层测试，未受影响）
```
