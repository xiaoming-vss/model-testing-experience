import { seedOwnerProject } from '@/test/projectAccess'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CodeRiskTaskDetailPage } from './CodeRiskTaskDetailPage'

const task = {
  taskId: 'risk-task-1',
  taskType: 'code_risk_analysis',
  name: '登录风险分析',
  projectId: 'project-1',
  sprintId: 'sprint-1',
  requirementId: 'requirement-1',
  instruction: '分析登录相关风险',
}

const run = {
  runId: 'risk-run-1',
  taskId: 'risk-task-1',
  projectId: 'project-1',
  requirementId: 'requirement-1',
  status: 'success',
  currentStage: 'completed',
  reviewStatus: 'pending',
  importStatus: 'pending',
  resultYaml: 'risks: []',
  createdAt: '2026-08-02T07:00:00.000Z',
}

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify({ code: status < 400 ? 0 : status, message: status < 400 ? 'ok' : '请求失败', data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installFetchHandler(getRun: () => typeof run, onRequest?: (url: URL, init?: RequestInit) => Response | undefined) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const requestUrl = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(requestUrl, 'http://localhost')
    const handled = onRequest?.(url, init)
    if (handled) return handled

    if (url.pathname === '/v1/code-risk-analysis-tasks/risk-task-1') return jsonResponse(task)
    if (url.pathname === '/v1/code-risk-analysis-tasks/risk-task-1/runs') return jsonResponse({ items: [getRun()], total: 1 })
    if (url.pathname === '/v1/code-risk-analysis-runs/risk-run-1') return jsonResponse(getRun())
    return jsonResponse({ items: [], total: 0 })
  })
}

function renderPage(role: 'owner' | 'viewer' = 'owner') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(queryClient)
  if (role === 'viewer') queryClient.setQueryData(['projectAccess', 'project-1'], { projectId: 'project-1', name: '只读项目', role, permissions: ['read'] })

  render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/ai-testing/code-risk-tasks/risk-task-1']}>
          <Routes>
            <Route path="/ai-testing/code-risk-tasks/:taskId" element={<CodeRiskTaskDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

/** Modal.confirm 是命令式弹窗，上一个用例的实例可能还在离场动画里，这里只取当前这一个。 */
async function findDeleteConfirm() {
  const dialogs = await screen.findAllByRole('dialog')
  const dialog = dialogs.find((node) => node.textContent?.includes('确认删除该运行记录？') && !node.className.includes('zoom-leave'))
  if (!dialog) throw new Error('未找到删除运行记录的确认框')
  return dialog
}

async function openRunActionsMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: '更多操作' }))
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('代码风险任务运行记录删除', () => {
  it('确认后才删除该次运行', async () => {
    const deleted: string[] = []
    installFetchHandler(() => run, (url, init) => {
      if (init?.method === 'DELETE') {
        deleted.push(url.pathname)
        return jsonResponse({})
      }
      return undefined
    })
    renderPage()
    const user = userEvent.setup()

    await openRunActionsMenu(user)
    await user.click(await screen.findByRole('menuitem', { name: '删除运行记录' }))
    const confirm = await findDeleteConfirm()
    expect(deleted).toEqual([])
    await user.click(within(confirm).getByRole('button', { name: /^删\s*除$/ }))
    await waitFor(() => expect(deleted).toEqual(['/v1/code-risk-analysis-runs/risk-run-1']))
  })

  it('运行中的记录没有可用的删除入口', async () => {
    installFetchHandler(() => ({ ...run, status: 'running' }))
    renderPage()
    const user = userEvent.setup()

    await openRunActionsMenu(user)
    expect(await screen.findByRole('menuitem', { name: '删除运行记录' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('只读成员没有删除入口', async () => {
    installFetchHandler(() => run)
    renderPage('viewer')
    await screen.findByText('登录风险分析')

    expect(screen.queryByRole('button', { name: '更多操作' })).toBeNull()
  })
})


it('服务端翻页保留全局运行状态，选中旧摘要后才获取报告详情', async () => {
  const historyPages: number[] = []
  const details: string[] = []
  const newest = { ...run, runId: 'newest', status: 'running' }
  const older = { ...run, runId: 'older', resultYaml: undefined }
  installFetchHandler(() => run, (url) => {
    if (url.pathname.endsWith('/runs')) {
      const page = Number(url.searchParams.get('page'))
      historyPages.push(page)
      expect(url.searchParams.get('pageSize')).toBe('20')
      return jsonResponse({ items: [page === 1 ? { ...newest, resultYaml: undefined } : older], total: 21,
        latestRun: { ...newest, resultYaml: undefined }, statusCounts: { running: 1, success: 20 } })
    }
    if (url.pathname.startsWith('/v1/code-risk-analysis-runs/')) {
      const id = url.pathname.split('/').at(-1)!
      details.push(id)
      return jsonResponse({ ...(id === 'newest' ? newest : older), resultYaml: '只在详情返回的报告内容' })
    }
  })
  renderPage()
  const user = userEvent.setup()
  await screen.findByText('#1')
  expect(screen.getByRole('button', { name: '发起运行' })).toBeDisabled()
  await user.click(screen.getByTitle('2'))
  const rowIndex = await screen.findByText('#21')
  expect(historyPages).toContain(2)
  expect(screen.getByRole('button', { name: '发起运行' })).toBeDisabled()
  expect(details).not.toContain('older')
  await user.click(rowIndex)
  await waitFor(() => expect(details).toContain('older'))
  await user.click(screen.getByRole('button', { name: /分析报告/ }))
  expect(await screen.findByText('只在详情返回的报告内容')).toBeInTheDocument()
})
