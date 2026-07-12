import { useEffect, useRef, useState } from 'react'

// 配置中心专用事件流：与大屏共用 /dashboard/api/events SSE，但只保留配置流事件
// （station agentcfg 路由发的 kind==='agent-config' / type 以 'flow:' 开头），
// 不经 streamReducer（那只认 job 型事件）。保留最近 N 条供各面板消费。
export interface ConfigEvent { type?: string; channel?: string; matrix?: number[][]; reason?: string; [k: string]: unknown }

const KEEP = 50

export function useConfigEvents(): ConfigEvent[] {
  const [events, setEvents] = useState<ConfigEvent[]>([])
  const retry = useRef(1000)
  useEffect(() => {
    let es: EventSource | null = null
    let stop = false
    const connect = () => {
      if (stop) return
      es = new EventSource('/dashboard/api/events')
      es.onmessage = e => {
        try {
          const ev = JSON.parse(e.data) as ConfigEvent
          const isConfig = ev.kind === 'agent-config' ||
            (typeof ev.type === 'string' && ev.type.startsWith('flow'))
          if (isConfig) setEvents(prev => [...prev, ev].slice(-KEEP))
        } catch { /* skip */ }
      }
      es.onopen = () => { retry.current = 1000 }
      es.onerror = () => { es?.close(); setTimeout(connect, Math.min((retry.current *= 2), 30000)) }
    }
    connect()
    return () => { stop = true; es?.close() }
  }, [])
  return events
}
