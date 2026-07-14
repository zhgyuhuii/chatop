import { describe, it, expect } from 'vitest'
import { freeKvToPatch, splitFields } from './ChannelPanel'
describe('channel field helpers', () => {
  it('freeKvToPatch builds channels.<id> with enabled', () => {
    expect(freeKvToPatch('wecom', [{ k: 'corpId', v: 'c1' }, { k: '', v: 'x' }]))
      .toEqual({ channels: { wecom: { enabled: true, corpId: 'c1' } } })
  })
  it('splitFields separates primary vs advanced', () => {
    const fs = [{ key: 'a', advanced: false }, { key: 'b', advanced: true }] as never[]
    const { primary, advanced } = splitFields(fs)
    expect(primary.map((f: any) => f.key)).toEqual(['a'])
    expect(advanced.map((f: any) => f.key)).toEqual(['b'])
  })
})
