import type { StreamState } from '../streamReducer'

export type Task = {
  id: string; agent: string; goal: string; state: string
  current_step: string; tokens: number; source: string; created_at: number
}
const ICON: Record<string, string> = {
  running: '▶', succeeded: '✓', failed: '✗', pending_approval: '⏸', queued: '…', cancelled: '⊘',
}

export default function TaskList({ tasks, live }: { tasks: Task[]; live: StreamState }) {
  if (!tasks.length) return <div className="panel muted">暂无任务——左侧派一个试试</div>
  return (
    <div className="panel" style={{ overflowY: 'auto', maxHeight: '60vh' }}>
      {tasks.map(t => {
        const l = live.jobs[t.id]
        const state = l?.state && t.state === 'running' ? l.state : t.state
        const step = l?.step || t.current_step
        return (
          <div key={t.id} style={{ borderBottom: '1px solid var(--line)', padding: '6px 0' }}>
            <div>{ICON[state] ?? '·'} <strong>{t.goal.slice(0, 60)}</strong>
              <span className="muted"> @{t.agent} · {state}{t.source === 'detected' ? ' · 侦测' : ''}</span></div>
            {step && <div className="muted" style={{ paddingLeft: 18 }}>└ {step.slice(0, 80)}</div>}
          </div>
        )
      })}
    </div>
  )
}
