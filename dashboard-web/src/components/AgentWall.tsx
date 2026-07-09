import { useState } from 'react'
import { configureAgent, installAgent, openAgent } from '../api'
import { t } from '../i18n'

export type Agent = {
  id: string; name: string; installed: boolean; agent_type?: string
  configured?: boolean; model?: string; running?: boolean
  active_sessions?: number; cpu?: number; mem_mb?: number
  dispatchable?: boolean; openable?: boolean; configurable?: boolean
}

const TYPE_LABEL: Record<string, string> = {
  runtime: t('Resident'), session: t('Session-based'), human: t('Human desktop'),
}

const statusDot = (a: Agent) =>
  !a.installed ? 'idle' : a.running || (a.active_sessions ?? 0) > 0 ? 'ok' : a.configured ? 'idle' : 'warn'

export default function AgentWall({ agents, onPick }: { agents: Agent[]; onPick: (id: string) => void }) {
  const [note, setNote] = useState('')
  const act = (fn: (id: string) => Promise<unknown>, id: string, label: string) =>
    fn(id).then(() => setNote(`${label} ${id} ✓`))
      .catch(e => setNote(t('{label} {id} failed: {err}', { label, id, err: e.message })))
  if (!agents.length)
    return <div className="panel muted">{t('catalog unavailable — check app-manager')}</div>
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 10 }}>
        {agents.map(a => (
          <div key={a.id} className="panel">
            <div><span className={`dot ${statusDot(a)}`} /><strong>{a.name}</strong>
              <span className="muted"> {TYPE_LABEL[a.agent_type ?? ''] ?? ''}</span></div>
            {a.installed ? (
              <>
                <div className="muted">{a.configured
                  ? t('Model: {model}', { model: a.model || t('Configured') })
                  : `⚠ ${t('Not configured')}`}</div>
                <div className="muted">
                  {a.running
                    ? t('Running CPU {cpu}% MEM {mem}M', { cpu: a.cpu ?? 0, mem: a.mem_mb ?? 0 })
                    : t('Active sessions {n}', { n: a.active_sessions ?? 0 })}
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                  {a.openable && <button onClick={() => act(openAgent, a.id, t('Open'))}>{t('Open')}</button>}
                  {a.configurable && <button onClick={() => act(configureAgent, a.id, t('Configure'))}>{t('Configure')}</button>}
                  {a.dispatchable && <button onClick={() => onPick(a.id)}>{t('Dispatch')}</button>}
                </div>
              </>
            ) : (
              <div style={{ marginTop: 6 }}>
                <div className="muted">{t('Not installed')}</div>
                <button onClick={() => act(installAgent, a.id, t('Install'))}>{t('Install')}</button>
              </div>
            )}
          </div>
        ))}
      </div>
      {note && <div className="muted" style={{ marginTop: 6 }}>
        {note} {t('(installation progress in Application Manager)')}
      </div>}
    </div>
  )
}
