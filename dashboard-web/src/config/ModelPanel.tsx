import { useEffect, useState } from 'react'
import {
  apply, fetchModels, fetchProviders,
  type Descriptor, type ModelInfo, type ProviderInfo,
} from './configApi'
import { readPrimaryModel } from './modelPrimary'

export default function ModelPanel({ agentId, desc, onSaved }: {
  agentId: string; desc: Descriptor | null; onSaved: () => void
}) {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [reason, setReason] = useState('')
  const [source, setSource] = useState('')
  const [primary, setPrimary] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const current = readPrimaryModel(agentId, desc)
  const selected = providers.find(p => p.id === provider)
  const isOauth = selected?.auth_kind === 'oauth'
  const showBaseUrl = provider === 'ollama' || showAdvanced

  useEffect(() => {
    fetchProviders(agentId).then(setProviders).catch(() => {})
  }, [agentId])

  useEffect(() => {
    if (!provider && providers[0]) setProvider(providers[0].id)
  }, [providers, provider])

  const load = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await fetchModels(agentId, provider, apiKey, baseUrl || undefined)
      setModels(r.models); setSource(r.source); setReason(r.reason)
      if (r.models[0]) setPrimary(r.models[0].key)
    } catch { setReason('请求失败') } finally { setBusy(false) }
  }

  const save = async () => {
    if (!primary) return
    setBusy(true); setMsg('')
    try {
      // openclaw 主模型路径；hermes 用 model 字段。
      const patch = agentId === 'hermes'
        ? { model: primary }
        : { agents: { defaults: { model: { primary } } } }
      const r = await apply(agentId, patch)
      setMsg(r.ok ? '已保存主模型：' + primary : '保存失败')
      onSaved()
    } finally { setBusy(false) }
  }

  return (
    <div className="panel" style={{ display: 'grid', gap: 8 }}>
      <b>模型</b>
      <div className="muted" style={{ fontSize: 12 }}>
        当前主模型：{current || '未设置'}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={provider} onChange={e => setProvider(e.target.value)}>
          {providers.map(p => <option key={p.id} value={p.id}>{p.label || p.id}</option>)}
        </select>
        {isOauth ? (
          <span style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
            {selected?.apply_url && (
              <a href={selected.apply_url} target="_blank" rel="noreferrer">前往授权 ↗</a>
            )}
            <span className="muted">授权后回来点获取模型</span>
          </span>
        ) : provider !== 'ollama' && (
          <input type="password" placeholder="API Key" value={apiKey}
                 onChange={e => setApiKey(e.target.value)} style={{ width: 220 }} />
        )}
        <button disabled={busy} onClick={load}>获取模型</button>
      </div>
      {!isOauth && provider !== 'ollama' && (
        <label style={{ fontSize: 12, display: 'flex', gap: 4, alignItems: 'center' }}>
          <input type="checkbox" checked={showAdvanced}
                 onChange={e => setShowAdvanced(e.target.checked)} />
          高级
        </label>
      )}
      {showBaseUrl && (
        <input placeholder="自定义端点 (base_url)，留空用默认" value={baseUrl}
               onChange={e => setBaseUrl(e.target.value)} style={{ width: 320, fontSize: 12 }} />
      )}
      {reason && <div className="muted" style={{ fontSize: 12,
        color: source === 'snapshot' ? 'var(--warn)' : undefined }}>{reason}</div>}
      {models.length > 0 && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="muted" style={{ fontSize: 12 }}>
            主模型（{source === 'live' ? '实时' : '快照'}）：
          </span>
          <select value={primary} onChange={e => setPrimary(e.target.value)} style={{ minWidth: 240 }}>
            {models.map(m => <option key={m.key} value={m.key}>{m.key}</option>)}
          </select>
          <button disabled={busy || !primary} onClick={save}>设为主模型</button>
        </div>
      )}
      {msg && <div style={{ fontSize: 12, color: 'var(--ok)' }}>{msg}</div>}
    </div>
  )
}
