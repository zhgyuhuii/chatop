import { useState } from 'react'
import { configureAgent, installAgent, openAgent } from '../api'

export type Agent = {
  id: string; name: string; installed: boolean; agent_type?: string
  configured?: boolean; model?: string; running?: boolean
  active_sessions?: number; cpu?: number; mem_mb?: number
  dispatchable?: boolean; openable?: boolean; configurable?: boolean
}

const TYPE_LABEL: Record<string, string> = { runtime: '常驻', session: '会话式', human: '人工桌面' }

const statusDot = (a: Agent) =>
  !a.installed ? 'idle' : a.running || (a.active_sessions ?? 0) > 0 ? 'ok' : a.configured ? 'idle' : 'warn'

export default function AgentWall({ agents, onPick }: { agents: Agent[]; onPick: (id: string) => void }) {
  const [note, setNote] = useState('')
  const act = (fn: (id: string) => Promise<unknown>, id: string, label: string) =>
    fn(id).then(() => setNote(`${label} ${id} ✓`)).catch(e => setNote(`${label} ${id} 失败: ${e.message}`))
  if (!agents.length)
    return <div className="panel muted">catalog 不可用——检查 app-manager</div>
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 10 }}>
        {agents.map(a => (
          <div key={a.id} className="panel">
            <div><span className={`dot ${statusDot(a)}`} /><strong>{a.name}</strong>
              <span className="muted"> {TYPE_LABEL[a.agent_type ?? ''] ?? ''}</span></div>
            {a.installed ? (
              <>
                <div className="muted">{a.configured ? `模型: ${a.model || '已配置'}` : '⚠ 未配置'}</div>
                <div className="muted">
                  {a.running ? `运行中 CPU ${a.cpu}% MEM ${a.mem_mb}M` : `活动会话 ${a.active_sessions ?? 0}`}
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                  {a.openable && <button onClick={() => act(openAgent, a.id, '打开')}>打开</button>}
                  {a.configurable && <button onClick={() => act(configureAgent, a.id, '配置')}>配置</button>}
                  {a.dispatchable && <button onClick={() => onPick(a.id)}>派活</button>}
                </div>
              </>
            ) : (
              <div style={{ marginTop: 6 }}>
                <div className="muted">未安装</div>
                <button onClick={() => act(installAgent, a.id, '安装')}>安装</button>
              </div>
            )}
          </div>
        ))}
      </div>
      {note && <div className="muted" style={{ marginTop: 6 }}>{note}（安装进度见应用管理）</div>}
    </div>
  )
}
