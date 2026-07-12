export type StreamEvent = {
  job_id: string; kind: string; seq: number
  payload: Record<string, unknown>; ts: number
}
export type JobLive = { state: string; step: string; tokens: number; lastTs: number }
export type StreamState = { jobs: Record<string, JobLive> }

export const initialStream = (): StreamState => ({ jobs: {} })

export function applyEvent(s: StreamState, ev: StreamEvent): StreamState {
  // 配置中心的 flow 事件也走同一条 SSE，但没有 job_id；无 job_id 的事件不属于任务流，
  // 忽略之，否则会往 jobs 里塞一个 key 为 undefined 的幽灵任务。
  if (!ev.job_id) return s
  const prev = s.jobs[ev.job_id] ?? { state: 'running', step: '', tokens: 0, lastTs: 0 }
  const terminal = ev.kind === 'succeeded' || ev.kind === 'failed'
  const next: JobLive = {
    state: terminal ? ev.kind : prev.state,
    step: typeof ev.payload.text === 'string' && ev.payload.text ? ev.payload.text : prev.step,
    tokens: prev.tokens + (typeof ev.payload.tokens === 'number' ? ev.payload.tokens : 0),
    lastTs: ev.ts,
  }
  return { jobs: { ...s.jobs, [ev.job_id]: next } }
}
