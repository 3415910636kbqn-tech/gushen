/**
 * 策略分析 API
 * 对接后端 /api/strategy/* 三个接口：
 *   NDX 动量对冲信号 / 龟龟估值 / 龟龟选股
 */

import { request } from './request'

// NDX 动量对冲信号数据结构
export interface NdxMomentumItem {
  symbol: string
  momentum: number       // 20日动量(%)
  momentum_5d: number    // 5日动量(%)
  price: number          // 最新价
}

export interface NdxMomentumData {
  date: string
  week_start: string
  pool_size: number
  momentum_top5: NdxMomentumItem[]
  top_symbols: string[]
  changes: {
    added: string[]
    removed: string[]
    kept: string[]
  }
  performance: {
    strategy_w: number
    qqq_w: number
    psq_w: number
  }
  qqq_12w: Array<{ date: string; qqq: number; psq: number }>
  full_momentum?: NdxMomentumItem[]
}

// 龟龟估值结果数据结构
export interface TurtleValuationData {
  ts_code: string
  markdown: string
  classification: Record<string, any> | null
  wacc: Record<string, any> | null
}

// 龟龟选股参数
export interface TurtleScreenerParams {
  tier1_only?: boolean
  tier2_limit?: number
}

// 策略分析 API
export const strategyApi = {
  // NDX 动量对冲信号（美股数据源不可用时后端返回 502，组件内需友好提示）
  ndxMomentum(): Promise<any> {
    return request.get('/api/strategy/ndx-momentum', { timeout: 120000, retryCount: 0 })
  },

  // 龟龟估值分析（akshare 拉取财务数据，放宽超时）
  turtleValuation(code: string): Promise<any> {
    return request.get(`/api/strategy/turtle-valuation/${code}`, { timeout: 180000, retryCount: 0 })
  },

  // 龟龟选股（Tier1 全市场筛选可能需 1-5 分钟，超时放宽到 10 分钟）
  turtleScreener(params: TurtleScreenerParams): Promise<any> {
    return request.get('/api/strategy/turtle-screener', { params, timeout: 600000, retryCount: 0 })
  }
}
