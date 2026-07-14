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

    // --- config center（智能体配置中心）UI 外壳。教程 steps 正文本轮不译，仍中文。 ---
    'Agent Config Center': '智能体配置中心',
    'One-click health check': '一键体检',
    'Health check': '体检',
    'auto-fix: {fix}': '可自愈：{fix}',
    'Channel list not ready (needs an openclaw directory snapshot). Refresh after running directory collection inside the container.':
      '通道清单尚未就绪（需 openclaw 目录快照）。可在容器内运行目录采集后刷新。',
    Model: '模型',
    'Current primary model:': '当前主模型：',
    'Not set': '未设置',
    'Go authorize ↗': '前往授权 ↗',
    'Return here after authorizing, then fetch models': '授权后回来点获取模型',
    'Fetch models': '获取模型',
    Advanced: '高级',
    'Custom endpoint (base_url), leave blank for default': '自定义端点 (base_url)，留空用默认',
    'Request failed': '请求失败',
    'Primary model saved: {model}': '已保存主模型：{model}',
    'Save failed': '保存失败',
    'Primary model ({source}):': '主模型（{source}）：',
    Live: '实时',
    Snapshot: '快照',
    'Set as primary': '设为主模型',
    'Fallback models (multi-select):': '备选模型（可多选）：',
    Channels: '通道',
    'QR not captured yet, please scan in the terminal window': '未抓到二维码，请在终端窗口扫码',
    Connected: '已连接',
    'Unknown error': '未知错误',
    'Scan failed to start: {reason}': '扫码启动失败：{reason}',
    Saved: '已保存',
    'Saved (cleaned up: {removed})': '已保存（清理：{removed}）',
    'Starting scan…': '正在启动扫码…',
    'Testing…': '测试中…',
    'Test connectivity': '测连通',
    'Apply for credentials / developer console ↗': '去申请凭据 / 开发者后台 ↗',
    'Tutorial ({n} steps)': '图文教程（{n} 步）',
    'Troubleshooting:': '排错：',
    'Official docs ↗': '官方文档 ↗',
    'Start scanning': '开始扫码',
    'Enable and save': '启用并保存',
    'More settings ({n})': '更多设置（{n}）',
    'Save configuration': '保存配置',
    'Field name': '字段名',
    Value: '值',
    '+ Add field': '+ 添加字段',
    Save: '保存',
    'Config Assistant': '配置助手',
    'Try: "help me connect WeCom" / "configure deepseek model" / "how do I scan the WeChat QR code"':
      '试试：「帮我接入企业微信」「配 deepseek 模型」「微信怎么扫码」',
    '(no reply)': '（无回复）',
    'Assistant unavailable right now — just say "connect WeCom" or "configure deepseek model".':
      '助手暂不可用，请直接说「接入企业微信」「配 deepseek 模型」。',
    'Tools used: {names}': '调用：{names}',
    'Describe in one sentence what you want to configure…': '用一句话描述你想配置什么…',
    Send: '发送',
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

    'Agent Config Center': '智慧體配置中心',
    'One-click health check': '一鍵體檢',
    'Health check': '體檢',
    'auto-fix: {fix}': '可自癒：{fix}',
    'Channel list not ready (needs an openclaw directory snapshot). Refresh after running directory collection inside the container.':
      '通道清單尚未就緒（需 openclaw 目錄快照）。可在容器內執行目錄採集後重新整理。',
    Model: '模型',
    'Current primary model:': '當前主模型：',
    'Not set': '未設定',
    'Go authorize ↗': '前往授權 ↗',
    'Return here after authorizing, then fetch models': '授權後回來點取得模型',
    'Fetch models': '取得模型',
    Advanced: '進階',
    'Custom endpoint (base_url), leave blank for default': '自訂端點 (base_url)，留空使用預設',
    'Request failed': '請求失敗',
    'Primary model saved: {model}': '已儲存主模型：{model}',
    'Save failed': '儲存失敗',
    'Primary model ({source}):': '主模型（{source}）：',
    Live: '即時',
    Snapshot: '快照',
    'Set as primary': '設為主模型',
    'Fallback models (multi-select):': '備選模型（可多選）：',
    Channels: '通道',
    'QR not captured yet, please scan in the terminal window': '尚未擷取到二維碼，請在終端機視窗掃碼',
    Connected: '已連線',
    'Unknown error': '未知錯誤',
    'Scan failed to start: {reason}': '掃碼啟動失敗：{reason}',
    Saved: '已儲存',
    'Saved (cleaned up: {removed})': '已儲存（清理：{removed}）',
    'Starting scan…': '正在啟動掃碼…',
    'Testing…': '測試中…',
    'Test connectivity': '測試連線',
    'Apply for credentials / developer console ↗': '前往申請憑證 / 開發者後台 ↗',
    'Tutorial ({n} steps)': '圖文教學（{n} 步）',
    'Troubleshooting:': '疑難排解：',
    'Official docs ↗': '官方文件 ↗',
    'Start scanning': '開始掃碼',
    'Enable and save': '啟用並儲存',
    'More settings ({n})': '更多設定（{n}）',
    'Save configuration': '儲存設定',
    'Field name': '欄位名稱',
    Value: '值',
    '+ Add field': '+ 新增欄位',
    Save: '儲存',
    'Config Assistant': '設定助理',
    'Try: "help me connect WeCom" / "configure deepseek model" / "how do I scan the WeChat QR code"':
      '試試看：「幫我串接企業微信」「設定 deepseek 模型」「微信怎麼掃碼」',
    '(no reply)': '（無回覆）',
    'Assistant unavailable right now — just say "connect WeCom" or "configure deepseek model".':
      '助理目前無法使用，請直接說「串接企業微信」「設定 deepseek 模型」。',
    'Tools used: {names}': '呼叫：{names}',
    'Describe in one sentence what you want to configure…': '用一句話描述你想設定什麼…',
    Send: '傳送',
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

    'Agent Config Center': 'エージェント設定センター',
    'One-click health check': 'ワンクリック診断',
    'Health check': '診断',
    'auto-fix: {fix}': '自動修復：{fix}',
    'Channel list not ready (needs an openclaw directory snapshot). Refresh after running directory collection inside the container.':
      'チャンネル一覧はまだ準備できていません（openclaw ディレクトリのスナップショットが必要です）。コンテナ内でディレクトリ収集を実行後に再読み込みしてください。',
    Model: 'モデル',
    'Current primary model:': '現在のプライマリモデル：',
    'Not set': '未設定',
    'Go authorize ↗': '認証へ進む ↗',
    'Return here after authorizing, then fetch models': '認証後にここに戻ってモデルを取得してください',
    'Fetch models': 'モデルを取得',
    Advanced: '詳細設定',
    'Custom endpoint (base_url), leave blank for default': 'カスタムエンドポイント (base_url)、空欄でデフォルト使用',
    'Request failed': 'リクエスト失敗',
    'Primary model saved: {model}': 'プライマリモデルを保存しました：{model}',
    'Save failed': '保存に失敗',
    'Primary model ({source}):': 'プライマリモデル（{source}）：',
    Live: 'リアルタイム',
    Snapshot: 'スナップショット',
    'Set as primary': 'プライマリに設定',
    'Fallback models (multi-select):': 'フォールバックモデル（複数選択可）：',
    Channels: 'チャンネル',
    'QR not captured yet, please scan in the terminal window': 'QRコードを検出できません。ターミナルウィンドウでスキャンしてください',
    Connected: '接続済み',
    'Unknown error': '不明なエラー',
    'Scan failed to start: {reason}': 'スキャン開始に失敗：{reason}',
    Saved: '保存しました',
    'Saved (cleaned up: {removed})': '保存しました（クリーンアップ：{removed}）',
    'Starting scan…': 'スキャンを開始しています…',
    'Testing…': 'テスト中…',
    'Test connectivity': '接続テスト',
    'Apply for credentials / developer console ↗': '認証情報の申請 / 開発者コンソールへ ↗',
    'Tutorial ({n} steps)': 'チュートリアル（{n} ステップ）',
    'Troubleshooting:': 'トラブルシューティング：',
    'Official docs ↗': '公式ドキュメント ↗',
    'Start scanning': 'スキャン開始',
    'Enable and save': '有効化して保存',
    'More settings ({n})': 'その他の設定（{n}）',
    'Save configuration': '設定を保存',
    'Field name': 'フィールド名',
    Value: '値',
    '+ Add field': '＋ フィールドを追加',
    Save: '保存',
    'Config Assistant': '設定アシスタント',
    'Try: "help me connect WeCom" / "configure deepseek model" / "how do I scan the WeChat QR code"':
      '例：「WeCom を連携して」「deepseek モデルを設定して」「WeChat のQRコードの読み方は？」',
    '(no reply)': '（返信なし）',
    'Assistant unavailable right now — just say "connect WeCom" or "configure deepseek model".':
      'アシスタントは現在利用できません。「WeCom を連携」「deepseek モデルを設定」のように話しかけてください。',
    'Tools used: {names}': '使用ツール：{names}',
    'Describe in one sentence what you want to configure…': '設定したいことを一言で入力してください…',
    Send: '送信',
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

    'Agent Config Center': '에이전트 설정 센터',
    'One-click health check': '원클릭 점검',
    'Health check': '점검',
    'auto-fix: {fix}': '자동 복구: {fix}',
    'Channel list not ready (needs an openclaw directory snapshot). Refresh after running directory collection inside the container.':
      '채널 목록이 아직 준비되지 않았습니다(openclaw 디렉터리 스냅샷 필요). 컨테이너에서 디렉터리 수집을 실행한 뒤 새로고침하세요.',
    Model: '모델',
    'Current primary model:': '현재 기본 모델:',
    'Not set': '설정되지 않음',
    'Go authorize ↗': '인증하러 가기 ↗',
    'Return here after authorizing, then fetch models': '인증 후 여기로 돌아와 모델을 가져오세요',
    'Fetch models': '모델 가져오기',
    Advanced: '고급',
    'Custom endpoint (base_url), leave blank for default': '사용자 지정 엔드포인트 (base_url), 비워두면 기본값 사용',
    'Request failed': '요청 실패',
    'Primary model saved: {model}': '기본 모델 저장됨: {model}',
    'Save failed': '저장 실패',
    'Primary model ({source}):': '기본 모델({source}):',
    Live: '실시간',
    Snapshot: '스냅샷',
    'Set as primary': '기본 모델로 설정',
    'Fallback models (multi-select):': '대체 모델(다중 선택):',
    Channels: '채널',
    'QR not captured yet, please scan in the terminal window': 'QR 코드를 아직 인식하지 못했습니다. 터미널 창에서 스캔하세요',
    Connected: '연결됨',
    'Unknown error': '알 수 없는 오류',
    'Scan failed to start: {reason}': '스캔 시작 실패: {reason}',
    Saved: '저장됨',
    'Saved (cleaned up: {removed})': '저장됨(정리됨: {removed})',
    'Starting scan…': '스캔을 시작하는 중…',
    'Testing…': '테스트 중…',
    'Test connectivity': '연결 테스트',
    'Apply for credentials / developer console ↗': '자격 증명 신청 / 개발자 콘솔로 이동 ↗',
    'Tutorial ({n} steps)': '튜토리얼({n}단계)',
    'Troubleshooting:': '문제 해결:',
    'Official docs ↗': '공식 문서 ↗',
    'Start scanning': '스캔 시작',
    'Enable and save': '활성화하고 저장',
    'More settings ({n})': '추가 설정({n})',
    'Save configuration': '설정 저장',
    'Field name': '필드 이름',
    Value: '값',
    '+ Add field': '+ 필드 추가',
    Save: '저장',
    'Config Assistant': '설정 어시스턴트',
    'Try: "help me connect WeCom" / "configure deepseek model" / "how do I scan the WeChat QR code"':
      '예: "WeCom 연동해줘" "deepseek 모델 설정해줘" "WeChat QR 스캔 방법"',
    '(no reply)': '(응답 없음)',
    'Assistant unavailable right now — just say "connect WeCom" or "configure deepseek model".':
      '어시스턴트를 현재 사용할 수 없습니다. "WeCom 연동" 또는 "deepseek 모델 설정"이라고 말해보세요.',
    'Tools used: {names}': '사용한 도구: {names}',
    'Describe in one sentence what you want to configure…': '설정하려는 내용을 한 문장으로 입력하세요…',
    Send: '전송',
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
