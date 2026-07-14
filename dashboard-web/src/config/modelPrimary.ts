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
