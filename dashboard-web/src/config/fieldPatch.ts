export interface FieldLike { key: string; kind?: string }
export function setDotted(obj: Record<string, unknown>, dotted: string, value: unknown) {
  const parts = dotted.split('.'); let cur = obj
  for (let i = 0; i < parts.length - 1; i++) {
    if (typeof cur[parts[i]] !== 'object' || cur[parts[i]] === null) cur[parts[i]] = {}
    cur = cur[parts[i]] as Record<string, unknown>
  }
  cur[parts[parts.length - 1]] = value
}
export function buildGroupPatch(fields: FieldLike[], values: Record<string, unknown>) {
  const patch: Record<string, unknown> = {}
  for (const f of fields) {
    const v = values[f.key]
    if (f.kind === 'bool') { if (v !== undefined) setDotted(patch, f.key, !!v) }
    else if (f.kind === 'number') {
      if (v !== undefined && v !== '') {
        const n = Number(v)
        if (!Number.isNaN(n)) setDotted(patch, f.key, n)
      }
    }
    else if (v !== undefined && v !== '') setDotted(patch, f.key, v)
  }
  return patch
}
