import { describe, expect, it } from 'vitest'
import { interactionFor, interactionLabel, type AuthKind } from './configApi'

describe('interactionFor', () => {
  it('maps each auth kind to the right interaction', () => {
    expect(interactionFor('qr')).toBe('scan-qr')
    expect(interactionFor('token')).toBe('fill-token')
    expect(interactionFor('code')).toBe('enter-code')
    expect(interactionFor('webhook')).toBe('show-webhook')
    expect(interactionFor('oauth')).toBe('open-oauth')
    expect(interactionFor('builtin')).toBe('enable-only')
  })

  it('defaults unknown kinds to fill-token', () => {
    expect(interactionFor('weird' as AuthKind)).toBe('fill-token')
  })
})

describe('interactionLabel', () => {
  it('gives Chinese labels', () => {
    expect(interactionLabel('qr')).toBe('扫码登录')
    expect(interactionLabel('builtin')).toBe('启用即可')
  })
})
