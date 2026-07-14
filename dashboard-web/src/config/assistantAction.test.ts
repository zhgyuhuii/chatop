import { describe, it, expect } from 'vitest'
import { actionToTarget } from './ConfigCenter'

describe('actionToTarget', () => {
  it('open_auth_flow → channel target', () =>
    expect(actionToTarget({ type: 'open_auth_flow', channel: 'wecom' })).toEqual({ channel: 'wecom' }))
  it('open_model_panel → provider target', () =>
    expect(actionToTarget({ type: 'open_model_panel', provider: 'deepseek' })).toEqual({ provider: 'deepseek' }))
  it('unknown action → empty', () =>
    expect(actionToTarget({ type: 'noop' })).toEqual({}))
})
