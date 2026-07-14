import { describe, it, expect } from 'vitest'
import { setDotted, buildGroupPatch } from './fieldPatch'

describe('fieldPatch', () => {
  it('setDotted expands dotted keys', () => {
    const o: Record<string, unknown> = {}
    setDotted(o, 'channels.telegram.botToken', 'x')
    expect(o).toEqual({ channels: { telegram: { botToken: 'x' } } })
  })
  it('buildGroupPatch skips empty, keeps bool', () => {
    const fields = [{ key: 'api_key', kind: 'secret' }, { key: 'auto_approve', kind: 'bool' }] as never[]
    expect(buildGroupPatch(fields, { api_key: 'sk-1', auto_approve: true }))
      .toEqual({ api_key: 'sk-1', auto_approve: true })
    expect(buildGroupPatch(fields, { api_key: '' })).toEqual({})
  })
})
