import { useEffect, useRef, useState } from 'react'
import { applyEvent, initialStream, type StreamState } from './streamReducer'

const BASE = '/dashboard/api'

export function usePoll<T>(path: string, intervalMs: number, fallback: T): T {
  const [data, setData] = useState<T>(fallback)
  useEffect(() => {
    let alive = true
    const tick = () =>
      fetch(BASE + path).then(r => r.json()).then(d => { if (alive) setData(d) }).catch(() => {})
    tick()
    const t = setInterval(tick, intervalMs)
    return () => { alive = false; clearInterval(t) }
  }, [path, intervalMs])
  return data
}

export function useEventStream(): { stream: StreamState; connected: boolean } {
  const [stream, setStream] = useState<StreamState>(initialStream())
  const [connected, setConnected] = useState(false)
  const retryRef = useRef(1000)
  useEffect(() => {
    let es: EventSource | null = null
    let stop = false
    const connect = () => {
      if (stop) return
      es = new EventSource(BASE + '/events')
      es.onopen = () => { setConnected(true); retryRef.current = 1000 }
      es.onmessage = e => { try { setStream(s => applyEvent(s, JSON.parse(e.data))) } catch { /* skip */ } }
      es.onerror = () => {
        setConnected(false); es?.close()
        setTimeout(connect, Math.min((retryRef.current *= 2), 30000))
      }
    }
    connect()
    return () => { stop = true; es?.close() }
  }, [])
  return { stream, connected }
}

const post = (path: string, body?: unknown) =>
  fetch(BASE + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json() })

export const dispatchTask = (agent: string, goal: string, workdir?: string) =>
  post('/dispatch', { agent, goal, workdir: workdir || null })

export const openAgent = (id: string) => post(`/agents/${id}/open`)
export const configureAgent = (id: string) => post(`/agents/${id}/configure`)
export const installAgent = (id: string) => post(`/agents/${id}/install`)
