import { describe, expect, it } from 'vitest'
import { applyEvent, initialStream, type StreamEvent, type StreamState } from './streamReducer'

const ev = (kind: string, jobId = 'j1', payload: Record<string, unknown> = {}): StreamEvent =>
  ({ job_id: jobId, kind, seq: 1, payload, ts: 1 })

describe('applyEvent', () => {
  it('progress 记录当前步与最近动作', () => {
    const s = applyEvent(initialStream(), ev('progress', 'j1', { text: 'editing' }))
    expect(s.jobs['j1'].state).toBe('running')
    expect(s.jobs['j1'].step).toBe('editing')
  })
  it('succeeded/failed 落终态', () => {
    let s: StreamState = applyEvent(initialStream(), ev('progress'))
    s = applyEvent(s, ev('succeeded'))
    expect(s.jobs['j1'].state).toBe('succeeded')
  })
  it('累计 tokens', () => {
    let s = applyEvent(initialStream(), ev('progress', 'j1', { tokens: 5 }))
    s = applyEvent(s, ev('succeeded', 'j1', { tokens: 7 }))
    expect(s.jobs['j1'].tokens).toBe(12)
  })
})
