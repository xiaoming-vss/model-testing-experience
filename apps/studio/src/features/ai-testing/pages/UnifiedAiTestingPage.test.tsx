import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '@/app/providers/ThemeProvider'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
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
    if (url.pathname.includes('case-generate-tasks')) return jsonResponse({ items: [], total: 0 })
    return jsonResponse({ items: [], total: 0 })
  })
}

function renderPage() {
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
        <MemoryRouter initialEntries={['/ai-testing/tasks']}>
          <Routes>
            <Route path="/ai-testing/tasks" element={<UnifiedAiTestingPage />} />
            <Route path="/ai-testing/ui-tasks/:taskId" element={<UiDetailProbe />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

function UiDetailProbe() {
  const location = useLocation()
  const state = location.state as { pendingSourceArchive?: File; pendingSourceArchiveError?: string } | null
  return <div>UI 任务详情 {state?.pendingSourceArchive?.name} {state?.pendingSourceArchiveError}</div>
}

beforeEach(() => {
  useWorkbenchStore.setState({ activeProjectId: 'project-1' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useWorkbenchStore.setState({ activeProjectId: undefined })
})

describe('统一任务列表中的 UI 用例生成', () => {
  it('刷新按钮只刷新当前任务类型列表', async () => {
    let apiTaskRequests = 0
    let functionalTaskRequests = 0
    installFetchHandler((url) => {
      if (url.pathname === '/v1/projects/project-1/api-case-generate-tasks') {
        apiTaskRequests += 1
        return jsonResponse({ items: [], total: 0 })
      }
      if (url.pathname === '/v1/projects/project-1/function-case-generate-tasks') {
        functionalTaskRequests += 1
        return jsonResponse({ items: [], total: 0 })
      }
    })
    const user = userEvent.setup()

    renderPage()

    await waitFor(() => {
      expect(apiTaskRequests).toBe(1)
      expect(functionalTaskRequests).toBe(1)
    })
    await user.click(screen.getByText('API测试'))
    const refreshButton = screen.getByRole('button', { name: '刷新当前任务列表' })
    await waitFor(() => expect(refreshButton).not.toHaveClass('ant-btn-loading'))
    await user.click(refreshButton)

    await waitFor(() => expect(apiTaskRequests).toBe(2))
    await waitFor(() => expect(refreshButton).not.toHaveClass('ant-btn-loading'))
    expect(functionalTaskRequests).toBe(1)
  })

  it('任务列表展示任务更新时间而不是最近运行时间', async () => {
    const updatedAt = '2026-08-05T06:47:06.000Z'
    installFetchHandler((url) => {
      if (url.pathname === '/v1/projects/project-1/function-case-generate-tasks') {
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

    const user = userEvent.setup()

    renderPage()

    await user.click(await screen.findByText('功能测试'))

    expect(await screen.findByRole('columnheader', { name: '更新时间' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '最近运行' })).not.toBeInTheDocument()
    expect(await screen.findByText('2026/8/5 14:47:06')).toBeInTheDocument()
  })

  it('按任务类型 tab 过滤任务列表并显示数量', async () => {
    installFetchHandler((url) => {
      if (url.pathname === '/v1/projects/project-1/api-case-generate-tasks') {
        return jsonResponse({
          items: [
            {
              taskId: 'api-task-1',
              taskType: 'api_case_generate',
              name: 'API 登录接口',
              projectId: 'project-1',
              sprintId: 'sprint-1',
              requirementId: 'requirement-1',
              sourceType: 'openapi',
              sourceContent: '{}',
              instruction: '',
              createdAt: '2026-08-01T01:00:00.000Z',
              updatedAt: '2026-08-01T02:00:00.000Z',
            },
          ],
          total: 1,
        })
      }
      if (url.pathname === '/v1/projects/project-1/function-case-generate-tasks') {
        return jsonResponse({
          items: [
            {
              taskId: 'functional-task-1',
              taskType: 'functional_case_generate',
              name: 'EGO本地Server',
              projectId: 'project-1',
              sprintId: 'sprint-1',
              requirementId: 'requirement-1',
              instruction: '生成功能测试',
              createdAt: '2026-08-01T01:00:00.000Z',
              updatedAt: '2026-08-02T06:47:06.000Z',
            },
          ],
          total: 1,
        })
      }
    })
    const user = userEvent.setup()

    renderPage()

    // 默认选中第一个需求分析标签，再切换到 API测试。
    expect(await screen.findByRole('radio', { name: /需求分析/ })).toBeChecked()
    await user.click(screen.getByText('API测试'))
    expect(await screen.findByRole('radio', { name: /API测试1/ })).toBeChecked()
    expect(await screen.findByText('API 登录接口')).toBeInTheDocument()
    expect(screen.queryByText('EGO本地Server')).not.toBeInTheDocument()

    // 应用 Segmented 点击选中后,列表切换到对应类型
    await user.click(screen.getByText('功能测试'))

    expect(await screen.findByRole('radio', { name: /功能测试1/ })).toBeChecked()
    expect(await screen.findByText('EGO本地Server')).toBeInTheDocument()
    expect(screen.queryByText('API 登录接口')).not.toBeInTheDocument()
  })

  it('创建 UI 任务后上传所选 ZIP 并进入详情', async () => {
    const requests: Array<{ path: string; method: string; body?: unknown }> = []
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/projects/project-1/ui-case-generate-tasks' && init?.method === 'POST') {
        requests.push({ path: url.pathname, method: init.method, body: JSON.parse(String(init.body)) })
        return jsonResponse({
          taskId: 'ui-task-1',
          taskType: 'ui_case_generate',
          name: '登录模块 UI 用例生成',
          projectId: 'project-1',
          sprintId: 'sprint-1',
          requirementId: 'requirement-1',
          sourceType: 'source_archive',
          sourceArchive: null,
          instruction: '覆盖表单校验',
        })
      }
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/source-archive' && init?.method === 'PUT') {
        requests.push({ path: url.pathname, method: init.method, body: init.body })
        return jsonResponse({
          taskId: 'ui-task-1',
          sourceArchive: {
            archiveId: 'archive-1',
            filename: 'source.zip',
            sizeBytes: 4,
            sha256: 'abc123',
            uploadedAt: '2026-08-02T08:00:00.000Z',
          },
        })
      }
    })
    const user = userEvent.setup()

    renderPage()

    await user.click(await screen.findByRole('button', { name: /新建任务/ }))
    await user.click(screen.getByRole('button', { name: /UI测试/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认/ }))

    await user.type(await screen.findByLabelText('任务名称'), '登录模块 UI 用例生成')
    await user.click(screen.getByLabelText('所属需求'))
    await user.click(await screen.findByText('登录需求'))
    await user.upload(screen.getByLabelText('源码 ZIP'), new File(['zip'], 'source.zip', { type: 'application/zip' }))
    await user.type(screen.getByLabelText('生成指令'), '覆盖表单校验')
    await user.click(screen.getByRole('button', { name: '创建并上传' }))

    await waitFor(() => expect(requests).toHaveLength(2))
    expect(requests[0]).toEqual({
      path: '/v1/projects/project-1/ui-case-generate-tasks',
      method: 'POST',
      body: {
        name: '登录模块 UI 用例生成',
        sprintId: 'sprint-1',
        requirementId: 'requirement-1',
        instruction: '覆盖表单校验',
      },
    })
    expect(requests[1].body).toBeInstanceOf(FormData)
    expect((requests[1].body as FormData).get('file')).toBeInstanceOf(File)
    expect(await screen.findByText('UI 任务详情')).toBeInTheDocument()
  })

  it('requirementId 和 ZIP 缺失时不创建任务', async () => {
    const fetchSpy = installFetchHandler()
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /新建任务/ }))
    await user.click(screen.getByRole('button', { name: /UI测试/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认/ }))
    await user.type(await screen.findByLabelText('任务名称'), '缺少来源的任务')
    await user.click(screen.getByRole('button', { name: '创建并上传' }))

    expect(await screen.findByText('请选择所属需求')).toBeInTheDocument()
    expect(screen.getByText('请选择源码 ZIP')).toBeInTheDocument()
    expect(fetchSpy.mock.calls.some(([input, init]) => String(input).includes('/ui-case-generate-tasks') && init?.method === 'POST')).toBe(false)
  })

  it('任务创建成功但上传失败时保留任务并进入详情重试', async () => {
    let deleteRequested = false
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/projects/project-1/ui-case-generate-tasks' && init?.method === 'POST') {
        return jsonResponse({ ...taskForUploadFailure, taskId: 'ui-task-retry' })
      }
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-retry/source-archive' && init?.method === 'PUT') {
        return new Response(JSON.stringify({ code: 400, message: 'ZIP 已损坏', data: {} }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-retry' && init?.method === 'DELETE') deleteRequested = true
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /新建任务/ }))
    await user.click(screen.getByRole('button', { name: /UI测试/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认/ }))
    await user.type(await screen.findByLabelText('任务名称'), '待重试任务')
    await user.click(screen.getByLabelText('所属需求'))
    await user.click(await screen.findByText('登录需求'))
    await user.upload(screen.getByLabelText('源码 ZIP'), new File(['broken'], 'broken.zip', { type: 'application/zip' }))
    await user.click(screen.getByRole('button', { name: '创建并上传' }))

    expect(await screen.findByText(/UI 任务详情 broken.zip ZIP 已损坏/)).toBeInTheDocument()
    expect(deleteRequested).toBe(false)
  })
})

const taskForUploadFailure = {
  taskType: 'ui_case_generate',
  name: '待重试任务',
  projectId: 'project-1',
  sprintId: 'sprint-1',
  requirementId: 'requirement-1',
  sourceType: 'source_archive',
  sourceArchive: null,
  instruction: '',
}

it.each([
  ['功能测试', 'function-case-generate-tasks'],
  ['API测试', 'api-case-generate-tasks'],
  ['UI测试', 'ui-case-generate-tasks'],
  ['代码风险分析', 'code-risk-analysis-tasks'],
])('%s 列表运行使用当前项目加载模型授权', async (tab, resource) => {
  let connectionPath = ''
  let runBody: unknown
  installFetchHandler((url, init) => {
    if (url.pathname === `/v1/projects/project-1/${resource}`) {
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
    if (url.pathname === `/v1/${resource}/task-run-1/run`) {
      runBody = JSON.parse(String(init?.body))
      return jsonResponse({ taskId: 'task-run-1', runId: 'run-1', status: 'pending' })
    }
  })
  const user = userEvent.setup()
  renderPage()
  await user.click(await screen.findByText(tab))
  const runButton = await screen.findByRole('button', { name: '运行任务' })
  await waitFor(() => expect(runButton).toBeEnabled())
  await user.click(runButton)
  expect(screen.queryByText('请先选择项目')).not.toBeInTheDocument()
  await user.click(await screen.findByRole('radio', { name: '当前项目模型' }))
  expect(connectionPath).toContain('/projects/project-1/')
  expect(screen.getByRole('button', { name: '确认运行' })).toBeEnabled()
  if (resource !== 'code-risk-analysis-tasks') {
    await user.click(screen.getByRole('button', { name: '确认运行' }))
    await waitFor(() => expect(runBody).toMatchObject({ connectionId: 'mine' }))
  }
})

it.each(['', '   \n'])('功能测试列表有原文但无增强文本时禁止运行（%j）', async (documentContent) => {
  let runRequested = false
  installFetchHandler((url) => {
    if (url.pathname === '/v1/projects/project-1/function-case-generate-tasks') {
      return jsonResponse({ items: [{ taskId: 'task-run-1', name: '待生成任务', projectId: 'project-1', sprintId: 'sprint-1', requirementId: 'requirement-1' }], total: 1 })
    }
    if (url.pathname === '/v1/sprints/sprint-1/requirements' || url.pathname === '/v1/requirements/requirement-1') {
      const requirement = { requirementId: 'requirement-1', name: '需求', documentType: 'docx', documentFilename: '原文.docx', documentContent }
      return jsonResponse(url.pathname.endsWith('/requirements') ? { items: [requirement], total: 1 } : requirement)
    }
    if (url.pathname.endsWith('/run')) runRequested = true
  })
  const user = userEvent.setup()
  renderPage()
  await user.click(await screen.findByText('功能测试'))
  const button = await screen.findByRole('button', { name: '运行任务' })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  expect(await screen.findByText('请先完成需求分析并导入增强文本，再生成功能用例')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '确认运行' })).not.toBeInTheDocument()
  expect(runRequested).toBe(false)
})
