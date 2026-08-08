### Task 5: 前端"策略分析"页面

**Files:**
- Create: `frontend/src/views/Analysis/Strategy.vue`
- Modify: `frontend/src/router/index.ts`（`/analysis` children 加 strategy 路由）
- Modify: `frontend/src/components/Layout/SidebarMenu.vue`（加"策略分析"菜单项）
- Modify: `frontend/src/api/strategy.ts`（新建 API 封装）

**Interfaces:**
- Consumes: `GET /api/strategy/ndx-momentum`、`/turtle-valuation/{code}`、`/turtle-screener?tier1_only=..&tier2_limit=..`
- Produces: Strategy.vue（三个 tab：NDX 动量对冲 / 龟龟估值 / 龟龟选股）

- [ ] **Step 1: 写 API 封装 `frontend/src/api/strategy.ts`**

```typescript
import request from '@/utils/request'

export const strategyApi = {
  ndxMomentum: () => request.get('/api/strategy/ndx-momentum'),
  turtleValuation: (code: string) => request.get(`/api/strategy/turtle-valuation/${code}`),
  turtleScreener: (params: { tier1_only?: boolean; tier2_limit?: number }) =>
    request.get('/api/strategy/turtle-screener', { params }),
}
```

- [ ] **Step 2: 新建 Strategy.vue**（Element Plus，三个 el-tab：NDX 信号卡片表格 / 估值表单+结果 Markdown / 选股结果表格），参考 `frontend/src/views/Screening/index.vue` 的表格写法与 `SingleAnalysis.vue` 的 markdown 渲染（`vue3-markdown-it` 已装）

- [ ] **Step 3: 注册路由**（`frontend/src/router/index.ts` 的 `/analysis` children，约 L58-70）：
```typescript
{ path: 'strategy', name: 'Strategy', component: () => import('@/views/Analysis/Strategy.vue'), meta: { title: '策略分析' } }
```

- [ ] **Step 4: 菜单**（`frontend/src/components/Layout/SidebarMenu.vue` L19-28 股票分析子菜单）加：
```vue
<el-menu-item index="/analysis/strategy">策略分析</el-menu-item>
```

- [ ] **Step 5: 重新构建前端 + 验证**

Run: `cd frontend && npm run build`
Expected: 构建成功
验证：重启 serve_prod 后访问 `http://127.0.0.1:8000/analysis/strategy`（登录后）

- [ ] **Step 6: 提交**

```bash
git add frontend/
git commit -m "feat: 前端新增策略分析页面（NDX 动量/龟龟估值/龟龟选股）"
```

---


