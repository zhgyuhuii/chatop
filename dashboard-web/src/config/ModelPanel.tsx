import { useState } from 'react'
import { apply, fetchModels, type Descriptor, type ModelInfo } from './configApi'

// 策展厂商（与引擎 catalog_overrides.MODEL_PROVIDERS 对齐的常用子集；下拉够用即可）。
const PROVIDERS = [
  ['ollama', 'Ollama（本地，无需 Key）'], ['deepseek', 'DeepSeek 深度求索'],
  ['zai', '智谱 GLM'], ['moonshot', '月之暗面 Kimi'], ['volcengine', '火山方舟（豆包）'],
  ['openai', 'OpenAI'], ['anthropic', 'Anthropic Claude'], ['mistral', 'Mistral'],
  ['groq', 'Groq'], ['openrouter', 'OpenRouter'], ['cohere', 'Cohere'],
] as const

export default function ModelPanel({ agentId, desc, onSaved }: {
  agentId: string; desc: Descriptor | null; onSaved: () => void
}) {
  const [provider, setProvider] = useState('deepseek')
  const [apiKey, setApiKey] = useState('')
  const [models, setModels] = useState<ModelInfo[]>([])
  const [reason, setReason] = useState('')
  const [source, setSource] = useState('')
  const [primary, setPrimary] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const current = desc?.groups.find(g => g.id === 'model')
    ?.fields.find(f => f.key.endsWith('model.primary'))?.value as string | undefined

  const load = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await fetchModels(agentId, provider, apiKey)
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
          {PROVIDERS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
        {provider !== 'ollama' && (
          <input type="password" placeholder="API Key" value={apiKey}
                 onChange={e => setApiKey(e.target.value)} style={{ width: 220 }} />
        )}
        <button disabled={busy} onClick={load}>获取模型</button>
      </div>
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
