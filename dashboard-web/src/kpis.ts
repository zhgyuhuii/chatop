export type TaskLike = { state: string }
export type Kpis = {
  total: number; running: number; waiting: number
  succeeded: number; failed: number; successRate: number
}

export function computeKpis(tasks: TaskLike[]): Kpis {
  const by = (st: string) => tasks.filter(t => t.state === st).length
  const succeeded = by('succeeded'); const failed = by('failed')
  const done = succeeded + failed
  return {
    total: tasks.length, running: by('running'), waiting: by('pending_approval'),
    succeeded, failed, successRate: done ? succeeded / done : 0,
  }
}
