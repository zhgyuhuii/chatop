import { describe, expect, it } from 'vitest'
import { DICT, t } from '../i18n'

// i18n.ts 的真实 API：`lang` 是模块加载时从 cookie/navigator 算出的一次性常量（没有 setLang()，
// 语言切换=整页刷新，不是运行时可变的）；`t(key)` 里 key 本身就是英文原文，各语言词典把英文原文
// 映射到译文，`en` 没有词典、缺译一律回落 key 本身。
//
// vitest 默认 node 环境下没有 `document`（cookie 读不到），但 Node 22 全局 `navigator.language`
// 是 'en-US'，于是这里 `lang` 会解析成 'en' —— 这恰好让 `t(key)` 天然充当「en 渲染结果」（等于 key
// 本身），不需要 mock cookie / resetModules 就能验证「同一 key 在 zh 和 en 下文案不同」。
describe('config i18n', () => {
  // 目前 config 面板的一批 UI 外壳 key（按钮/标题/占位符/提示）。教程 steps 正文本轮不译，不在此列。
  const configKeys = [
    'Agent Config Center',
    'One-click health check',
    'Health check',
    'Model',
    'Fetch models',
    'Set as primary',
    'Channels',
    'Test connectivity',
    'Save configuration',
    'Save',
    'Config Assistant',
    'Send',
  ]

  it('has config keys in the zh_CN dict, and each differs from its English key', () => {
    for (const key of configKeys) {
      expect(DICT.zh_CN[key]).toBeTruthy()
      expect(DICT.zh_CN[key]).not.toBe(key)
    }
  })

  it('t() falls back to the English key in this env (no dict for "en") — and it differs from zh_CN', () => {
    for (const key of configKeys) {
      const en = t(key)
      const zh = DICT.zh_CN[key]
      expect(en).toBe(key) // en 没词典，t() 回落原文
      expect(zh).toBeTruthy()
      expect(zh).not.toBe(en) // 同一 key，中英文案不同
    }
  })

  it('zh_TW / ja / ko also cover every config key (no silent English leak in other langs)', () => {
    for (const code of ['zh_TW', 'ja', 'ko'] as const) {
      for (const key of configKeys) {
        expect(DICT[code][key]).toBeTruthy()
      }
    }
  })

  it('every t()/tr() key literally used in src/config/*.tsx exists in DICT.zh_CN', () => {
    // 同 src/i18n.test.ts 的「词条使用扫描」思路，范围收窄到 config 目录，防止拼错 key 静默显示英文。
    const sources = import.meta.glob('./*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<
      string,
      string
    >
    const used = new Set<string>()
    for (const src of Object.values(sources)) {
      for (const m of src.matchAll(/\bt(?:r)?\(\s*'((?:[^'\\]|\\.)+)'/g)) used.add(m[1])
    }
    expect(Object.keys(sources).length).toBeGreaterThan(3)
    expect(used.size).toBeGreaterThan(10)
    expect([...used].filter(k => !(k in DICT.zh_CN))).toEqual([])
  })
})
