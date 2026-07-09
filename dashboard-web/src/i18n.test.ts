import { describe, expect, it } from 'vitest'
import { DICT, normalize, t } from './i18n'

describe('normalize', () => {
  it('把繁体变体收进 zh_TW，别让港台读者拿到简体', () => {
    for (const raw of ['zh-HK', 'zh-Hant', 'zh-Hant-TW', 'zh-Hant-HK', 'zh-Hant-MO']) {
      expect(normalize(raw)).toBe('zh_TW')
    }
  })
  it('简体变体收进 zh_CN', () => {
    expect(normalize('zh')).toBe('zh_CN')
    expect(normalize('zh-Hans')).toBe('zh_CN')
    expect(normalize('zh-SG')).toBe('zh_CN')
  })
  it('不支持的语言返回空串', () => {
    expect(normalize('fr-FR')).toBe('')
    expect(normalize('')).toBe('')
  })
})

describe('t', () => {
  it('缺译回落英文原文', () => {
    expect(t('Some brand new string')).toBe('Some brand new string')
  })
  it('占位符替换', () => {
    expect(t('Up {hours}h', { hours: 3 })).toContain('3')
  })
})

describe('词典完整性', () => {
  const base = Object.keys(DICT.zh_CN)

  it('每种语言覆盖同一批 key —— 漏一条就是某语言下突然冒出英文', () => {
    for (const code of ['zh_TW', 'ja', 'ko'] as const) {
      expect(Object.keys(DICT[code]).sort()).toEqual([...base].sort())
    }
  })

  it('中文词典里没有「译文 == 英文原文」的漏翻', () => {
    expect(Object.entries(DICT.zh_CN).filter(([k, v]) => k === v)).toEqual([])
  })

  it('组件里 t() 用到的 key 都在词典里 —— 拼错会静默显示英文', () => {
    // 用 import.meta.glob 而不是 node:fs：Dockerfile 的 dashweb 阶段跑 tsc --noEmit，
    // 装的是浏览器那套 types，引 node:fs / __dirname 会让镜像构建挂掉。
    const sources = import.meta.glob('./{main.tsx,components/*.tsx}', {
      query: '?raw', import: 'default', eager: true,
    }) as Record<string, string>

    const used = new Set<string>()
    for (const src of Object.values(sources)) {
      for (const m of src.matchAll(/\bt(?:r)?\(\s*'((?:[^'\\]|\\.)+)'/g)) used.add(m[1])
    }
    expect(Object.keys(sources).length).toBeGreaterThan(3)
    expect(used.size).toBeGreaterThan(10)
    expect([...used].filter(k => !(k in DICT.zh_CN))).toEqual([])
  })
})
