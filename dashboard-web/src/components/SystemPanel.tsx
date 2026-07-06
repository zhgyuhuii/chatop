export type Sys = {
  cpu?: number; mem?: number; disk?: number; uptime?: number
  services?: { name: string; ok: boolean }[]; ports?: number[]; vnc_online?: boolean
}

export default function SystemPanel({ sys }: { sys: Sys }) {
  return (
    <div className="panel">
      <div><strong>容器运行状态</strong>
        <span className="muted"> 运行 {Math.floor((sys.uptime ?? 0) / 3600)}h</span></div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 6 }}>
        {(sys.services ?? []).map(s => (
          <span key={s.name}><span className={`dot ${s.ok ? 'ok' : 'err'}`} />{s.name}</span>
        ))}
        <span><span className={`dot ${sys.vnc_online ? 'ok' : 'idle'}`} />VNC 会话</span>
      </div>
      <div className="muted" style={{ marginTop: 6 }}>监听端口: {(sys.ports ?? []).join(', ') || '–'}</div>
    </div>
  )
}
