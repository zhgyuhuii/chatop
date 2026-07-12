import { useEffect, useState } from 'react'
import {
  apply, authFlow, getTutorial, startAuthFlow, interactionFor, interactionLabel,
  type ChannelSummary, type AuthFlow, type Tutorial,
} from './configApi'
import QrCanvas from './QrCanvas'
import type { ConfigEvent } from './useConfigEvents'

export default function ChannelPanel({ agentId, channels, flowEvents }: {
  agentId: string; channels: ChannelSummary[]; flowEvents: ConfigEvent[]
}) {
  const [active, setActive] = useState<string>('')
  const [flow, setFlow] = useState<AuthFlow | null>(null)
  const [tut, setTut] = useState<Tutorial | null>(null)
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [qr, setQr] = useState<number[][] | null>(null)
  const [status, setStatus] = useState('')
  const [msg, setMsg] = useState('')

  const open = async (ch: ChannelSummary) => {
    setActive(ch.id); setFlow(null); setTut(null); setQr(null); setStatus(''); setMsg('')
    setInputs({})
    const [f, t] = await Promise.all([authFlow(agentId, ch.id), getTutorial(agentId, ch.id)])
    setFlow(f); setTut(t)
  }

  // 监听 SSE：抓到本通道二维码矩阵就渲染。
  useEffect(() => {
    if (!active) return
    for (const ev of flowEvents) {
      if (ev.channel && ev.channel !== active) continue
      if (ev.type === 'flow:qr_ready' && ev.matrix) setQr(ev.matrix)
      if (ev.type === 'flow:qr_missing') setStatus(ev.reason || '未抓到二维码，请在终端窗口扫码')
      if (ev.type === 'flow:connected') setStatus('已连接')
      if (ev.type === 'flow:error') setStatus('扫码启动失败：' + (ev.reason || '未知错误'))
    }
  }, [flowEvents, active])

  const enableAndSave = async () => {
    setMsg('')
    const patch: Record<string, unknown> = { channels: { [active]: { enabled: true, ...inputs } } }
    // token 字段的 key 是完整点路径，需要展开
    const nested: Record<string, unknown> = { channels: { [active]: { enabled: true } } }
    for (const f of flow?.fields || []) {
      const v = inputs[f.key]
      if (v) setDotted(nested, f.key, v)
    }
    const r = await apply(agentId, flow?.fields.length ? nested : patch)
    setMsg(r.ok ? '已保存' + (r.removed.length ? `（清理：${r.removed.join(', ')}）` : '') : '保存失败')
  }

  const startScan = async () => {
    setStatus('正在启动扫码…'); setQr(null)
    await startAuthFlow(agentId, active)
  }

  return (
    <div className="panel" style={{ display: 'grid', gap: 8 }}>
      <b>通道</b>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: 6 }}>
        {channels.map(ch => (
          <button key={ch.id} onClick={() => open(ch)}
                  style={{ textAlign: 'left', borderColor: active === ch.id ? 'var(--accent)' : undefined }}>
            <span className={'dot ' + (ch.enabled ? 'ok' : 'idle')} />
            {ch.label}
            <div className="muted" style={{ fontSize: 11 }}>{interactionLabel(ch.auth)}</div>
          </button>
        ))}
      </div>

      {flow && (
        <div className="panel" style={{ background: 'var(--panel-2)', display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <b>{flow.label}</b>
            <span className="muted" style={{ fontSize: 12 }}>{interactionLabel(flow.kind)}</span>
          </div>
          {flow.hint && <div className="muted" style={{ fontSize: 12 }}>{flow.hint}</div>}

          {/* 动态认证交互：按 kind 出不同界面 */}
          <AuthInteraction kind={flow.kind} flow={flow} inputs={inputs} setInputs={setInputs}
                           qr={qr} status={status} onScan={startScan} onSave={enableAndSave} />

          {flow.apply_url && (
            <a href={flow.apply_url} target="_blank" rel="noreferrer"
               style={{ color: 'var(--accent)', fontSize: 12 }}>去申请凭据 / 开发者后台 ↗</a>
          )}
          {msg && <div style={{ fontSize: 12, color: 'var(--ok)' }}>{msg}</div>}

          {tut && (
            <details>
              <summary style={{ cursor: 'pointer' }}>图文教程（{tut.steps.length} 步）</summary>
              <ol style={{ margin: '6px 0', paddingLeft: 18 }}>
                {tut.steps.map((s, i) => <li key={i} style={{ marginBottom: 4 }}>{s}</li>)}
              </ol>
              {tut.troubleshooting?.length > 0 && (
                <div className="muted" style={{ fontSize: 12 }}>
                  排错：{tut.troubleshooting.map((s, i) => <div key={i}>· {s}</div>)}
                </div>
              )}
              {tut.docs_url && <a href={tut.docs_url} target="_blank" rel="noreferrer"
                style={{ color: 'var(--accent)', fontSize: 12 }}>官方文档 ↗</a>}
            </details>
          )}
        </div>
      )}
    </div>
  )
}

function AuthInteraction({ kind, flow, inputs, setInputs, qr, status, onScan, onSave }: {
  kind: string; flow: AuthFlow; inputs: Record<string, string>
  setInputs: (v: Record<string, string>) => void; qr: number[][] | null
  status: string; onScan: () => void; onSave: () => void
}) {
  const it = interactionFor(kind as never)
  if (it === 'scan-qr') {
    return (
      <div style={{ display: 'grid', gap: 8, justifyItems: 'start' }}>
        {qr ? <QrCanvas matrix={qr} /> :
          <button onClick={onScan}>开始扫码</button>}
        {status && <div className="muted" style={{ fontSize: 12 }}>{status}</div>}
      </div>
    )
  }
  if (it === 'enable-only') {
    return <button onClick={onSave}>启用并保存</button>
  }
  if (it === 'show-webhook') {
    return (
      <div style={{ display: 'grid', gap: 6 }}>
        <code style={{ background: 'var(--panel)', padding: 6, borderRadius: 6 }}>
          {flow.webhook_url}
        </code>
        <button onClick={onSave}>启用并保存</button>
      </div>
    )
  }
  if (it === 'open-oauth') {
    return (
      <div style={{ display: 'grid', gap: 6 }}>
        {flow.apply_url && <a href={flow.apply_url} target="_blank" rel="noreferrer">
          <button>前往授权 ↗</button></a>}
        <button onClick={onSave}>启用并保存</button>
      </div>
    )
  }
  // fill-token / enter-code：字段表单
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {flow.fields.map(f => (
        <label key={f.key} style={{ display: 'grid', gap: 2 }}>
          <span style={{ fontSize: 12 }}>{f.label}</span>
          <input type={f.secret ? 'password' : 'text'} placeholder={f.placeholder}
                 value={inputs[f.key] || ''}
                 onChange={e => setInputs({ ...inputs, [f.key]: e.target.value })} />
        </label>
      ))}
      <button onClick={onSave}>保存配置</button>
    </div>
  )
}

function setDotted(obj: Record<string, unknown>, dotted: string, value: unknown) {
  const parts = dotted.split('.')
  let cur = obj
  for (let i = 0; i < parts.length - 1; i++) {
    if (typeof cur[parts[i]] !== 'object' || cur[parts[i]] === null) cur[parts[i]] = {}
    cur = cur[parts[i]] as Record<string, unknown>
  }
  cur[parts[parts.length - 1]] = value
}
