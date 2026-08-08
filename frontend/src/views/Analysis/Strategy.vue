<template>
  <div class="strategy-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><TrendCharts /></el-icon>
        策略分析
      </h1>
      <p class="page-description">
        NDX 动量对冲 / 龟龟估值 / 龟龟选股 — 量化策略研究与信号展示
      </p>
    </div>

    <el-card shadow="never" class="strategy-card">
      <el-tabs v-model="activeTab" type="border-card">
        <!-- ==================== NDX 动量对冲 ==================== -->
        <el-tab-pane label="NDX 动量对冲" name="ndx">
          <div class="tab-toolbar">
            <el-button type="primary" :loading="ndxLoading" @click="fetchNdxSignal">
              <el-icon style="margin-right: 4px;"><Refresh /></el-icon>
              <span>获取信号</span>
            </el-button>
            <span class="toolbar-tip">纳斯达克 100 动量选股 + PSQ 反向对冲，周频调仓</span>
          </div>

          <el-alert
            v-if="ndxError"
            type="warning"
            :title="ndxError"
            description="可能是美股数据源暂时不可用，请稍后重试。"
            show-icon
            :closable="true"
            style="margin-bottom: 16px;"
          />

          <template v-if="ndxData">
            <!-- 信号日期 -->
            <el-descriptions :column="3" border style="margin-bottom: 20px;">
              <el-descriptions-item label="信号日期">
                <strong>{{ ndxData.date }}</strong>
              </el-descriptions-item>
              <el-descriptions-item label="周起始日">{{ ndxData.week_start }}</el-descriptions-item>
              <el-descriptions-item label="样本池">{{ ndxData.pool_size }} 只</el-descriptions-item>
            </el-descriptions>

            <!-- Top5 持仓 -->
            <h3 class="section-title">Top 5 持仓</h3>
            <el-table :data="ndxData.momentum_top5" border stripe style="margin-bottom: 20px;">
              <el-table-column type="index" label="#" width="55" align="center" />
              <el-table-column prop="symbol" label="代码" min-width="90">
                <template #default="{ row }">
                  <strong>{{ row.symbol }}</strong>
                </template>
              </el-table-column>
              <el-table-column prop="momentum" label="20日动量 (%)" min-width="130" align="right">
                <template #default="{ row }">
                  <span :class="fmtClass(row.momentum)">{{ fmtPct(row.momentum) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="momentum_5d" label="5日动量 (%)" min-width="130" align="right">
                <template #default="{ row }">
                  <span :class="fmtClass(row.momentum_5d)">{{ fmtPct(row.momentum_5d) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="price" label="现价" min-width="100" align="right">
                <template #default="{ row }">{{ fmtNum(row.price) }}</template>
              </el-table-column>
            </el-table>

            <!-- 调仓变化 -->
            <template v-if="ndxData.changes && (ndxData.changes.added?.length || ndxData.changes.removed?.length)">
              <h3 class="section-title">调仓变化</h3>
              <div class="changes-row" style="margin-bottom: 20px;">
                <el-tag
                  v-for="s in ndxData.changes.added"
                  :key="'a' + s"
                  type="success"
                  effect="plain"
                  style="margin-right: 8px;"
                >+ {{ s }} 新增</el-tag>
                <el-tag
                  v-for="s in ndxData.changes.removed"
                  :key="'r' + s"
                  type="danger"
                  effect="plain"
                  style="margin-right: 8px;"
                >- {{ s }} 移除</el-tag>
              </div>
            </template>

            <!-- 绩效对比 -->
            <h3 class="section-title">周度绩效对比 (%)</h3>
            <el-table :data="performanceRows" border stripe style="margin-bottom: 20px;">
              <el-table-column prop="name" label="指标" min-width="200" />
              <el-table-column prop="value" label="周涨跌" min-width="120" align="right">
                <template #default="{ row }">
                  <span :class="fmtClass(row.value)">{{ fmtPct(row.value) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="desc" label="说明" min-width="220" />
            </el-table>

            <!-- QQQ 12 周走势 -->
            <h3 class="section-title">QQQ / PSQ 近 12 周走势</h3>
            <el-table :data="ndxData.qqq_12w" border stripe size="small">
              <el-table-column prop="date" label="日期" min-width="110" />
              <el-table-column prop="qqq" label="QQQ" min-width="110" align="right">
                <template #default="{ row }">{{ fmtNum(row.qqq) }}</template>
              </el-table-column>
              <el-table-column prop="psq" label="PSQ" min-width="110" align="right">
                <template #default="{ row }">{{ fmtNum(row.psq) }}</template>
              </el-table-column>
            </el-table>
          </template>
        </el-tab-pane>

        <!-- ==================== 龟龟估值 ==================== -->
        <el-tab-pane label="龟龟估值" name="valuation">
          <div class="tab-toolbar">
            <el-input
              v-model="valuationCode"
              placeholder="输入A股代码，如 000001.SZ"
              style="width: 240px; margin-right: 12px;"
              @keyup.enter="runValuation"
            />
            <el-button type="primary" :loading="valuationLoading" @click="runValuation">
              <el-icon style="margin-right: 4px;"><DataAnalysis /></el-icon>
              <span>估值分析</span>
            </el-button>
            <span class="toolbar-tip">基于 akshare 数据的 DCF / DDM / PE Band / PEG / PS 多方法估值</span>
          </div>

          <el-alert
            v-if="valuationError"
            type="error"
            :title="valuationError"
            show-icon
            :closable="true"
            style="margin-bottom: 16px;"
          />

          <template v-if="valuationData">
            <el-descriptions :column="2" border style="margin-bottom: 20px;">
              <el-descriptions-item label="股票代码">
                <strong>{{ valuationData.ts_code }}</strong>
              </el-descriptions-item>
              <el-descriptions-item label="WACC">
                <strong v-if="valuationData.wacc && valuationData.wacc.wacc != null">
                  {{ fmtNum(valuationData.wacc.wacc) }}%
                </strong>
                <span v-else>—</span>
              </el-descriptions-item>
            </el-descriptions>

            <!-- 公司类型与估值方法权重 -->
            <template v-if="valuationData.classification">
              <h3 class="section-title">公司类型与估值方法</h3>
              <div class="classify-box" style="margin-bottom: 20px;">
                <el-tag type="primary" effect="dark" style="margin-right: 8px;">
                  类型：{{ valuationData.classification.type || '未知' }}
                </el-tag>
                <el-tag
                  v-for="(w, m) in valuationData.classification.weights"
                  :key="m"
                  type="info"
                  effect="plain"
                  style="margin-right: 8px;"
                >{{ m }}: {{ fmtNum(w) }}%</el-tag>
              </div>
            </template>

            <!-- 估值报告 -->
            <h3 class="section-title">估值报告</h3>
            <div class="markdown-body" v-html="renderMarkdown(valuationData.markdown)" />
          </template>
        </el-tab-pane>

        <!-- ==================== 龟龟选股 ==================== -->
        <el-tab-pane label="龟龟选股" name="screener">
          <div class="tab-toolbar">
            <el-button type="primary" :loading="screenerLoading" @click="runScreener">
              <el-icon style="margin-right: 4px;"><Search /></el-icon>
              <span>运行 Tier1 选股</span>
            </el-button>
            <span class="toolbar-tip">全市场选股需 1-5 分钟，请耐心等待</span>
          </div>

          <el-alert
            v-if="screenerError"
            type="error"
            :title="screenerError"
            show-icon
            :closable="true"
            style="margin-bottom: 16px;"
          />

          <template v-if="screenerData">
            <div class="result-summary" style="margin-bottom: 16px;">
              <el-statistic title="候选股票数" :value="screenerData.count || (screenerData.candidates || []).length" />
            </div>

            <el-table v-if="(screenerData.candidates || []).length" :data="screenerData.candidates" border stripe size="small" style="width: 100%;">
              <el-table-column type="index" label="#" width="55" align="center" />
              <el-table-column
                v-for="col in screenerColumns"
                :key="col"
                :prop="col"
                :label="columnLabel(col)"
                min-width="110"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  {{ formatCell(row[col]) }}
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无候选股票" />
          </template>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { TrendCharts, Refresh, DataAnalysis, Search } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { strategyApi } from '@/api/strategy'

// 配置marked选项
marked.setOptions({ breaks: true, gfm: true })

const activeTab = ref('ndx')

// ---------- NDX 动量对冲 ----------
const ndxLoading = ref(false)
const ndxData = ref<any>(null)
const ndxError = ref('')

const fetchNdxSignal = async () => {
  ndxLoading.value = true
  ndxError.value = ''
  try {
    const res: any = await strategyApi.ndxMomentum()
    if (res?.success && res.data && !res.data.error) {
      ndxData.value = res.data
    } else {
      ndxData.value = null
      ndxError.value = '美股数据源暂不可用'
    }
  } catch (err: any) {
    ndxData.value = null
    ndxError.value = '美股数据源暂不可用'
  } finally {
    ndxLoading.value = false
  }
}

const performanceRows = computed(() => {
  const p = ndxData.value?.performance
  if (!p) return []
  return [
    { name: '策略（50% Top5 动量 + 50% PSQ）', value: p.strategy_w, desc: '对冲组合周收益' },
    { name: 'QQQ 基准', value: p.qqq_w, desc: '纳斯达克 100 ETF 周收益' },
    { name: 'PSQ 反向对冲', value: p.psq_w, desc: '反向 QQQ ETF 周收益' }
  ]
})

// ---------- 龟龟估值 ----------
const valuationCode = ref('000001.SZ')
const valuationLoading = ref(false)
const valuationData = ref<any>(null)
const valuationError = ref('')

const runValuation = async () => {
  let code = valuationCode.value.trim().toUpperCase()
  if (!code) {
    ElMessage.warning('请输入股票代码')
    return
  }
  // 6 位纯数字自动补 A 股后缀（与后端规则一致：6/9->SH、0/3->SZ、8/4/920->BJ）
  if (/^\d{6}$/.test(code)) {
    if (/^[69]/.test(code)) code += '.SH'
    else if (/^(8|4|920)/.test(code)) code += '.BJ'
    else code += '.SZ'
  }
  if (!code) {
    ElMessage.warning('请输入股票代码')
    return
  }
  valuationLoading.value = true
  valuationError.value = ''
  valuationData.value = null
  try {
    const res: any = await strategyApi.turtleValuation(code)
    if (res?.success && res.data) {
      if (res.data.error) {
        valuationError.value = `估值分析失败：${res.data.error}`
      } else {
        valuationData.value = res.data
      }
    } else {
      valuationError.value = '估值分析失败，请稍后重试'
    }
  } catch (err: any) {
    valuationError.value = `估值分析失败：${err?.message || '未知错误'}`
  } finally {
    valuationLoading.value = false
  }
}

// ---------- 龟龟选股 ----------
const screenerLoading = ref(false)
const screenerData = ref<any>(null)
const screenerError = ref('')

const runScreener = async () => {
  screenerLoading.value = true
  screenerError.value = ''
  screenerData.value = null
  try {
    const res: any = await strategyApi.turtleScreener({ tier1_only: true, tier2_limit: 10 })
    if (res?.success && res.data) {
      if (res.data.error) {
        screenerError.value = `选股失败：${res.data.error}`
      } else {
        screenerData.value = res.data
      }
    } else {
      screenerError.value = '选股失败，请稍后重试'
    }
  } catch (err: any) {
    screenerError.value = `选股失败：${err?.message || '未知错误'}`
  } finally {
    screenerLoading.value = false
  }
}

// 选股结果动态列（优先展示常用字段，最多 8 列）
const PREFERRED_COLUMNS = [
  'ts_code', 'name', 'industry', 'close', 'pe_ttm', 'pb', 'dv_ttm',
  'roe_waa', 'gross_margin', 'fcf_yield', 'fcf_margin', 'R',
  'ev_ebitda', 'floor_premium', 'composite_score'
]

const COLUMN_LABELS: Record<string, string> = {
  ts_code: '代码', name: '名称', industry: '行业', close: '现价',
  pe_ttm: '市盈率', pb: '市净率', dv_ttm: '股息率', roe_waa: 'ROE',
  gross_margin: '毛利率', fcf_yield: 'FCF收益率', fcf_margin: 'FCF利润率',
  R: 'R', ev_ebitda: 'EV/EBITDA', floor_premium: '安全边际', composite_score: '综合评分'
}

const screenerColumns = computed(() => {
  const rows = screenerData.value?.candidates
  if (!Array.isArray(rows) || rows.length === 0) return []
  const first = rows[0]
  const keys: string[] = []
  for (const k of PREFERRED_COLUMNS) {
    if (k in first && !keys.includes(k)) keys.push(k)
  }
  for (const k of Object.keys(first)) {
    if (!keys.includes(k)) keys.push(k)
    if (keys.length >= 8) break
  }
  return keys.slice(0, 8)
})

const columnLabel = (col: string) => COLUMN_LABELS[col] || col

// ---------- 格式化工具 ----------
const fmtNum = (v: any) => (v === null || v === undefined || v === '') ? '—' : Number(v).toFixed(2)
const fmtPct = (v: any) => (v === null || v === undefined || v === '') ? '—' : `${Number(v).toFixed(2)}%`
const fmtClass = (v: any) => (Number(v) >= 0 ? 'up' : 'down')
const formatCell = (v: any) => {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'number') return Number(v).toFixed(2)
  return String(v)
}

// markdown 渲染（与 SingleAnalysis.vue 一致的 marked 方案）
const renderMarkdown = (content: string): string => {
  try {
    return marked.parse(content || '') as string
  } catch (e) {
    return `<pre style="white-space: pre-wrap;">${content || ''}</pre>`
  }
}
</script>

<style lang="scss" scoped>
.strategy-page {
  .page-header {
    margin-bottom: 20px;

    .page-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 22px;
      margin: 0 0 6px;
      color: var(--el-text-color-primary);
    }

    .page-description {
      margin: 0;
      color: var(--el-text-color-secondary);
      font-size: 14px;
    }
  }

  .strategy-card {
    border-radius: 8px;

    :deep(.el-tabs__content) {
      padding: 16px;
    }
  }

  .tab-toolbar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 16px;

    .toolbar-tip {
      margin-left: 12px;
      color: var(--el-text-color-secondary);
      font-size: 13px;
    }
  }

  .section-title {
    font-size: 15px;
    margin: 0 0 10px;
    color: var(--el-text-color-primary);
  }

  .up {
    color: #e53935;
  }

  .down {
    color: #16a34a;
  }

  .markdown-body {
    background: var(--el-fill-color-light);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 6px;
    padding: 16px;
    line-height: 1.7;
    font-size: 14px;
    overflow-x: auto;

    :deep(table) {
      border-collapse: collapse;
      width: 100%;
      margin-bottom: 12px;

      th, td {
        border: 1px solid var(--el-border-color-lighter);
        padding: 6px 10px;
      }
    }

    :deep(pre) {
      background: var(--el-bg-color);
      padding: 10px;
      border-radius: 4px;
      overflow-x: auto;
    }

    :deep(img) {
      max-width: 100%;
    }
  }
}
</style>
