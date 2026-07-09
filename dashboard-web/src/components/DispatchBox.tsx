import { useState } from 'react'
import { dispatchTask } from '../api'
import type { Agent } from './AgentWall'
import { t } from '../i18n'

export default function DispatchBox({ agents, picked }: { agents: Agent[]; picked: string }) {
  const targets = agents.filter(a => a.installed && a.dispatchable)
  const [agent, setAgent] = useState('')
  const [goal, setGoal] = useState('')
  const [note, setNote] = useState('')
  const chosen = agent || picked || targets[0]?.id || ''
  const send = () => {
    if (!chosen || !goal.trim()) return
    dispatchTask(chosen, goal.trim())
      .then(r => { setNote(t('Dispatched #{id}', { id: r.job_id })); setGoal('') })
      .catch(e => setNote(t('Dispatch failed: {err}', { err: e.message })))
  }
  return (
    <div className="panel" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <select value={chosen} onChange={e => setAgent(e.target.value)}>
        {targets.map(a => <option key={a.id} value={a.id}>@{a.name}</option>)}
      </select>
      <input style={{ flex: 1 }} placeholder={t('What should it do…')} value={goal}
             onChange={e => setGoal(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
      <button onClick={send} disabled={!chosen}>{t('Dispatch')}</button>
      {note && <span className="muted">{note}</span>}
    </div>
  )
}
