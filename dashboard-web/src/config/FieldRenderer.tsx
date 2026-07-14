import type { FieldSpec } from './configApi'
export default function FieldRenderer({ field, value, onChange }: {
  field: FieldSpec; value: unknown; onChange: (v: unknown) => void
}) {
  if (field.kind === 'bool') return (
    <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
      <input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)} />
      <span>{field.label}</span>
    </label>)
  if (field.kind === 'select') return (
    <label style={{ display: 'grid', gap: 2, fontSize: 12 }}>
      <span>{field.label}</span>
      <select value={(value as string) || ''} onChange={e => onChange(e.target.value)}>
        <option value="">—</option>
        {(field.options || []).map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>)
  return (
    <label style={{ display: 'grid', gap: 2, fontSize: 12 }}>
      <span>{field.label}</span>
      <input type={field.secret ? 'password' : 'text'} placeholder={field.placeholder || ''}
             value={(value as string) || ''} onChange={e => onChange(e.target.value)} />
      {field.help && <span className="muted" style={{ fontSize: 11 }}>{field.help}</span>}
    </label>)
}
