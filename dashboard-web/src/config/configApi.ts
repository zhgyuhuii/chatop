// 配置中心 API 客户端 + 纯逻辑（认证类型 → 交互种类）。
// 复用 dashboard 的 SSE 事件流（../api 的 useEventStream）。

const BASE = '/dashboard/api/agent-config'

export type AuthKind = 'qr' | 'token' | 'code' | 'webhook' | 'oauth' | 'builtin'

export interface FieldSpec {
  key: string; label: string; kind: string; secret?: boolean; advanced?: boolean; help?: string
  options?: string[]; apply_url?: string | null; placeholder?: string; value?: unknown
}
export interface ChannelSummary {
  id: string; label: string; auth: AuthKind; enabled: boolean; installed: boolean
  configured: boolean; supports_qr: boolean; apply_url: string | null; has_tutorial: boolean
}
export interface Group { id: string; label: string; fields: FieldSpec[]; channels: ChannelSummary[] }
export interface Descriptor { id: string; label: string; groups: Group[] }
export interface AgentStatus {
  id: string; label: string; installed: boolean; configured: boolean
  running: boolean; version: string | null; model: string | null; error?: string
}
export interface AuthFlow {
  kind: AuthKind; target: string; label: string; fields: FieldSpec[]
  apply_url: string | null; tutorial_id: string | null; webhook_url: string | null
  cmd: string[] | null; hint: string; free_kv?: boolean
}
export interface ModelInfo { key: string; label: string; source: 'live' | 'snapshot' }
export interface ModelsResult { ok: boolean; source: string; models: ModelInfo[]; reason: string }
export interface Tutorial {
  id: string; label: string; auth: string; steps: string[]
  credential_fields: string[]; apply_url: string | null; docs_url: string
  troubleshooting: string[]; source: string
}
export interface Diagnostic { id: string; level: 'ok' | 'warn' | 'error'; message: string; auto_fix: string | null }
export interface AssistantReply {
  mode: string; kind?: string; reply: string
  actions?: { type: string; agent?: string; channel?: string; provider?: string }[]
  auth_flow?: AuthFlow; tutorial?: Tutorial; tools_used?: { name: string }[]
}

// 认证类型 → 前端应渲染的「就地交互」种类。纯函数，便于单测。
export type Interaction = 'scan-qr' | 'fill-token' | 'enter-code' | 'show-webhook' | 'open-oauth' | 'enable-only'

export function interactionFor(kind: AuthKind): Interaction {
  switch (kind) {
    case 'qr': return 'scan-qr'
    case 'code': return 'enter-code'
    case 'webhook': return 'show-webhook'
    case 'oauth': return 'open-oauth'
    case 'builtin': return 'enable-only'
    default: return 'fill-token'
  }
}

export function interactionLabel(kind: AuthKind): string {
  return {
    'scan-qr': '扫码登录', 'fill-token': '填写凭据', 'enter-code': '输入验证码',
    'show-webhook': '配置 Webhook', 'open-oauth': '授权登录', 'enable-only': '启用即可',
  }[interactionFor(kind)]
}

const getJson = <T>(path: string): Promise<T> =>
  fetch(BASE + path).then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json() })
const postJson = <T>(path: string, body?: unknown): Promise<T> =>
  fetch(BASE + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json() })

export const getAgents = () => getJson<AgentStatus[]>('/agents')
export const describe = (id: string) => getJson<Descriptor>(`/${id}/describe`)
export const getConfig = (id: string) => getJson<Record<string, unknown>>(`/${id}/config`)
export const apply = (id: string, patch: unknown) =>
  postJson<{ ok: boolean; removed: string[]; message: string }>(`/${id}/apply`, { patch })
export const fetchModels = (id: string, provider: string, apiKey: string) =>
  postJson<ModelsResult>(`/${id}/models`, { provider, api_key: apiKey })
export const authFlow = (id: string, channel: string) =>
  getJson<AuthFlow>(`/${id}/auth-flow?channel=${encodeURIComponent(channel)}`)
export const startAuthFlow = (id: string, channel: string, inputs: Record<string, unknown> = {}) =>
  postJson<{ ok: boolean; streaming: boolean }>(`/${id}/auth-flow/start`, { channel, inputs })
export const getTutorial = (id: string, channel: string) =>
  getJson<Tutorial>(`/${id}/tutorial?channel=${encodeURIComponent(channel)}`)
export const health = (id: string) => postJson<Diagnostic[]>(`/${id}/health`)
export const askAssistant = (message: string, agent = 'openclaw', useLlm = true) =>
  postJson<AssistantReply>('/assistant', { message, agent, use_llm: useLlm })
