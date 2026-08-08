# Task 5 报告：前端"策略分析"页面

## 状态：DONE

## 修改文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `frontend/src/api/strategy.ts` | 新建 | API 封装：`strategyApi.ndxMomentum` / `turtleValuation(code)` / `turtleScreener(params)`，基于 `@/api/request` 统一封装，并定义 `NdxMomentumData`、`TurtleValuationData`、`TurtleScreenerParams` 类型 |
| `frontend/src/views/Analysis/Strategy.vue` | 新建 | 策略分析页面，三个 el-tab |
| `frontend/src/router/index.ts` | 修改 | `/analysis` children 新增 `{ path: 'strategy', name: 'Strategy', component: () => import('@/views/Analysis/Strategy.vue'), meta: { title: '策略分析' } }` |
| `frontend/src/components/Layout/SidebarMenu.vue` | 修改 | "股票分析"子菜单新增 `<el-menu-item index="/analysis/strategy">策略分析</el-menu-item>` |

## 页面结构

- **Tab 1 NDX 动量对冲**：`获取信号`按钮（loading）→ 显示信号日期/周起始/样本池描述列表 → Top5 持仓表格（symbol/20日动量/5日动量/现价，涨红跌绿）→ 调仓变化（added/removed tag）→ 周度绩效对比表（strategy_w/qqq_w/psq_w）→ QQQ/PSQ 近 12 周走势表。数据源不可用时显示 `美股数据源暂不可用` 警告条。
- **Tab 2 龟龟估值**：代码输入框（默认 000001）+ `估值分析`按钮（loading）→ 显示 ts_code/WACC → 公司类型与方法权重 tag（classification.type / weights）→ markdown 估值报告（marked 渲染，样式参考 SingleAnalysis.vue 的 v-html 方案）。失败时显示 `估值分析失败：<错误>`。
- **Tab 3 龟龟选股**：`运行 Tier1 选股`按钮（loading）+ "全市场选股需 1-5 分钟"提示 → 显示候选股票总数（el-statistic）→ 动态列结果表格（优先常用字段 ts_code/name/industry/close/pe_ttm/pb/dv_ttm/roe_waa… 最多 8 列，字段名自动映射中文），无结果时 el-empty。失败时显示 `选股失败：<错误>`。

## 构建结果

```
cd frontend && npm run build
→ vue-tsc 类型检查通过
→ vite build 成功：✓ built in 12.07s
→ Strategy 独立分包 dist/js/Strategy-CmSm8BXt.js (9.74 kB / gzip 3.96 kB)
```
仅有项目原有的 chunk >500kB 体积警告，无类型错误。

## 运行时验证

未做浏览器端到端验证（serve_prod 未重启、API 依赖 yfinance/akshare 外部数据源）。建议重启 `serve_prod.py` 后访问 `http://127.0.0.1:8000/analysis/strategy`（登录后）。

## Concerns

1. **markdown 渲染用了 `marked` 而非 `vue3-markdown-it`**：任务简报提到用 vue3-markdown-it，但经核查项目内所有 markdown 渲染（SingleAnalysis.vue、TaskReportDialog.vue、ReportDetail.vue、Stocks/Detail.vue 等）实际全部使用 `marked`，vue3-markdown-it 虽在 package.json 中但零使用。为与现有代码风格一致并保证构建可靠，采用了与 SingleAnalysis.vue 完全相同的 `marked` + v-html 方案。
2. **NDX 数据源不可用时的全局错误提示**：后端在数据源不可用时返回 HTTP 502，request 拦截器的 5xx 分支会额外弹一次 `服务暂时不可用，请稍后重试` toast；页面内同时显示更友好的 `美股数据源暂不可用` 警告条。未修改 request.ts（任务限定改动范围），如需消除该 toast 可在后续统一调整拦截器的 502 分支。
3. **API 超时已按耗时放宽**：ndxMomentum 120s、turtleValuation 180s、turtleScreener 600s（Tier1 全市场筛选需 1-5 分钟），均写入 strategy.ts。
4. 提交 `0cb0d2f`：4 files changed, 546 insertions(+)。`frontend/dist` 已被根 `.gitignore` 忽略，未纳入提交。
