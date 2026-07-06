import { computeKpis, type TaskLike } from '../kpis'

const EMBED = new URLSearchParams(location.search).get('embed') === '1'

export default function TopBar({ tasks, agents, sys, connected }: {
  tasks: TaskLike[]; agents: { installed?: boolean; running?: boolean }[]
  sys: { cpu?: number; mem?: number; disk?: number }; connected: boolean
}) {
  const k = computeKpis(tasks)
  const installed = agents.filter(a => a.installed).length
  const running = agents.filter(a => a.running).length
  return (
    <header className="panel" style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
      {!EMBED && <strong style={{ color: 'var(--accent)' }}>🖥️ 工位大屏</strong>}
      <span><span className={`dot ${connected ? 'ok' : 'err'}`} />{connected ? '事件流已连' : '事件流断开'}</span>
      <span className="muted">独立模式</span>
      <span>智能体 {installed} 装 / {running} 跑</span>
      <span>任务 {k.total} · 运行 {k.running} · 待批 {k.waiting} · 成功率 {(k.successRate * 100).toFixed(0)}%</span>
      <span className="muted">CPU {sys.cpu ?? '–'}% · MEM {sys.mem ?? '–'}% · DISK {sys.disk ?? '–'}%</span>
      {!EMBED && <span className="muted" style={{ marginLeft: 'auto' }}>{new Date().toLocaleTimeString()}</span>}
    </header>
  )
}
