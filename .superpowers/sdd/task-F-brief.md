### Task F: 前端整合

**Files:**
- Modify: `frontend/package.json`（加 `stock-sdk` npm 依赖）
- Modify: `frontend/src/views/Analysis/Strategy.vue`（加 tab：技术指标/筹码分布/因子选股/回测）或新建 `frontend/src/views/Analysis/Quant.vue`
- Modify: `frontend/src/router/index.ts`、`SidebarMenu.vue`
- Create: `frontend/src/api/quant.ts`

**范围：**
1. **行情看板/技术图**：用 stock-sdk（npm）在前端画 K 线 + 技术指标叠加（ECharts 已有）
2. **筹码分布图**：调 `/api/strategy/chips/{symbol}` → 前端筹码峰图
3. **因子选股**：因子列表 + 条件输入 → `/api/strategy/factor-screen`
4. **回测页**：股票/策略/区间 → `/api/strategy/backtest` → 权益曲线（ECharts）+ 指标卡片
5. **quantlib 调用**：简易计算器（BS 定价输入框）

- [ ] 装 stock-sdk：`cd frontend && npm install stock-sdk`
- [ ] 新页面/新 tab 组件（参考 Strategy.vue 现有风格）→ `npm run build` 成功
- [ ] 提交 `feat: 前端量化页（技术图/筹码/因子/回测）`

---


