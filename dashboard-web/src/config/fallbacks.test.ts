import { describe, it, expect } from 'vitest'
import { buildModelPatch } from './ModelPanel'
describe('buildModelPatch', () => {
  it('openclaw includes primary + fallbacks', () => {
    expect(buildModelPatch('openclaw', 'a/x', ['a/y', 'a/z']))
      .toEqual({ agents: { defaults: { model: { primary: 'a/x', fallbacks: ['a/y', 'a/z'] } } } })
  })
  it('openclaw omits fallbacks when empty', () => {
    expect(buildModelPatch('openclaw', 'a/x', [])).toEqual({ agents: { defaults: { model: { primary: 'a/x' } } } })
  })
  it('hermes uses bare model, no fallbacks', () => {
    expect(buildModelPatch('hermes', 'H-4', [])).toEqual({ model: 'H-4' })
  })
})
