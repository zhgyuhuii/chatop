import { useEffect, useState } from 'react'
import { useEventStream, usePoll } from './api'
import AgentWall, { type Agent } from './components/AgentWall'
import DispatchBox from './components/DispatchBox'
import SystemPanel, { type Sys } from './components/SystemPanel'
import TaskList, { type Task } from './components/TaskList'
import TopBar from './components/TopBar'
import ConfigCenter from './config/ConfigCenter'
import { UpdaterPanel } from './updater/UpdaterPanel'

// 极简 hash 路由：#/config → 配置中心，否则大屏。桌面「智能体配置」图标打开 #/config。
function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const on = () => setHash(window.location.hash)
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return hash
}

export default function App() {
  const route = useHashRoute()
  if (route.startsWith('#/config')) return <ConfigCenter />
  if (route.startsWith('#/updater')) return <UpdaterPanel />
  return <Dashboard />
}

function Dashboard() {
  const agents = usePoll<Agent[]>('/agents', 10000, [])
  const tasks = usePoll<Task[]>('/tasks', 5000, [])
  const sys = usePoll<Sys>('/system', 5000, {})
  const { stream, connected } = useEventStream()
  const [picked, setPicked] = useState('')
  return (
    <div style={{ display: 'grid', gap: 10, padding: 10,
                  gridTemplateRows: 'auto 1fr auto auto', minHeight: '100vh' }}>
      <TopBar tasks={tasks} agents={agents} sys={sys} connected={connected} />
      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 10 }}>
        <AgentWall agents={agents} onPick={setPicked} />
        <TaskList tasks={tasks} live={stream} />
      </div>
      <DispatchBox agents={agents} picked={picked} />
      <SystemPanel sys={sys} />
    </div>
  )
}
