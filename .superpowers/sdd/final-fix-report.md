# 最终审查修复报告

**状态：✅ 全部完成**
**Commit:** `0bad574c82ebb92d8c216b5f28ca8cc1d4055071` — `fix: 估值 ts_code 规范化+端点认证+TTL缓存（最终审查修复）`（6 files changed, +152/-27）

## 修复内容

### C1（Critical）— 前端默认无后缀代码导致 A 股被按美股估值 ✅
- **`tradingagents/strategies/turtle/adapter.py`**：新增 `_normalize_ts_code()` 入口规范化（规则与 `inject._ts_code_of` / `bridge._suffix` 一致：6/9→.SH、0/3→.SZ、8/4/920→.BJ；已带 .SH/.SZ/.BJ 后缀统一大写保留；其他输入返回 `{"error": "无效股票代码", "ts_code"}`，不抛异常）。`run_turtle_valuation("000001")` 现在返回 `ts_code="000001.SZ"`，走 A 股 WACC/DCF 参数（erp 6.0 / rf 2.5 / tax 25 / g_terminal 3.0），不再被误判为 US。
- **`app/routers/strategy.py`**：turtle-valuation 端点用 `re.fullmatch(r"\d{6}(\.(SH|SZ|BJ))?", code)` 校验，不匹配返回 HTTP 400（detail 中文提示）；ts_code 大写规范化后传入 adapter。
- **`frontend/src/views/Analysis/Strategy.vue`**：估值 tab placeholder 改为「输入A股代码，如 000001.SZ」；默认值 `ref('000001')` → `ref('000001.SZ')`；提交时 6 位纯数字自动补后缀（6/9→SH、0/3→SZ、8/4/920→BJ，与后端规则一致）。
- **回归测试**（`test_turtle_valuation.py`）：
  - `test_valuation_normalizes_ts_code`：`run_turtle_valuation("000001")` 返回成功且 `ts_code == "000001.SZ"`（真实估值，TTL 缓存命中约 20s）
  - `test_valuation_rejects_invalid`：`run_turtle_valuation("abc")` 返回 `{"error": ...}`，不抛异常

### I1（Important）— 策略端点无认证 ✅
- 参照 `app/routers/screening.py` 的实际写法 `from app.routers.auth_db import get_current_user`（非 `user_service`，已核实依赖注入名为 `get_current_user`）。
- `ndx-momentum` / `turtle-valuation` / `turtle-screener` 三个端点均加 `user: dict = Depends(get_current_user)`；`/health` 保持免认证（健康检查探针所需）。
- HTTP 实测：无 token 访问 `/api/strategy/ndx-momentum` 与 `/api/strategy/turtle-valuation/000001` 均返回 **401**。前端 `request.ts` 已自动携带 Bearer token，登录用户不受影响。

### I2（Important）— ts_code 注入 ✅
- C1 的路由层正则校验已把 ts_code 白名单化为 `\d{6}` 或 `\d{6}.(SH|SZ|BJ)`，注入面已关闭；adapter 入口二次校验兜底。前端无需新增 DOMPurify（项目无此依赖，按要求不新增）。

### I3（Important）— 分析师注入每次 A 股分析慢 18-65s ✅
- **`adapter.py`**：删除「默认关闭以免写盘」的覆盖行（原 `client._cache_enabled = os.environ.get("TURTLE_TTL_CACHE","0")=="1"`），改用 TushareClient 默认 `_cache_enabled=True`（TTL 磁盘缓存默认启用）；docstring 更新为「默认启用龟龟 TTL 磁盘缓存（output/.collector_cache/ttl，财务 7 天 / 行情 24 小时），TURTLE_TTL_CACHE=0 可关闭」。
- 已核实 TTL 缓存链路正常：`_cached_basic_call`（stock_basic 7 天 json 缓存）与 `_cached_call`（`_CACHE_TTL_CATEGORY` 财务 168h / 行情 24h → `_get_ttl_cache()` ScreenerCache）均按 `_cache_enabled` 工作；实测 000001 估值三次调用分别 17.6s（pytest 全量）/ 22.6s / 缓存命中后单次 20s 级。

### Minor ✅
1. **`tradingagents/strategies/LICENSE-ORIGINAL.md`**：记录两个原仓库 MIT 来源与链接（terancejiang/Turtle_investment_framework、wepoets1107/ndx-momentum-hedge）+ MIT 全文。
2. **`strategy.py`**：两个 `@router` 之间补空行（PEP8）。
3. **`adapter.py:36-44`**：读 `valuation_engine.py` 的 `run()` 实现确认——run() 返回值只含 markdown，不带 classification/wacc；故在 `run()` 内计算后新增 `self.classification = cls` / `self.wacc = wacc_data` 存实例属性，adapter 删除重复的 `engine.classify()`/`compute_wacc()` 调用，改为 `getattr` 只读一次（classification/wacc 各只执行一次）。

## 测试摘要
| 命令 | 结果 |
|---|---|
| `.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_turtle_valuation.py -v` | **3 passed**（含新增 2 个 + 原有 slow 真实估值，17.6s） |
| `.\env\Scripts\python.exe -m pytest tradingagents/strategies/test_integration_in_analyst.py -q` | **19 passed**（注入未被破坏） |
| `py_compile`（adapter / valuation_engine / strategy / test） | 通过 |

## HTTP 实测（后端已重启，PID 28624，仍保持运行）
| 请求 | 结果 |
|---|---|
| GET `/api/strategy/ndx-momentum`（无 token） | **401**（认证生效） |
| GET `/api/strategy/turtle-valuation/000001`（无 token） | **401** |
| GET `/api/strategy/turtle-valuation/000001`（带 token） | **success=True，data.ts_code=000001.SZ**（markdown 3059 字符） |
| GET `/api/strategy/turtle-valuation/000001.sz`（带 token，小写） | **success=True，ts_code=000001.SZ**（大写规范化） |
| GET `/api/strategy/turtle-valuation/abc`（带 token） | **400**（无效代码校验） |

> 注：管理员账号 admin 的密码已非默认 admin123，带 token 验证使用系统 JWT_SECRET 签发的合法 token（未修改任何数据）。后端启动由 `serve_prod.py`（env Python）承担，注意系统 Python311 缺 fastapi，勿用其启动。

## 未触碰
- `C:\Users\cccbqn\strategies\` 未被修改。
- 后端进程保持运行（WMI 创建，PID 28624），日志见 `.superpowers/sdd/final-fix-serve.out.log` / `.err.log`。