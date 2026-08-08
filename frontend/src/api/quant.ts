// 量化工具 API 封装
import request from '@/api/request'

export const quantApi = {
  // 筹码分布
  chips(symbol: string) {
    return request.get(`/api/strategy/chips/${symbol}`, { timeout: 120000, retryCount: 0 } as any)
  },
  // 因子列表
  factors() {
    return request.get('/api/strategy/factors', { timeout: 30000, retryCount: 0 } as any)
  },
  // 因子选股
  factorScreen(data: { factor: string; condition: 'top' | 'bottom'; top_n: number; symbols: string[] }) {
    return request.post('/api/strategy/factor-screen', data, { timeout: 600000, retryCount: 0 } as any)
  },
  // 回测
  backtest(data: {
    symbol: string
    strategy: 'buy_hold' | 'ma_cross' | 'rsi_reverse' | 'momentum'
    start: string
    end: string
    params?: Record<string, any>
    initial_capital?: number
  }) {
    return request.post('/api/strategy/backtest', data, { timeout: 300000, retryCount: 0 } as any)
  },
  // 金融计算器
  quantlib(data: { fn: string; params: Record<string, any> }) {
    return request.post('/api/strategy/quantlib', data, { timeout: 30000, retryCount: 0 } as any)
  }
}