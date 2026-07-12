import { useState } from 'react'
import { askAssistant, type AssistantReply } from './configApi'

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
      setTurns(t => [...t, { role: 'bot', text: r.reply || '（无回复）', reply: r }])
      for (const a of r.actions || []) onAction(a)
    } catch {
      setTurns(t => [...t, { role: 'bot', text: '助手暂不可用，请直接说「接入企业微信」「配 deepseek 模型」。' }])
    } finally { setBusy(false) }
  }

  return (
    <div className="panel" style={{ display: 'grid', gap: 8, gridTemplateRows: 'auto 1fr auto' }}>
      <b>配置助手</b>
      <div style={{ overflowY: 'auto', maxHeight: 280, display: 'grid', gap: 6, alignContent: 'start' }}>
        {turns.length === 0 && (
          <div className="muted" style={{ fontSize: 12 }}>
            试试：「帮我接入企业微信」「配 deepseek 模型」「微信怎么扫码」
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
                调用：{t.reply.tools_used.map(x => x.name).join(', ')}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <input value={text} placeholder="用一句话描述你想配置什么…" style={{ flex: 1 }}
               onChange={e => setText(e.target.value)}
               onKeyDown={e => { if (e.key === 'Enter') send() }} />
        <button disabled={busy} onClick={send}>发送</button>
      </div>
    </div>
  )
}
