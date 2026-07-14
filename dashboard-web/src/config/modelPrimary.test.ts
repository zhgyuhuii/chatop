import { describe, it, expect } from 'vitest'
import { readPrimaryModel, readFallbacks } from './modelPrimary'
describe('readPrimaryModel', () => {
  const desc = (gid: string, key: string, val: string) => ({
    groups: [{ id: gid, label: '', fields: [{ key, value: val }], channels: [] }] }) as never
  it('openclaw reads model.primary', () =>
    expect(readPrimaryModel('openclaw', desc('model', 'agents.defaults.model.primary', 'zai/glm-5'))).toBe('zai/glm-5'))
  it('hermes reads bare model', () =>
    expect(readPrimaryModel('hermes', desc('basic', 'model', 'Hermes-4'))).toBe('Hermes-4'))
})
describe('readFallbacks', () => {
  const descFb = (val: unknown) => ({
    groups: [{ id: 'model', label: '', fields: [
      { key: 'agents.defaults.model.fallbacks', value: val }], channels: [] }] }) as never
  it('reads fallbacks array', () =>
    expect(readFallbacks('openclaw', descFb(['a/x', 'a/y']))).toEqual(['a/x', 'a/y']))
  it('hermes has no fallbacks', () =>
    expect(readFallbacks('hermes', descFb(['a/x']))).toEqual([]))
  it('non-array value → []', () =>
    expect(readFallbacks('openclaw', descFb(undefined))).toEqual([]))
})
