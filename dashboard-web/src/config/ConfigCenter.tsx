import { useEffect, useState } from 'react'
import {
  describe, getAgents, health,
  type AgentStatus, type Descriptor, type Diagnostic,
} from './configApi'
import { useConfigEvents } from './useConfigEvents'
import ModelPanel from './ModelPanel'
import ChannelPanel from './ChannelPanel'
import AssistantChat from './AssistantChat'

// 智能体统一配置中心。openclaw / hermes 一期；claude-code 等仅在总览显示状态。
export default function ConfigCenter() {
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [agentId, setAgentId] = useState('openclaw')
  const [desc, setDesc] = useState<Descriptor | null>(null)
  const [diags, setDiags] = useState<Diagnostic[]>([])
  const flowEvents = useConfigEvents()

  const reloadAgents = () => getAgents().then(setAgents).catch(() => {})
  const reloadDesc = () => describe(agentId).then(setDesc).catch(() => setDesc(null))

  useEffect(() => { reloadAgents() }, [])
  useEffect(() => { setDesc(null); reloadDesc(); setDiags([]) }, [agentId])

  const runHealth = () => health(agentId).then(setDiags).catch(() => {})

  const channelGroup = desc?.groups.find(g => g.id === 'channels')

  return (
    <div style={{ display: 'grid', gap: 10, padding: 12, minHeight: '100vh',
                  gridTemplateColumns: '1.6fr 1fr' }}>
      <div style={{ display: 'grid', gap: 10, alignContent: 'start' }}>
        <div className="panel" style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <b style={{ marginRight: 8 }}>智能体配置中心</b>
          {agents.map(a => (
            <button key={a.id} onClick={() => setAgentId(a.id)}
                    disabled={a.id !== 'openclaw' && a.id !== 'hermes'}
                    style={{ borderColor: agentId === a.id ? 'var(--accent)' : undefined }}>
              <span className={'dot ' + (a.running ? 'ok' : a.configured ? 'warn' : 'idle')} />
              {a.label}
              {a.version ? <span className="muted" style={{ fontSize: 11 }}> {a.version}</span> : null}
            </button>
          ))}
          <span style={{ flex: 1 }} />
          <button onClick={runHealth}>一键体检</button>
        </div>

        {diags.length > 0 && (
          <div className="panel" style={{ display: 'grid', gap: 4 }}>
            <b>体检</b>
            {diags.map(d => (
              <div key={d.id} style={{ fontSize: 13 }}>
                <span className={'dot ' + (d.level === 'ok' ? 'ok' : d.level === 'error' ? 'err' : 'warn')} />
                {d.message}
                {d.auto_fix ? <span className="muted" style={{ fontSize: 11 }}>（可自愈：{d.auto_fix}）</span> : null}
              </div>
            ))}
          </div>
        )}

        <ModelPanel agentId={agentId} desc={desc} onSaved={() => { reloadDesc(); reloadAgents() }} />

        {channelGroup && channelGroup.channels.length > 0 && (
          <ChannelPanel agentId={agentId} channels={channelGroup.channels} flowEvents={flowEvents} />
        )}
        {agentId === 'openclaw' && channelGroup && channelGroup.channels.length === 0 && (
          <div className="panel muted" style={{ fontSize: 12 }}>
            通道清单尚未就绪（需 openclaw 目录快照）。可在容器内运行目录采集后刷新。
          </div>
        )}
      </div>

      <AssistantChat agentId={agentId}
        onAction={a => { if (a.channel || a.provider) reloadDesc() }} />
    </div>
  )
}
