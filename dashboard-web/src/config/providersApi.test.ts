import { describe, it, expect, vi } from 'vitest'
import { fetchProviders, fetchModels } from './configApi'

describe('providers api', () => {
  it('fetchProviders hits endpoint', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ providers: [{ id: 'deepseek', label: 'DS', auth_kind: 'key', has_live: true }] }), { status: 200 }))
    const r = await fetchProviders('openclaw')
    const url = spy.mock.calls[0][0] as string
    expect(url).toContain('/openclaw/providers')
    expect(r[0].id).toBe('deepseek')
  })

  it('fetchModels passes base_url', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true, source: 'live', models: [], reason: '' }), { status: 200 }))
    await fetchModels('openclaw', 'ollama', '', 'http://x:11434')
    const body = JSON.parse((spy.mock.calls[0][1] as RequestInit).body as string)
    expect(body.base_url).toBe('http://x:11434')
  })
})
