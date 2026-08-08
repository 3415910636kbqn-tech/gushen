<template>
  <div class="quant-page">
    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <!-- ① 行情技术图 -->
        <el-tab-pane label="行情技术图" name="kline">
          <el-form inline>
            <el-form-item label="股票代码">
              <el-input v-model="klineSymbol" placeholder="如 600519" style="width: 160px" clearable />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="klineLoading" @click="loadKline">获取行情</el-button>
            </el-form-item>
          </el-form>
          <el-alert v-if="klineError" type="warning" :title="klineError" show-icon style="margin-bottom: 12px" :closable="false" />
          <div class="chart-box">
            <v-chart v-if="klineOption" class="k-chart" :option="klineOption" autoresize />
          </div>
        </el-tab-pane>

        <!-- ② 筹码分布 -->
        <el-tab-pane label="筹码分布" name="chips">
          <el-form inline>
            <el-form-item label="股票代码">
              <el-input v-model="chipsSymbol" placeholder="如 600519.SH" style="width: 160px" clearable />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="chipsLoading" @click="loadChips">分析筹码</el-button>
            </el-form-item>
          </el-form>
          <el-alert v-if="chipsError" type="warning" :title="chipsError" show-icon style="margin-bottom: 12px" :closable="false" />
          <template v-if="chipsData">
            <el-row :gutter="12" style="margin-bottom: 12px">
              <el-col :span="6"><el-statistic title="获利比例" :value="chipsData.profit_ratio" :precision="2" /></el-col>
              <el-col :span="6"><el-statistic title="平均成本" :value="chipsData.avg_cost" :precision="2" /></el-col>
              <el-col :span="6"><div class="stat-label">90%成本区间</div><div class="stat-value">{{ chipsData.cost_90?.[0] }} - {{ chipsData.cost_90?.[1] }}</div></el-col>
              <el-col :span="6"><el-statistic title="筹码峰价格" :value="chipsData.peak_price" :precision="2" /></el-col>
            </el-row>
            <div class="chart-box">
              <v-chart class="k-chart" :option="chipsOption" autoresize />
            </div>
          </template>
        </el-tab-pane>

        <!-- ③ 因子选股 -->
        <el-tab-pane label="因子选股" name="factor">
          <el-form inline>
            <el-form-item label="因子">
              <el-select v-model="factorName" placeholder="选择因子" style="width: 220px" filterable>
                <el-option v-for="f in factorList" :key="f.name" :label="`${f.display_name}（${f.category}）`" :value="f.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="方向">
              <el-select v-model="factorCond" style="width: 110px">
                <el-option label="Top（最高）" value="top" />
                <el-option label="Bottom（最低）" value="bottom" />
              </el-select>
            </el-form-item>
            <el-form-item label="取前 N 只">
              <el-input-number v-model="factorTopN" :min="1" :max="30" />
            </el-form-item>
            <el-form-item label="股票代码（逗号分隔，≤30 只）">
              <el-input v-model="factorSymbols" placeholder="600519,000001,300750" style="width: 280px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="factorLoading" @click="runFactorScreen">筛选</el-button>
            </el-form-item>
          </el-form>
          <el-alert v-if="factorError" type="warning" :title="factorError" show-icon style="margin-bottom: 12px" :closable="false" />
          <el-table v-if="factorResult?.candidates?.length" :data="factorResult.candidates" border stripe max-height="420">
            <el-table-column prop="symbol" label="代码" width="110" />
            <el-table-column prop="factor_value" label="因子值" />
            <el-table-column label="状态">
              <template #default="{ row }">{{ row.error ? row.error : '✓' }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- ④ 策略回测 -->
        <el-tab-pane label="策略回测" name="backtest">
          <el-form inline>
            <el-form-item label="股票代码">
              <el-input v-model="btSymbol" placeholder="如 000001" style="width: 140px" />
            </el-form-item>
            <el-form-item label="策略">
              <el-select v-model="btStrategy" style="width: 150px">
                <el-option label="买入持有" value="buy_hold" />
                <el-option label="MA 金叉" value="ma_cross" />
                <el-option label="RSI 反转" value="rsi_reverse" />
                <el-option label="动量" value="momentum" />
              </el-select>
            </el-form-item>
            <el-form-item label="开始">
              <el-input v-model="btStart" placeholder="20240101" style="width: 130px" />
            </el-form-item>
            <el-form-item label="结束">
              <el-input v-model="btEnd" placeholder="20241231" style="width: 130px" />
            </el-form-item>
            <el-form-item label="本金">
              <el-input-number v-model="btCapital" :min="10000" :step="10000" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="btLoading" @click="runBacktest">回测</el-button>
            </el-form-item>
          </el-form>
          <el-alert v-if="btError" type="warning" :title="btError" show-icon style="margin-bottom: 12px" :closable="false" />
          <template v-if="btResult && btResult.total_return !== undefined">
            <el-row :gutter="12" style="margin-bottom: 12px">
              <el-col :span="4"><el-statistic title="总收益" :value="btResult.total_return * 100" :precision="2" suffix="%" /></el-col>
              <el-col :span="4"><el-statistic title="年化收益" :value="btResult.annual_return ? btResult.annual_return * 100 : 0" :precision="2" suffix="%" /></el-col>
              <el-col :span="4"><el-statistic title="最大回撤" :value="btResult.max_drawdown ? btResult.max_drawdown * 100 : 0" :precision="2" suffix="%" /></el-col>
              <el-col :span="4"><el-statistic title="Sharpe" :value="btResult.sharpe || 0" :precision="2" /></el-col>
              <el-col :span="4"><el-statistic title="胜率" :value="(btResult.win_rate || 0) * 100" :precision="1" suffix="%" /></el-col>
              <el-col :span="4"><el-statistic title="交易次数" :value="btResult.num_trades || 0" /></el-col>
            </el-row>
            <div class="chart-box">
              <v-chart class="k-chart" :option="btOption" autoresize />
            </div>
          </template>
        </el-tab-pane>

        <!-- ⑤ 金融计算器 -->
        <el-tab-pane label="金融计算器" name="quant">
          <el-form inline>
            <el-form-item label="函数">
              <el-select v-model="qlFn" style="width: 240px" filterable>
                <el-option v-for="fn in quantlibFns" :key="fn.value" :label="fn.label" :value="fn.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="参数(JSON)">
              <el-input v-model="qlParams" placeholder='{"S":100,"K":100,"T":1,"r":0.05,"sigma":0.2,"option_type":"call"}' style="width: 420px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="qlLoading" @click="runQuantlib">计算</el-button>
            </el-form-item>
          </el-form>
          <el-alert v-if="qlError" type="warning" :title="qlError" show-icon style="margin-bottom: 12px" :closable="false" />
          <pre v-if="qlResult" class="ql-result">{{ qlResult }}</pre>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { use } from 'echarts/core'
import { CandlestickChart, LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { quantApi } from '@/api/quant'
// @ts-ignore stock-sdk 类型较新，宽松处理
import { StockSDK } from 'stock-sdk'

use([CandlestickChart, LineChart, BarChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, TitleComponent, CanvasRenderer])

const activeTab = ref('kline')

// ---------- ① 行情技术图 ----------
const klineSymbol = ref('600519')
const klineLoading = ref(false)
const klineError = ref('')
const klineOption = ref<any>(null)

async function loadKline() {
  const sym = klineSymbol.value.trim()
  if (!sym) { klineError.value = '请输入股票代码'; return }
  klineLoading.value = true
  klineError.value = ''
  try {
    const sdk = new StockSDK()
    const kline = await (sdk as any).kline.cn({ symbol: sym, adjust: 'qfq' })
    if (!kline || !kline.length) { klineError.value = '未获取到 K 线数据（网络或代码问题）'; return }
    const bars = kline.map((k: any) => [k.open, k.close, k.low, k.high])
    const dates = kline.map((k: any) => k.date || k.time)
    const closes = kline.map((k: any) => k.close)
    // 简单 MA 指标（前端计算）
    const ma = (n: number) => closes.map((_: number, i: number) => i < n - 1 ? null : +(closes.slice(i - n + 1, i + 1).reduce((a: number, b: number) => a + b, 0) / n).toFixed(2))
    klineOption.value = {
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      legend: { data: ['K线', 'MA5', 'MA20'] },
      grid: [{ left: 60, right: 20, top: 30, height: '60%' }],
      xAxis: [{ type: 'category', data: dates, scale: true }],
      yAxis: [{ scale: true }] as any,
      dataZoom: [{ type: 'inside', start: 60 }, { type: 'slider', start: 60 }],
      series: [
        { name: 'K线', type: 'candlestick', data: bars, itemStyle: { color: '#ef232a', color0: '#14b143', borderColor: '#ef232a', borderColor0: '#14b143' } },
        { name: 'MA5', type: 'line', data: ma(5), smooth: true, showSymbol: false, lineStyle: { width: 1 } },
        { name: 'MA20', type: 'line', data: ma(20), smooth: true, showSymbol: false, lineStyle: { width: 1 } }
      ]
    }
  } catch (e: any) {
    klineError.value = `行情获取失败: ${e?.message || e}（国内网络可能需代理）`
  } finally {
    klineLoading.value = false
  }
}

// ---------- ② 筹码分布 ----------
const chipsSymbol = ref('600519.SH')
const chipsLoading = ref(false)
const chipsError = ref('')
const chipsData = ref<any>(null)
const chipsOption = ref<any>(null)

async function loadChips() {
  const sym = chipsSymbol.value.trim()
  if (!sym) { chipsError.value = '请输入股票代码'; return }
  chipsLoading.value = true
  chipsError.value = ''
  chipsData.value = null
  try {
    const r: any = await quantApi.chips(sym)
    const d = r?.data || r
    if (!d || d.error) { chipsError.value = d?.error || '筹码分析失败'; return }
    chipsData.value = d
    const hist = (d.histogram || []).map((h: any) => [h[0], h[1]])
    chipsOption.value = {
      tooltip: { trigger: 'axis' },
      title: { text: `${sym} 筹码分布`, left: 'center', textStyle: { fontSize: 14 } },
      grid: { left: 60, right: 20, top: 40, bottom: 40 },
      xAxis: { type: 'value', name: '价格' },
      yAxis: { type: 'value', name: '筹码量' },
      series: [{ type: 'bar', data: hist, itemStyle: { color: '#409eff' }, barCategoryGap: 0 }]
    }
  } catch (e: any) {
    chipsError.value = `筹码分析失败: ${e?.message || e}`
  } finally {
    chipsLoading.value = false
  }
}

// ---------- ③ 因子选股 ----------
const factorList = ref<any[]>([])
const factorName = ref('')
const factorCond = ref<'top' | 'bottom'>('top')
const factorTopN = ref(10)
const factorSymbols = ref('600519,000001,300750')
const factorLoading = ref(false)
const factorError = ref('')
const factorResult = ref<any>(null)

onMounted(async () => {
  try {
    const r: any = await quantApi.factors()
    factorList.value = r?.data || []
    if (factorList.value.length) factorName.value = factorList.value[0].name
  } catch { /* 因子列表加载失败，静默 */ }
})

async function runFactorScreen() {
  const symbols = factorSymbols.value.split(',').map((s: string) => s.trim()).filter(Boolean)
  if (!factorName.value) { factorError.value = '请选择因子'; return }
  if (!symbols.length) { factorError.value = '请输入股票代码'; return }
  factorLoading.value = true
  factorError.value = ''
  try {
    const r: any = await quantApi.factorScreen({ factor: factorName.value, condition: factorCond.value, top_n: factorTopN.value, symbols })
    const d = r?.data
    if (d?.error) { factorError.value = d.error; return }
    factorResult.value = d
  } catch (e: any) {
    factorError.value = `筛选失败: ${e?.message || e}`
  } finally {
    factorLoading.value = false
  }
}

// ---------- ④ 策略回测 ----------
const btSymbol = ref('000001')
const btStrategy = ref<'buy_hold' | 'ma_cross' | 'rsi_reverse' | 'momentum'>('ma_cross')
const btStart = ref('20240101')
const btEnd = ref('20241231')
const btCapital = ref<number>(100000)
const btLoading = ref(false)
const btError = ref('')
const btResult = ref<any>(null)
const btOption = ref<any>(null)

async function runBacktest() {
  btLoading.value = true
  btError.value = ''
  btResult.value = null
  try {
    const r: any = await quantApi.backtest({
      symbol: btSymbol.value.trim(),
      strategy: btStrategy.value,
      start: btStart.value.trim(),
      end: btEnd.value.trim(),
      initial_capital: btCapital.value
    })
    const d = r?.data || r
    if (d?.error) { btError.value = d.error; return }
    btResult.value = d
    const eq = (d.equity_curve || []).map((p: any) => [p.date, p.value])
    const bench = (d.benchmark?.equity_curve || []).map((p: any) => [p.date, p.value])
    btOption.value = {
      tooltip: { trigger: 'axis' },
      legend: { data: ['策略', '基准(买入持有)'] },
      grid: { left: 60, right: 20, top: 30, bottom: 40 },
      xAxis: { type: 'category', data: (d.equity_curve || []).map((p: any) => p.date) },
      yAxis: { type: 'value', scale: true },
      dataZoom: [{ type: 'inside' }],
      series: [
        { name: '策略', type: 'line', data: eq, showSymbol: false, smooth: true },
        { name: '基准(买入持有)', type: 'line', data: bench, showSymbol: false, smooth: true, lineStyle: { type: 'dashed' } }
      ]
    }
  } catch (e: any) {
    btError.value = `回测失败: ${e?.message || e}`
  } finally {
    btLoading.value = false
  }
}

// ---------- ⑤ 金融计算器 ----------
const quantlibFns = [
  { value: 'bs_price', label: 'BS 定价 bs_price' },
  { value: 'bs_greeks', label: 'BS Greeks bs_greeks' },
  { value: 'implied_volatility', label: '隐含波动率 implied_volatility' },
  { value: 'historical_var', label: '历史 VaR historical_var' },
  { value: 'parametric_var', label: '参数 VaR parametric_var' },
  { value: 'historical_cvar', label: '历史 CVaR historical_cvar' },
  { value: 'max_drawdown_analysis', label: '回撤分析 max_drawdown_analysis' },
  { value: 'sharpe_ratio', label: '夏普比率 sharpe_ratio' },
  { value: 'sortino_ratio', label: 'Sortino 比率 sortino_ratio' },
  { value: 'xirr', label: 'XIRR 现金流收益率 xirr' },
  { value: 'irr', label: 'IRR 内部收益率 irr' }
]
const qlFn = ref('bs_price')
const qlParams = ref('{"S":100,"K":100,"T":1,"r":0.05,"sigma":0.2,"option_type":"call"}')
const qlLoading = ref(false)
const qlError = ref('')
const qlResult = ref('')

async function runQuantlib() {
  qlLoading.value = true
  qlError.value = ''
  qlResult.value = ''
  let params: any
  try {
    params = JSON.parse(qlParams.value)
  } catch {
    qlError.value = '参数不是合法 JSON'
    qlLoading.value = false
    return
  }
  try {
    const r: any = await quantApi.quantlib({ fn: qlFn.value, params })
    qlResult.value = JSON.stringify(r?.data ?? r, null, 2)
  } catch (e: any) {
    qlError.value = `计算失败: ${e?.message || e}`
  } finally {
    qlLoading.value = false
  }
}
</script>

<style scoped>
.quant-page :deep(.el-card__body) { padding: 16px; }
.chart-box { width: 100%; }
.k-chart { height: 420px; }
.stat-label { color: #909399; font-size: 13px; margin-bottom: 4px; }\n.stat-value { font-size: 20px; font-weight: 600; }\n.ql-result { background: #f5f7fa; border-radius: 6px; padding: 12px; font-size: 13px; max-height: 320px; overflow: auto; white-space: pre-wrap; word-break: break-all; }
</style>