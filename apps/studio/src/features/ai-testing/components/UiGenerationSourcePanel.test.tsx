import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import type {
  UiGenerationSourceInputs,
  UiGenerationSourceOptions,
  UiGenerationSourceRepository,
} from '../api/generationChain.api'
import { UiGenerationSourcePanel } from './UiGenerationSourcePanel'

vi.mock('@/domain/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))

const clients: QueryClient[] = []
afterEach(() => {
  cleanup()
  clients.splice(0).forEach(client => client.clear())
  vi.restoreAllMocks()
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
    currentProfile: {
      candidateId: 'pv1',
      label: '当前画像',
      createdAt: '2026-11-09T10:00:00Z',
      repositories,
    },
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
    profileCandidateId: 'pv1',
    resolvedAt: '2026-11-09T10:00:00Z',
  },
  cases: [{ caseId: 'c1', title: '转换成功' }],
}

function mount({
  sourceOptions = options(), canWrite = true, busy = false, existing,
  onOpenProfile = vi.fn(), onOpenCandidate = vi.fn(),
}: {
  sourceOptions?: UiGenerationSourceOptions
  canWrite?: boolean
  busy?: boolean
  existing?: UiGenerationSourceInputs
  onOpenProfile?: () => void
  onOpenCandidate?: () => void
} = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  render(<TestThemeProvider><QueryClientProvider client={client}>
    <UiGenerationSourcePanel sourceOptions={{ data: sourceOptions, loading: false }}
      canWrite={canWrite} busy={busy} existingSource={existing}
      onOpenProfile={onOpenProfile} onOpenCandidate={onOpenCandidate} />
  </QueryClientProvider></TestThemeProvider>)
  return { onOpenProfile, onOpenCandidate }
}

it('展示冻结来源并打开候选工作区', async () => {
  const { onOpenCandidate } = mount({ existing: existingSource })
  expect(screen.getByText('frozen123')).toBeInTheDocument()
  expect(screen.getByText('1 条')).toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('button', { name: '打开候选工作区' }))
  expect(onOpenCandidate).toHaveBeenCalledOnce()
})

it('没有前端仓库时提示并可进入画像', async () => {
  const { onOpenProfile } = mount({ sourceOptions: options([repository({
    repositoryId: 'repo-api', role: 'backend', isFrontend: false,
  })]) })
  expect(screen.getByText('画像未识别出前端仓库')).toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('button', { name: '去生成仓库画像' }))
  expect(onOpenProfile).toHaveBeenCalledOnce()
})

it('只读成员可查看摘要但不能打开候选工作区', () => {
  mount({ canWrite: false })
  expect(screen.getByText('team/web')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '打开候选工作区' })).not.toBeInTheDocument()
})

it('运行期间禁用候选工作区入口', () => {
  mount({ busy: true })
  expect(screen.getByRole('button', { name: '打开候选工作区' })).toBeDisabled()
})
