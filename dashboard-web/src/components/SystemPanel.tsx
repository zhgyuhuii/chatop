import { t } from '../i18n'

export type Sys = {
  cpu?: number; mem?: number; disk?: number; uptime?: number
  services?: { name: string; ok: boolean }[]; ports?: number[]; vnc_online?: boolean
}

export default function SystemPanel({ sys }: { sys: Sys }) {
  return (
    <div className="panel">
      <div><strong>{t('Container status')}</strong>
        <span className="muted"> {t('Up {hours}h', { hours: Math.floor((sys.uptime ?? 0) / 3600) })}</span></div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 6 }}>
        {(sys.services ?? []).map(s => (
          <span key={s.name}><span className={`dot ${s.ok ? 'ok' : 'err'}`} />{s.name}</span>
        ))}
        <span><span className={`dot ${sys.vnc_online ? 'ok' : 'idle'}`} />{t('VNC session')}</span>
      </div>
      <div className="muted" style={{ marginTop: 6 }}>
        {t('Listening ports: {ports}', { ports: (sys.ports ?? []).join(', ') || '–' })}
      </div>
    </div>
  )
}
