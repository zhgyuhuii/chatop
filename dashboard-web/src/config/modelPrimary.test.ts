import { describe, it, expect } from 'vitest'
import { readPrimaryModel } from './modelPrimary'
describe('readPrimaryModel', () => {
  const desc = (gid: string, key: string, val: string) => ({
    groups: [{ id: gid, label: '', fields: [{ key, value: val }], channels: [] }] }) as never
  it('openclaw reads model.primary', () =>
    expect(readPrimaryModel('openclaw', desc('model', 'agents.defaults.model.primary', 'zai/glm-5'))).toBe('zai/glm-5'))
  it('hermes reads bare model', () =>
    expect(readPrimaryModel('hermes', desc('basic', 'model', 'Hermes-4'))).toBe('Hermes-4'))
})
