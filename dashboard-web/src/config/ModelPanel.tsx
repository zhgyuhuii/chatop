import { useEffect, useState } from 'react'
import {
  apply, fetchModels, fetchProviders,
  type Descriptor, type ModelInfo, type ProviderInfo,
} from './configApi'
import { readPrimaryModel, readFallbacks } from './modelPrimary'
import { t } from '../i18n'

// openclaw 写 agents.defaults.model.{primary,fallbacks}；hermes 只写裸 model 字段（无备选）。
export function buildModelPatch(agentId: string, primary: string, fallbacks: string[]) {
  if (agentId === 'hermes') return { model: primary }
  const model: Record<string, unknown> = { primary }
  if (fallbacks.length) model.fallbacks = fallbacks
  return { agents: { defaults: { model } } }
}

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
  const [fallbacks, setFallbacks] = useState<string[]>([])
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

  useEffect(() => {
    setFallbacks(readFallbacks(agentId, desc))
  }, [agentId, desc])

  useEffect(() => {
    setFallbacks(prev => prev.filter(k => k !== primary))
  }, [primary])

  const load = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await fetchModels(agentId, provider, apiKey, baseUrl || undefined)
      setModels(r.models); setSource(r.source); setReason(r.reason)
      if (r.models[0]) setPrimary(r.models[0].key)
    } catch { setReason(t('Request failed')) } finally { setBusy(false) }
  }

  const save = async () => {
    if (!primary) return
    setBusy(true); setMsg('')
    try {
      const patch = buildModelPatch(agentId, primary, fallbacks)
      const r = await apply(agentId, patch)
      setMsg(r.ok ? t('Primary model saved: {model}', { model: primary }) : t('Save failed'))
      onSaved()
    } finally { setBusy(false) }
  }

  return (
    <div className="panel" style={{ display: 'grid', gap: 8 }}>
      <b>{t('Model')}</b>
      <div className="muted" style={{ fontSize: 12 }}>
        {t('Current primary model:')}{current || t('Not set')}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={provider} onChange={e => setProvider(e.target.value)}>
          {providers.map(p => <option key={p.id} value={p.id}>{p.label || p.id}</option>)}
        </select>
        {isOauth ? (
          <span style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
            {selected?.apply_url && (
              <a href={selected.apply_url} target="_blank" rel="noreferrer">{t('Go authorize ↗')}</a>
            )}
            <span className="muted">{t('Return here after authorizing, then fetch models')}</span>
          </span>
        ) : provider !== 'ollama' && (
          <input type="password" placeholder="API Key" value={apiKey}
                 onChange={e => setApiKey(e.target.value)} style={{ width: 220 }} />
        )}
        <button disabled={busy} onClick={load}>{t('Fetch models')}</button>
      </div>
      {!isOauth && provider !== 'ollama' && (
        <label style={{ fontSize: 12, display: 'flex', gap: 4, alignItems: 'center' }}>
          <input type="checkbox" checked={showAdvanced}
                 onChange={e => setShowAdvanced(e.target.checked)} />
          {t('Advanced')}
        </label>
      )}
      {showBaseUrl && (
        <input placeholder={t('Custom endpoint (base_url), leave blank for default')} value={baseUrl}
               onChange={e => setBaseUrl(e.target.value)} style={{ width: 320, fontSize: 12 }} />
      )}
      {reason && <div className="muted" style={{ fontSize: 12,
        color: source === 'snapshot' ? 'var(--warn)' : undefined }}>{reason}</div>}
      {models.length > 0 && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="muted" style={{ fontSize: 12 }}>
            {t('Primary model ({source}):', { source: source === 'live' ? t('Live') : t('Snapshot') })}
          </span>
          <select value={primary} onChange={e => setPrimary(e.target.value)} style={{ minWidth: 240 }}>
            {models.map(m => <option key={m.key} value={m.key}>{m.key}</option>)}
          </select>
          <button disabled={busy || !primary} onClick={save}>{t('Set as primary')}</button>
        </div>
      )}
      {models.length > 0 && agentId !== 'hermes' && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <span className="muted" style={{ fontSize: 12, marginTop: 4 }}>{t('Fallback models (multi-select):')}</span>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', maxWidth: 420 }}>
            {models.filter(m => m.key !== primary).map(m => (
              <label key={m.key} style={{ fontSize: 12, display: 'flex', gap: 4, alignItems: 'center' }}>
                <input type="checkbox" checked={fallbacks.includes(m.key)}
                       onChange={e => setFallbacks(prev => e.target.checked
                         ? [...prev, m.key]
                         : prev.filter(k => k !== m.key))} />
                {m.key}
              </label>
            ))}
          </div>
        </div>
      )}
      {msg && <div style={{ fontSize: 12, color: 'var(--ok)' }}>{msg}</div>}
    </div>
  )
}
