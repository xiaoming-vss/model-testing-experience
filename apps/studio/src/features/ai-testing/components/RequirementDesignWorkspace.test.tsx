import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { aiTestingApi } from '../api/aiTesting.api'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { generationChainApi } from '../api/generationChain.api'
import type { GenerationChain } from '../api/generationChain.api'
import type { ListResponse } from '@/shared/api/request'
import { RequirementDesignWorkspace } from './RequirementDesignWorkspace'

vi.mock('../hooks/usePersonalLlmChoice', () => ({
  usePersonalLlmChoice: () => ({ choose: async () => 'mine', chooseRun: async () => ({ connectionId: 'mine', checkpointEnabled: true }), dialog: null }),
}))
vi.mock('@/features/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))
vi.mock('../api/generationChain.api', () => ({
  generationChainApi: {
    overview: vi.fn(), chain: vi.fn(), version: vi.fn(), run: vi.fn(),
    revise: vi.fn(), review: vi.fn(), deleteVersion: vi.fn(), importOptions: vi.fn(), importVersion: vi.fn(),
  },
}))

function listPayload<T>(items: T[]): ListResponse<T> {
  return Object.assign([...items], { total: items.length, items })
}

function chainWith(kind: GenerationChain['kind'], label: string, configured: boolean): GenerationChain {
  return {
    kind, label, configured, taskId: configured ? `task-${kind}` : undefined, runId: configured ? `run-${kind}` : undefined,
    active: false, busy: false, sourceChanged: false, draftCount: configured ? 1 : 0,
    stages: configured ? [{
      stage: 'extracting_text', label: '提取与整理', order: 0, state: 'draft', latestVersion: null,
      draft: {
        attemptId: 'draft', runId: 'run', status: 'draft', summary: '1 个材料来源', artifactFormat: 'json',
        content: JSON.stringify({ schemaVersion: '1.0', artifactType: 'document_extraction', documentTitle: '材料', sources: [], contentBlocks: [], extractedFacts: [], questions: [] }),
        revision: 1, createdAt: '2026-10-30T09:00:00Z',
      },
      versions: [], upstreamStages: [],
    }] : [{ stage: 'generate', label: '首阶段', order: 0, state: 'not_started', latestVersion: null, draft: null, versions: [], upstreamStages: [] }],
    leaf: {},
  }
}

const clients: QueryClient[] = []
const stopFlowDragInJsdom = (event: MouseEvent) => {
  if ((event.target as Element).closest('.react-flow__node button')) event.stopPropagation()
}
// React Flow 量出节点尺寸后才显示节点；jsdom 没有布局引擎，需要补上尺寸。
beforeAll(() => {
  document.addEventListener('mousedown', stopFlowDragInJsdom, true)
  vi.stubGlobal('DOMMatrixReadOnly', class { m22 = 1 })
  vi.stubGlobal('ResizeObserver', class {
    callback: ResizeObserverCallback
    constructor(callback: ResizeObserverCallback) { this.callback = callback }
    observe(target: Element) { queueMicrotask(() => this.callback([{ target, contentRect: { width: 180, height: 100 } } as ResizeObserverEntry], this as unknown as ResizeObserver)) }
    unobserve() {}
    disconnect() {}
  })
})
afterAll(() => { document.removeEventListener('mousedown', stopFlowDragInJsdom, true); vi.unstubAllGlobals() })
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.clearAllMocks(); vi.restoreAllMocks() })
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(180)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(100)
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ code: 0, message: 'ok', data: { items: [], total: 0 } }), { headers: { 'Content-Type': 'application/json' } }))
  vi.spyOn(aiTestingApi, 'getCodeRiskTasks').mockResolvedValue(listPayload([]))
  vi.spyOn(baseServicesApi, 'getGitlabRequirementBindings').mockResolvedValue(listPayload([]))
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [chainWith('requirement_analysis', '需求分析', true), chainWith('function', '功能测试', false), chainWith('api', 'API 测试', false), chainWith('ui', 'UI 测试', false)],
  })
})

function mount(onOpenDocument = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter>
    <RequirementDesignWorkspace requirementId="req" projectId="project" canWrite onOpenDocument={onOpenDocument} />
  </MemoryRouter></QueryClientProvider></TestThemeProvider>)
  return { onOpenDocument }
}

it('需求详情正文只渲染生成全景，不再包含页签、页头、汇总和运行记录', async () => {
  mount()
  expect(await screen.findByRole('button', { name: '提取与整理 · 待审核' })).toBeInTheDocument()
  expect(screen.queryByRole('group', { name: '筛选生成链' })).not.toBeInTheDocument()
  expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: '需求的生成链' })).not.toBeInTheDocument()
  expect(document.querySelector('.gc-summary')).toBeNull()
  expect(document.querySelector('.ai-requirement-design-history')).toBeNull()
})

it('文档与代码风险从泳道入口打开，未配置链打开生成设置', async () => {
  const { onOpenDocument } = mount()
  const user = userEvent.setup()
  await screen.findByRole('button', { name: '提取与整理 · 待审核' })

  // 泳道卡片单击选中、双击打开：需求文档直接打开阅读弹窗，不经过侧栏；代码风险也直接打开。
  await user.dblClick(screen.getByRole('button', { name: /查看需求文档/ }))
  expect(onOpenDocument).toHaveBeenCalledTimes(1)

  await user.dblClick(screen.getByRole('button', { name: /代码风险分析/ }))
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
  await user.keyboard('{Escape}')
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

  await user.click(screen.getByRole('button', { name: /开始\s*API 测试/ }))
  expect(await screen.findByText('生成设置')).toBeInTheDocument()
})
