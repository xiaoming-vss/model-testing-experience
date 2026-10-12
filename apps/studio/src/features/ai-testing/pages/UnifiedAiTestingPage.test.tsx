import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/shared/api/files', () => ({
  storageCapabilities: vi.fn(async () => ({ enabled: true, maxBytes: 104857600 })),
  uploadStoredFile: vi.fn(async () => 'source-file-1'),
}))
import { ThemeProvider } from '@/app/providers/ThemeProvider'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { AppSidebar } from '@/app/layouts/AppSidebar'
import { UnifiedAiTestingPage } from './UnifiedAiTestingPage'

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify({ code: status < 400 ? 0 : status, message: status < 400 ? 'ok' : '请求失败', data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installFetchHandler(onRequest?: (url: URL, init?: RequestInit) => Response | undefined) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const requestUrl = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(requestUrl, 'http://localhost')
    const handled = onRequest?.(url, init)
    if (handled) return handled

    if (url.pathname === '/v1/projects') return jsonResponse([{ projectId: 'project-1', name: '示例项目' }])
    if (url.pathname === '/v1/projects/project-1/sprints') {
      return jsonResponse({ items: [{ sprintId: 'sprint-1', name: '迭代一' }], total: 1 })
    }
    if (url.pathname === '/v1/sprints/sprint-1/requirements') {
      return jsonResponse({ items: [{ requirementId: 'requirement-1', name: '登录需求' }], total: 1 })
    }
    if (/^\/v1\/ui-case-generate-tasks\/[^/]+$/.test(url.pathname)) return jsonResponse({ projectId: 'project-1' })
    if (url.pathname.includes('case-generate-tasks')) return jsonResponse({ items: [], total: 0 })
    return jsonResponse({ items: [], total: 0 })
  })
}

function renderPage(path = '/ai-testing/tasks') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  seedOwnerProject(queryClient)

  render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <AppSidebar />
          <Routes>
            <Route path="/projects" element={<div>需求列表入口</div>} />
            <Route path="/ai-testing" element={<UnifiedAiTestingPage />} />
            <Route path="/ai-testing/tasks" element={<UnifiedAiTestingPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

beforeEach(() => {
  useWorkbenchStore.setState({ activeProjectId: 'project-1' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useWorkbenchStore.setState({ activeProjectId: undefined })
})

describe('代码风险分析列表', () => {
  it('默认加载和刷新都只请求代码风险分析列表', async () => {
    const requests: string[] = []
    installFetchHandler((url) => {
      requests.push(url.pathname)
    })
    const user = userEvent.setup()
    renderPage()
    const endpoint = '/v1/projects/project-1/code-risk-analysis-tasks'
    await waitFor(() => expect(requests.filter(path => path === endpoint)).toHaveLength(1))
    const refreshButton = screen.getByRole('button', { name: '刷新当前任务列表' })
    await waitFor(() => expect(refreshButton).not.toHaveClass('ant-btn-loading'))
    await user.click(refreshButton)
    await waitFor(() => expect(requests.filter(path => path === endpoint)).toHaveLength(2))
    expect(requests.some(path => /case-generate-tasks|requirement-analysis-tasks/.test(path))).toBe(false)
  })

  it('任务列表展示任务更新时间而不是最近运行时间', async () => {
    const updatedAt = '2026-08-05T06:47:06.000Z'
    installFetchHandler((url) => {
      if (url.pathname === '/v1/projects/project-1/code-risk-analysis-tasks') {
        return jsonResponse({
          items: [{
            taskId: 'functional-task-1',
            taskType: 'functional_case_generate',
            name: 'EGO本地Server',
            projectId: 'project-1',
            sprintId: 'sprint-1',
            requirementId: 'requirement-1',
            instruction: '生成功能测试',
            createdAt: '2026-08-01T01:00:00.000Z',
            updatedAt,
          }],
          total: 1,
        })
      }
    })

    renderPage()

    expect(await screen.findByRole('columnheader', { name: '最近更新' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '最近运行' })).not.toBeInTheDocument()
    expect(await screen.findByText('2026/8/5 14:47:06')).toBeInTheDocument()
  })

  it.each(['', 'analysis', 'functional', 'api', 'ui', 'unknown', 'codeRisk'])('类型 %s 的链接只显示代码风险分析', async kind => {
    installFetchHandler(url => {
      if (url.pathname === '/v1/projects/project-1/code-risk-analysis-tasks') {
        return jsonResponse({ items: [{ taskId: 'risk-1', name: '代码分析任务', projectId: 'project-1', sprintId: 'sprint-1', requirementId: 'requirement-1' }], total: 1 })
      }
    })
    renderPage(`/ai-testing?kind=${kind}`)
    expect(await screen.findByText('代码分析任务')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '代码风险分析' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: '任务类型' })).not.toBeInTheDocument()
    // 代码风险分析已并入需求工作区 Tab，不再有侧边栏独立入口。
    expect(screen.queryByRole('link', { name: '代码风险分析' })).not.toBeInTheDocument()
  })

  it('状态筛选按最新运行状态过滤，并给出各档计数', async () => {
    installFetchHandler((url) => {
      if (url.pathname === '/v1/projects/project-1/code-risk-analysis-tasks') {
        return jsonResponse({
          items: [
            { taskId: 'api-success', name: '成功的任务', projectId: 'project-1', sprintId: 'sprint-1', requirementId: 'requirement-1', sourceType: 'openapi', sourceContent: '{}', instruction: '' },
            { taskId: 'api-review', name: '待审核的任务', projectId: 'project-1', sprintId: 'sprint-1', requirementId: 'requirement-1', sourceType: 'openapi', sourceContent: '{}', instruction: '' },
          ],
          total: 2,
        })
      }
      if (url.pathname === '/v1/code-risk-analysis-tasks/api-success/runs') {
        return jsonResponse({ items: [{ runId: 'run-1', taskId: 'api-success', status: 'success', createdAt: '2026-08-01T03:00:00.000Z' }], total: 1 })
      }
      if (url.pathname === '/v1/code-risk-analysis-tasks/api-review/runs') {
        return jsonResponse({ items: [{ runId: 'run-2', taskId: 'api-review', status: 'waiting_review', createdAt: '2026-08-01T03:00:00.000Z' }], total: 1 })
      }
    })
    const user = userEvent.setup()

    renderPage()

    // 计数来自「本类型全部任务的运行记录」，不是当前页
    expect(await screen.findByRole('button', { name: /全部 \(2\)/ })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /成功 \(1\)/ })).toBeInTheDocument()
    const reviewChip = await screen.findByRole('button', { name: /待审核 \(1\)/ })
    expect(screen.getByRole('button', { name: /进行中 \(0\)/ })).toBeInTheDocument()

    await user.click(reviewChip)

    expect(screen.getByText('待审核的任务')).toBeInTheDocument()
    expect(screen.queryByText('成功的任务')).not.toBeInTheDocument()
  })

  it('关键词搜索按任务名称与所属需求过滤', async () => {
    installFetchHandler((url) => {
      if (url.pathname === '/v1/projects/project-1/code-risk-analysis-tasks') {
        return jsonResponse({
          items: [
            { taskId: 'api-task-1', name: '登录接口用例', projectId: 'project-1', sprintId: 'sprint-1', requirementId: 'requirement-1', sourceType: 'openapi', sourceContent: '{}', instruction: '' },
            { taskId: 'api-task-2', name: '订单接口用例', projectId: 'project-1', sprintId: 'sprint-1', requirementId: 'requirement-1', sourceType: 'openapi', sourceContent: '{}', instruction: '' },
          ],
          total: 2,
        })
      }
    })
    const user = userEvent.setup()

    renderPage()

    await user.type(await screen.findByPlaceholderText('搜索任务名称 / 所属需求'), '订单')

    expect(await screen.findByText('订单接口用例')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('登录接口用例')).not.toBeInTheDocument())
  })

})

it('代码风险分析列表运行使用当前项目加载模型授权', async () => {
  let connectionPath = ''
  installFetchHandler((url) => {
    if (url.pathname === '/v1/projects/project-1/code-risk-analysis-tasks') {
      return jsonResponse({ items: [{ taskId: 'task-run-1', name: '可运行任务',
        projectId: 'project-1', sprintId: 'sprint-1', requirementId: 'requirement-1',
        sourceArchive: { fileName: 'source.zip' },
      }], total: 1 })
    }
    if (url.pathname === '/v1/sprints/sprint-1/requirements' || url.pathname === '/v1/requirements/requirement-1') {
      const requirement = { requirementId: 'requirement-1', name: '登录需求', documentType: 'text', documentFilename: '需求.md', documentContent: '已导入增强文本' }
      return jsonResponse(url.pathname.endsWith('/requirements') ? { items: [requirement], total: 1 } : requirement)
    }
    if (url.pathname.includes('/integrations/llm/connections')) {
      connectionPath = url.pathname
      return jsonResponse({ items: [{ connectionId: 'mine', name: '当前项目模型', status: 'active' }], total: 1 })
    }

  })
  const user = userEvent.setup()
  renderPage()
  const runButton = await screen.findByRole('button', { name: '运行任务' })
  await waitFor(() => expect(runButton).toBeEnabled())
  await user.click(runButton)
  expect(screen.queryByText('请先选择项目')).not.toBeInTheDocument()
  await user.click(await screen.findByRole('radio', { name: '当前项目模型' }))
  expect(connectionPath).toContain('/projects/project-1/')
  expect(screen.getByRole('button', { name: '确认运行' })).toBeEnabled()

})

it('代码风险分析仍保留创建入口', async () => {
  installFetchHandler()
  const user = userEvent.setup()
  renderPage()
  await user.click(screen.getByRole('button', { name: /新建任务/ }))
  expect(await screen.findByText('新建代码风险分析任务')).toBeInTheDocument()
})
