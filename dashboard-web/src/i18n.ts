/**
 * 工位大屏的轻量 i18n。
 *
 * 语言的**唯一真源**是 cookie `chatop_lang`，由 app-manager 的 /lang 端点写入，
 * 与登录页、noVNC 共用。没有 cookie = 跟随系统（navigator.languages）。
 *
 * 语言在页面加载时定死即可 —— 切换语言走 /lang 会整页跳转刷新，
 * 所以不需要 React context / 订阅，模块级常量就够。
 *
 * 约定同 noVNC：**英文原文即 key**，缺译回落原文。`en` 没有词典。
 */

export const SUPPORTED = ['zh_CN', 'en', 'zh_TW', 'ja', 'ko'] as const
export type Lang = (typeof SUPPORTED)[number]

const DEFAULT: Lang = 'zh_CN'

function isSupported(v: string): v is Lang {
  return (SUPPORTED as readonly string[]).includes(v)
}

/** 与 chatop_i18n.normalize 保持一致：zh-HK/zh-Hant → zh_TW，别把繁体读者塞进简体。 */
export function normalize(raw: string): Lang | '' {
  const s = (raw || '').trim().replace(/_/g, '-').toLowerCase()
  if (!s) return ''
  const alias: Record<string, Lang> = {
    zh: 'zh_CN', 'zh-cn': 'zh_CN', 'zh-hans': 'zh_CN', 'zh-sg': 'zh_CN',
    'zh-tw': 'zh_TW', 'zh-hant': 'zh_TW', 'zh-hk': 'zh_TW', 'zh-mo': 'zh_TW',
    en: 'en', ja: 'ja', ko: 'ko',
  }
  const exact = SUPPORTED.find(c => c.replace('_', '-').toLowerCase() === s)
  if (exact) return exact
  // 从最长前缀往短了退：zh-hant-tw 先命中 zh-hant(→zh_TW)，再退到 zh(→zh_CN)。
  // 直接砍到第一段会把 zh-Hant-TW 判成简体。
  const parts = s.split('-')
  for (let n = parts.length; n > 0; n--) {
    const hit = alias[parts.slice(0, n).join('-')]
    if (hit) return hit
  }
  return ''
}

function cookieLang(): Lang | '' {
  if (typeof document === 'undefined') return ''
  const m = document.cookie.match(/(?:^|;\s*)chatop_lang=([^;]*)/)
  return m ? normalize(decodeURIComponent(m[1])) : ''
}

function browserLang(): Lang | '' {
  if (typeof navigator === 'undefined') return ''
  const list = navigator.languages?.length ? navigator.languages : [navigator.language]
  for (const raw of list) {
    const code = normalize(raw)
    if (code) return code
  }
  return ''
}

export const lang: Lang = cookieLang() || browserLang() || DEFAULT

/** BCP-47 形式，喂给 <html lang>。与 chatop_i18n.HTML_LANG 一致。 */
export const HTML_LANG: Record<Lang, string> = {
  zh_CN: 'zh-CN', en: 'en', zh_TW: 'zh-TW', ja: 'ja', ko: 'ko',
}

export const DICT: Record<Exclude<Lang, 'en'>, Record<string, string>> = {
  zh_CN: {
    'Workstation Dashboard': '工位大屏',
    'Event stream connected': '事件流已连',
    'Event stream disconnected': '事件流断开',
    'Standalone mode': '独立模式',
    'Agents {installed} installed / {running} running': '智能体 {installed} 装 / {running} 跑',
    'Tasks {total} · Running {running} · Pending {waiting} · Success {rate}%':
      '任务 {total} · 运行 {running} · 待批 {waiting} · 成功率 {rate}%',
    'Dispatched #{id}': '已派活 #{id}',
    'Dispatch failed: {err}': '派活失败: {err}',
    'What should it do…': '要做什么…',
    Dispatch: '派活',
    'Container status': '容器运行状态',
    'Up {hours}h': '运行 {hours}h',
    'VNC session': 'VNC 会话',
    'Listening ports: {ports}': '监听端口: {ports}',
    'No tasks yet — dispatch one from the left': '暂无任务——左侧派一个试试',
    detected: '侦测',
    Resident: '常驻',
    'Session-based': '会话式',
    'Human desktop': '人工桌面',
    'catalog unavailable — check app-manager': 'catalog 不可用——检查 app-manager',
    'Model: {model}': '模型: {model}',
    Configured: '已配置',
    'Not configured': '未配置',
    'Running CPU {cpu}% MEM {mem}M': '运行中 CPU {cpu}% MEM {mem}M',
    'Active sessions {n}': '活动会话 {n}',
    Open: '打开',
    Configure: '配置',
    Install: '安装',
    'Not installed': '未安装',
    '{label} {id} failed: {err}': '{label} {id} 失败: {err}',
    '(installation progress in Application Manager)': '（安装进度见应用管理）',
  },
  zh_TW: {
    'Workstation Dashboard': '工位大屏',
    'Event stream connected': '事件流已連',
    'Event stream disconnected': '事件流中斷',
    'Standalone mode': '獨立模式',
    'Agents {installed} installed / {running} running': '智慧體 {installed} 裝 / {running} 跑',
    'Tasks {total} · Running {running} · Pending {waiting} · Success {rate}%':
      '任務 {total} · 執行 {running} · 待批 {waiting} · 成功率 {rate}%',
    'Dispatched #{id}': '已派工 #{id}',
    'Dispatch failed: {err}': '派工失敗: {err}',
    'What should it do…': '要做什麼…',
    Dispatch: '派工',
    'Container status': '容器執行狀態',
    'Up {hours}h': '執行 {hours}h',
    'VNC session': 'VNC 工作階段',
    'Listening ports: {ports}': '監聽埠: {ports}',
    'No tasks yet — dispatch one from the left': '暫無任務——左側派一個試試',
    detected: '偵測',
    Resident: '常駐',
    'Session-based': '會話式',
    'Human desktop': '人工桌面',
    'catalog unavailable — check app-manager': 'catalog 不可用——檢查 app-manager',
    'Model: {model}': '模型: {model}',
    Configured: '已設定',
    'Not configured': '未設定',
    'Running CPU {cpu}% MEM {mem}M': '執行中 CPU {cpu}% MEM {mem}M',
    'Active sessions {n}': '作用中工作階段 {n}',
    Open: '開啟',
    Configure: '設定',
    Install: '安裝',
    'Not installed': '未安裝',
    '{label} {id} failed: {err}': '{label} {id} 失敗: {err}',
    '(installation progress in Application Manager)': '（安裝進度見應用管理）',
  },
  ja: {
    'Workstation Dashboard': 'ワークステーション ダッシュボード',
    'Event stream connected': 'イベントストリーム接続済み',
    'Event stream disconnected': 'イベントストリーム切断',
    'Standalone mode': 'スタンドアロンモード',
    'Agents {installed} installed / {running} running':
      'エージェント {installed} 導入 / {running} 実行中',
    'Tasks {total} · Running {running} · Pending {waiting} · Success {rate}%':
      'タスク {total} · 実行中 {running} · 承認待ち {waiting} · 成功率 {rate}%',
    'Dispatched #{id}': '依頼しました #{id}',
    'Dispatch failed: {err}': '依頼に失敗: {err}',
    'What should it do…': '何をしますか…',
    Dispatch: '依頼',
    'Container status': 'コンテナの状態',
    'Up {hours}h': '稼働 {hours}時間',
    'VNC session': 'VNC セッション',
    'Listening ports: {ports}': '待受ポート: {ports}',
    'No tasks yet — dispatch one from the left': 'タスクはまだありません — 左から依頼してください',
    detected: '検出',
    Resident: '常駐',
    'Session-based': 'セッション型',
    'Human desktop': '人手デスクトップ',
    'catalog unavailable — check app-manager':
      'catalog を取得できません — app-manager を確認してください',
    'Model: {model}': 'モデル: {model}',
    Configured: '設定済み',
    'Not configured': '未設定',
    'Running CPU {cpu}% MEM {mem}M': '実行中 CPU {cpu}% MEM {mem}M',
    'Active sessions {n}': 'アクティブセッション {n}',
    Open: '開く',
    Configure: '設定',
    Install: 'インストール',
    'Not installed': '未インストール',
    '{label} {id} failed: {err}': '{label} {id} に失敗: {err}',
    '(installation progress in Application Manager)':
      '（インストールの進捗はアプリ管理で確認できます）',
  },
  ko: {
    'Workstation Dashboard': '워크스테이션 대시보드',
    'Event stream connected': '이벤트 스트림 연결됨',
    'Event stream disconnected': '이벤트 스트림 끊김',
    'Standalone mode': '독립 모드',
    'Agents {installed} installed / {running} running':
      '에이전트 {installed} 설치 / {running} 실행 중',
    'Tasks {total} · Running {running} · Pending {waiting} · Success {rate}%':
      '작업 {total} · 실행 {running} · 대기 {waiting} · 성공률 {rate}%',
    'Dispatched #{id}': '작업 배정됨 #{id}',
    'Dispatch failed: {err}': '작업 배정 실패: {err}',
    'What should it do…': '무엇을 할까요…',
    Dispatch: '배정',
    'Container status': '컨테이너 상태',
    'Up {hours}h': '가동 {hours}시간',
    'VNC session': 'VNC 세션',
    'Listening ports: {ports}': '수신 포트: {ports}',
    'No tasks yet — dispatch one from the left': '작업이 없습니다 — 왼쪽에서 배정해 보세요',
    detected: '감지됨',
    Resident: '상주',
    'Session-based': '세션형',
    'Human desktop': '사람 데스크톱',
    'catalog unavailable — check app-manager': 'catalog를 사용할 수 없습니다 — app-manager 확인',
    'Model: {model}': '모델: {model}',
    Configured: '설정됨',
    'Not configured': '설정되지 않음',
    'Running CPU {cpu}% MEM {mem}M': '실행 중 CPU {cpu}% MEM {mem}M',
    'Active sessions {n}': '활성 세션 {n}',
    Open: '열기',
    Configure: '설정',
    Install: '설치',
    'Not installed': '설치되지 않음',
    '{label} {id} failed: {err}': '{label} {id} 실패: {err}',
    '(installation progress in Application Manager)': '(설치 진행 상황은 앱 관리에서 확인)',
  },
}

/** 英文原文即 key；`{name}` 占位符按 vars 替换。缺译回落原文，不会崩。 */
export function t(key: string, vars?: Record<string, string | number>): string {
  const dict = lang === 'en' ? undefined : DICT[lang]
  let out = dict?.[key] ?? key
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      out = out.split('{' + k + '}').join(String(v))
    }
  }
  return out
}
