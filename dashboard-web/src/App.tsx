import { useState } from 'react'
import { useEventStream, usePoll } from './api'
import AgentWall, { type Agent } from './components/AgentWall'
import DispatchBox from './components/DispatchBox'
import SystemPanel, { type Sys } from './components/SystemPanel'
import TaskList, { type Task } from './components/TaskList'
import TopBar from './components/TopBar'

export default function App() {
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
