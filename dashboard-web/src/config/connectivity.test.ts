import { describe, it, expect, vi } from 'vitest'
import { checkConnectivity } from './configApi'

describe('checkConnectivity', () => {
  it('posts to connectivity endpoint and returns single diag', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 'conn:telegram:ok', level: 'ok', message: '连接成功' }), { status: 200 }))
    const d = await checkConnectivity('openclaw', 'telegram')
    expect((spy.mock.calls[0][0] as string)).toContain('/openclaw/connectivity/telegram')
    expect(d.level).toBe('ok')
    expect(d.message).toBe('连接成功')
  })
})
