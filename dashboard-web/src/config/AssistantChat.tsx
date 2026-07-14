import { useState } from 'react'
import { askAssistant, type AssistantReply } from './configApi'
import { t as tr } from '../i18n'

interface Turn { role: 'user' | 'bot'; text: string; reply?: AssistantReply }

// LLM 配置助手：自然语言 → 引擎规划步骤 / 工具调用。无模型时后端自动降级为确定性引导。
export default function AssistantChat({ agentId, onAction }: {
  agentId: string; onAction: (a: { type: string; channel?: string; provider?: string }) => void
}) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)

  const send = async () => {
    const q = text.trim()
    if (!q || busy) return
    setText(''); setBusy(true)
    setTurns(t => [...t, { role: 'user', text: q }])
    try {
      const r = await askAssistant(q, agentId)
      setTurns(t => [...t, { role: 'bot', text: r.reply || tr('(no reply)'), reply: r }])
      for (const a of r.actions || []) onAction(a)
    } catch {
      setTurns(t => [...t, { role: 'bot', text: tr('Assistant unavailable right now — just say "connect WeCom" or "configure deepseek model".') }])
    } finally { setBusy(false) }
  }

  return (
    <div className="panel" style={{ display: 'grid', gap: 8, gridTemplateRows: 'auto 1fr auto' }}>
      <b>{tr('Config Assistant')}</b>
      <div style={{ overflowY: 'auto', maxHeight: 280, display: 'grid', gap: 6, alignContent: 'start' }}>
        {turns.length === 0 && (
          <div className="muted" style={{ fontSize: 12 }}>
            {tr('Try: "help me connect WeCom" / "configure deepseek model" / "how do I scan the WeChat QR code"')}
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} style={{ justifySelf: t.role === 'user' ? 'end' : 'start', maxWidth: '90%' }}>
            <div style={{
              background: t.role === 'user' ? 'var(--accent)' : 'var(--panel-2)',
              color: t.role === 'user' ? '#04121a' : 'var(--text)',
              padding: '6px 10px', borderRadius: 8, whiteSpace: 'pre-wrap', fontSize: 13,
            }}>{t.text}</div>
            {t.reply?.tools_used?.length ? (
              <div className="muted" style={{ fontSize: 11 }}>
                {tr('Tools used: {names}', { names: t.reply.tools_used.map(x => x.name).join(', ') })}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <input value={text} placeholder={tr('Describe in one sentence what you want to configure…')} style={{ flex: 1 }}
               onChange={e => setText(e.target.value)}
               onKeyDown={e => { if (e.key === 'Enter') send() }} />
        <button disabled={busy} onClick={send}>{tr('Send')}</button>
      </div>
    </div>
  )
}
