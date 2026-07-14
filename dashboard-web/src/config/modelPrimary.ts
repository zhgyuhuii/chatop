import type { Descriptor } from './configApi'
export function readPrimaryModel(agentId: string, desc: Descriptor | null): string {
  if (!desc) return ''
  const wanted = agentId === 'hermes' ? 'model' : 'agents.defaults.model.primary'
  for (const g of desc.groups) {
    const f = g.fields.find(f => f.key === wanted)
    if (f) return (f.value as string) || ''
  }
  return ''
}
export function readFallbacks(agentId: string, desc: Descriptor | null): string[] {
  if (!desc || agentId === 'hermes') return []
  for (const g of desc.groups) {
    const f = g.fields.find(f => f.key === 'agents.defaults.model.fallbacks')
    if (f && Array.isArray(f.value)) return f.value as string[]
  }
  return []
}
