import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import type {
  UiGenerationRunInputs,
  UiGenerationSourceInputs,
  UiGenerationSourceOptions,
  UiGenerationSourceRepository,
} from '../api/generationChain.api'
import { UiGenerationSourcePanel } from './UiGenerationSourcePanel'

vi.mock('@/features/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))

const clients: QueryClient[] = []
afterEach(() => {
  cleanup()
  clients.splice(0).forEach(client => client.clear())
  vi.restoreAllMocks()
})
beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = new URL(String(input), 'http://localhost').pathname
    const rows = path.endsWith('/function-test-suites')
      ? [{ suiteId: 'suite', name: '功能' }]
      : [{ caseId: 'c1', title: '转换成功' }, { caseId: 'c2', title: '转换失败' }]
    return new Response(JSON.stringify({ code: 0, data: { items: rows, total: rows.length } }), {
      headers: { 'Content-Type': 'application/json' },
    })
  })
})

function repository(overrides: Partial<UiGenerationSourceRepository> = {}): UiGenerationSourceRepository {
  return {
    repositoryId: 'repo-web',
    pathWithNamespace: 'team/web',
    role: 'frontend',
    confidence: 0.92,
    responsibilitySummary: '管理端前端',
    keyPaths: ['src'],
    branch: 'main',
    commit: 'a1b2c3d4',
    isFrontend: true,
    available: true,
    profileError: '',
    ...overrides,
  }
}

function options(repositories = [repository()]): UiGenerationSourceOptions {
  return {
    defaultProfileVersionId: 'pv1',
    profileVersions: [{
      versionId: 'pv1',
      versionNo: 1,
      label: 'v1',
      createdAt: '2026-11-09T10:00:00Z',
      requirementMaterialVersion: { versionId: 'understand-1', versionNo: 1 },
      repositories,
    }],
  }
}

const existingSource: UiGenerationSourceInputs = {
  sourceKind: 'repository',
  repository: {
    repositoryId: 'repo-web',
    pathWithNamespace: 'team/web',
    branch: 'main',
    commit: 'frozen123',
    commitMode: 'profile',
    profileVersionId: 'pv1',
    profileVersionNo: 1,
    resolvedAt: '2026-11-09T10:00:00Z',
  },
  cases: [{ caseId: 'c1', title: '转换成功' }],
}

function mount({
  sourceOptions = options(),
  canWrite = true,
  busy = false,
  refreshInputs = false,
  configured = true,
  existing,
  onConfigure = vi.fn(async () => undefined),
  onStart = vi.fn(async () => undefined),
  onOpenProfile = vi.fn(),
}: {
  sourceOptions?: UiGenerationSourceOptions
  canWrite?: boolean
  busy?: boolean
  refreshInputs?: boolean
  configured?: boolean
  existing?: UiGenerationSourceInputs
  onConfigure?: () => Promise<unknown>
  onStart?: (inputs: UiGenerationRunInputs) => Promise<unknown>
  onOpenProfile?: () => void
} = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  render(
    <TestThemeProvider>
      <QueryClientProvider client={client}>
        <UiGenerationSourcePanel
          requirementId="req"
          sourceOptions={{ data: sourceOptions, loading: false }}
          canWrite={canWrite}
          busy={busy}
          refreshInputs={refreshInputs}
          configured={configured}
          existingSource={existing}
          onConfigure={onConfigure}
          onOpenProfile={onOpenProfile}
          onStart={onStart}
        />
      </QueryClientProvider>
    </TestThemeProvider>,
  )
  return { onConfigure, onStart, onOpenProfile }
}

async function advanceToReview(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: '配置并生成' }))
  const dialog = await screen.findByRole('dialog')
  await user.click(within(dialog).getByRole('button', { name: '下一步：选择用例' }))
  const review = within(dialog).getByRole('button', { name: '核对配置' })
  await waitFor(() => expect(review).toBeEnabled())
  await user.click(review)
  return within(dialog)
}

it('侧栏展示冻结来源摘要，向导默认选择当前正式用例并提交新的来源', async () => {
  const { onStart } = mount({ refreshInputs: true, existing: existingSource })
  const user = userEvent.setup()
  const summary = within(screen.getByRole('region', { name: 'UI 测试生成摘要' }))
  expect(summary.getByText('当前生成来源')).toBeInTheDocument()
  expect(summary.getByText('frozen123')).toBeInTheDocument()
  expect(summary.getByText('1 条')).toBeInTheDocument()
  expect(summary.queryByRole('table')).not.toBeInTheDocument()
  expect(globalThis.fetch).not.toHaveBeenCalled()
  const review = await advanceToReview(user)
  expect(review.getByText('2 条')).toBeInTheDocument()
  await user.click(review.getByRole('button', { name: '从元素控件清单重新生成' }))
  await waitFor(() => expect(onStart).toHaveBeenCalledWith({
    refreshInputs: true,
    functionCaseIds: ['c1', 'c2'],
    sourceProfileVersionId: 'pv1',
    sourceRepositoryId: 'repo-web',
    sourceCommitMode: 'profile',
  }))
})

it('没有前端仓库时解释原因并阻止进入用例步骤', async () => {
  const { onOpenProfile } = mount({
    sourceOptions: options([repository({
      repositoryId: 'repo-api', pathWithNamespace: 'team/api', role: 'backend', isFrontend: false,
    })]),
  })
  const user = userEvent.setup()
  expect(screen.getByText('画像未识别出前端仓库')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '配置并生成' }))
  const wizard = within(await screen.findByRole('dialog'))
  expect(wizard.getByText('team/api')).toBeInTheDocument()
  expect(wizard.getByRole('button', { name: '下一步：选择用例' })).toBeDisabled()
  await user.click(wizard.getByRole('button', { name: '去生成仓库画像' }))
  expect(onOpenProfile).toHaveBeenCalled()
})

it('只读成员可以查看生成摘要', () => {
  mount({ canWrite: false })
  expect(screen.getByText('team/web')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '配置并生成' })).not.toBeInTheDocument()
})

it('运行期间禁用配置并生成', () => {
  mount({ busy: true })
  expect(screen.getByRole('button', { name: '配置并生成' })).toBeDisabled()
})

it('未配置 UI 生成时先创建设置再启动首阶段', async () => {
  const order: string[] = []
  let startInputs: UiGenerationRunInputs | undefined
  mount({
    configured: false,
    onConfigure: async () => { order.push('configure') },
    onStart: async inputs => { order.push('start'); startInputs = inputs },
  })
  const user = userEvent.setup()
  const review = await advanceToReview(user)
  expect(order).toEqual([])
  await user.click(review.getByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(order).toEqual(['configure', 'start']))
  expect(startInputs).toEqual(expect.objectContaining({
    sourceProfileVersionId: 'pv1',
    sourceRepositoryId: 'repo-web',
  }))
})
