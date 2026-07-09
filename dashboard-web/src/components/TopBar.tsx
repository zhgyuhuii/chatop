import { computeKpis, type TaskLike } from '../kpis'
import { t } from '../i18n'

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
      {!EMBED && <strong style={{ color: 'var(--accent)' }}>🖥️ {t('Workstation Dashboard')}</strong>}
      <span><span className={`dot ${connected ? 'ok' : 'err'}`} />{connected ? t('Event stream connected') : t('Event stream disconnected')}</span>
      <span className="muted">{t('Standalone mode')}</span>
      <span>{t('Agents {installed} installed / {running} running', { installed, running })}</span>
      <span>{t('Tasks {total} · Running {running} · Pending {waiting} · Success {rate}%',
        { total: k.total, running: k.running, waiting: k.waiting, rate: (k.successRate * 100).toFixed(0) })}</span>
      <span className="muted">CPU {sys.cpu ?? '–'}% · MEM {sys.mem ?? '–'}% · DISK {sys.disk ?? '–'}%</span>
      {!EMBED && <span className="muted" style={{ marginLeft: 'auto' }}>{new Date().toLocaleTimeString()}</span>}
    </header>
  )
}
