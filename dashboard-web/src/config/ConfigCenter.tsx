import { useEffect, useState } from 'react'
import {
  describe, getAgents, health,
  type AgentStatus, type Descriptor, type Diagnostic,
} from './configApi'
import { useConfigEvents } from './useConfigEvents'
import ModelPanel from './ModelPanel'
import ChannelPanel from './ChannelPanel'
import AssistantChat from './AssistantChat'
import GroupRenderer from './GroupRenderer'
import { t } from '../i18n'

// 助手动作 → UI 目标态的纯归约函数。open_auth_flow 带 channel 时归约为 { channel }，
// open_model_panel 带 provider 时归约为 { provider }，其余（未知 action / 缺目标）归约为 {}。
export function actionToTarget(a: { type: string; channel?: string; provider?: string }) {
  if (a.type === 'open_auth_flow' && a.channel) return { channel: a.channel }
  if (a.type === 'open_model_panel' && a.provider) return { provider: a.provider }
  return {}
}

// 智能体统一配置中心。openclaw / hermes 一期；claude-code 等仅在总览显示状态。
export default function ConfigCenter() {
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [agentId, setAgentId] = useState('openclaw')
  const [desc, setDesc] = useState<Descriptor | null>(null)
  const [diags, setDiags] = useState<Diagnostic[]>([])
  const [activeChannel, setActiveChannel] = useState<string>()
  const [activeProvider, setActiveProvider] = useState<string>()
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
          <b style={{ marginRight: 8 }}>{t('Agent Config Center')}</b>
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
          <button onClick={runHealth}>{t('One-click health check')}</button>
        </div>

        {diags.length > 0 && (
          <div className="panel" style={{ display: 'grid', gap: 4 }}>
            <b>{t('Health check')}</b>
            {diags.map(d => (
              <div key={d.id} style={{ fontSize: 13 }}>
                <span className={'dot ' + (d.level === 'ok' ? 'ok' : d.level === 'error' ? 'err' : 'warn')} />
                {d.message}
                {d.auto_fix ? <span className="muted" style={{ fontSize: 11 }}>（{t('auto-fix: {fix}', { fix: d.auto_fix })}）</span> : null}
              </div>
            ))}
          </div>
        )}

        <ModelPanel agentId={agentId} desc={desc} initialProvider={activeProvider}
                    onSaved={() => { reloadDesc(); reloadAgents() }} />

        {desc?.groups
          .filter(g => g.id !== 'channels' && g.id !== 'model' && g.fields.some(f => f.kind !== 'model'))
          .map(g => <GroupRenderer key={g.id} agentId={agentId} group={g}
                                   onSaved={() => { reloadDesc(); reloadAgents() }} />)}

        {channelGroup && channelGroup.channels.length > 0 && (
          <ChannelPanel agentId={agentId} channels={channelGroup.channels} flowEvents={flowEvents}
                        activeChannel={activeChannel} />
        )}
        {agentId === 'openclaw' && channelGroup && channelGroup.channels.length === 0 && (
          <div className="panel muted" style={{ fontSize: 12 }}>
            {t('Channel list not ready (needs an openclaw directory snapshot). Refresh after running directory collection inside the container.')}
          </div>
        )}
      </div>

      <AssistantChat agentId={agentId}
        onAction={a => {
          const tgt = actionToTarget(a)
          if (tgt.channel) setActiveChannel(tgt.channel)
          if (tgt.provider) setActiveProvider(tgt.provider)
          if (tgt.channel || tgt.provider) reloadDesc()
        }} />
    </div>
  )
}
