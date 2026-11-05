import { PaneActivityProvider } from '@/shared/ui/PaneActivityProvider'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { Project } from '../types'
import { projectsApi } from '../api/projects.api'
import { useProjectAccess } from './useProjectAccess'

function Probe({ projectId }: { projectId: string }) {
  useProjectAccess(projectId)
  return null
}

function renderProbe(client: QueryClient, active: boolean) {
  return render(
    <QueryClientProvider client={client}>
      <PaneActivityProvider active={active}>
        <Probe projectId="project-1" />
      </PaneActivityProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

it('隐藏面板不轮询项目权限，切回可见后恢复', async () => {
  vi.useFakeTimers()
  const getProject = vi.spyOn(projectsApi, 'getProject').mockResolvedValue({
    projectId: 'project-1',
    name: '项目',
    permissions: ['read'],
  } as unknown as Project)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = renderProbe(client, false)

  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  expect(getProject).toHaveBeenCalledTimes(1)

  // 隐藏期间越过一个 30s 周期，不再发请求。
  await act(async () => { await vi.advanceTimersByTimeAsync(65_000) })
  expect(getProject).toHaveBeenCalledTimes(1)

  view.rerender(
    <QueryClientProvider client={client}>
      <PaneActivityProvider active>
        <Probe projectId="project-1" />
      </PaneActivityProvider>
    </QueryClientProvider>,
  )
  await act(async () => { await vi.advanceTimersByTimeAsync(31_000) })
  expect(getProject).toHaveBeenCalledTimes(2)

  client.clear()
})
