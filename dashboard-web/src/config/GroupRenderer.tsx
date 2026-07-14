import { useState } from 'react'
import FieldRenderer from './FieldRenderer'
import { buildGroupPatch } from './fieldPatch'
import { apply, type Group } from './configApi'
import { t } from '../i18n'
export default function GroupRenderer({ agentId, group, onSaved }: {
  agentId: string; group: Group; onSaved: () => void }) {
  const fields = group.fields.filter(f => f.kind !== 'model')
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [msg, setMsg] = useState('')
  if (!fields.length) return null
  const save = async () => {
    const r = await apply(agentId, buildGroupPatch(fields, values))
    setMsg(r.ok ? t('Saved') : t('Save failed')); onSaved()
  }
  return (
    <div className="panel" style={{ display: 'grid', gap: 8 }}>
      <b>{group.label}</b>
      {fields.map(f => (
        <FieldRenderer key={f.key} field={f} value={values[f.key] ?? f.value}
                       onChange={v => setValues({ ...values, [f.key]: v })} />
      ))}
      <button onClick={save} style={{ justifySelf: 'start' }}>{t('Save')}</button>
      {msg && <span style={{ fontSize: 12, color: 'var(--ok)' }}>{msg}</span>}
    </div>)
}
