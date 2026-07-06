import { describe, expect, it } from 'vitest'
import { computeKpis } from './kpis'

describe('computeKpis', () => {
  it('统计各态与成功率', () => {
    const k = computeKpis([
      { state: 'running' }, { state: 'succeeded' }, { state: 'succeeded' },
      { state: 'failed' }, { state: 'pending_approval' },
    ])
    expect(k).toEqual({ total: 5, running: 1, waiting: 1, succeeded: 2, failed: 1, successRate: 2 / 3 })
  })
  it('无终态成功率为 0', () => {
    expect(computeKpis([]).successRate).toBe(0)
  })
})
