import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import {
  generationChainApi,
  type UiGenerationRunInputs,
  type UiGenerationSourceOptions,
  type UiGenerationSourceRepository,
} from '../api/generationChain.api'
import { UiGenerationInputsModal } from './UiGenerationInputsModal'

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

function sourceOptions(): UiGenerationSourceOptions {
  return {
    defaultProfileVersionId: 'pv2',
    profileVersions: [
      {
        versionId: 'pv2',
        versionNo: 2,
        label: 'v2',
        createdAt: '2026-11-09T10:00:00Z',
        requirementUnderstandingVersion: { versionId: 'understand-2', versionNo: 2 },
        repositories: [repository()],
      },
      {
        versionId: 'pv1',
        versionNo: 1,
        label: 'v1',
        createdAt: '2026-11-08T10:00:00Z',
        requirementUnderstandingVersion: { versionId: 'understand-1', versionNo: 1 },
        repositories: [repository({
          repositoryId: 'repo-old',
          pathWithNamespace: 'team/old-web',
          role: 'fullstack',
          branch: 'release',
          commit: '9999999',
        })],
      },
    ],
  }
}

function mount({
  options = sourceOptions(),
  refreshInputs = false,
  source,
  onSubmit = vi.fn(async () => undefined),
  onOpenProfile = vi.fn(),
}: {
  options?: UiGenerationSourceOptions
  refreshInputs?: boolean
  source?: React.ComponentProps<typeof UiGenerationInputsModal>['source']
  onSubmit?: (inputs: UiGenerationRunInputs) => Promise<unknown>
  onOpenProfile?: () => void
} = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  const onClose = vi.fn()
  render(
    <TestThemeProvider>
      <QueryClientProvider client={client}>
        <UiGenerationInputsModal
          requirementId="req"
          refreshInputs={refreshInputs}
          source={source}
          sourceOptions={{ data: options, loading: false }}
          onOpenProfile={onOpenProfile}
          onSubmit={onSubmit}
          onClose={onClose}
        />
      </QueryClientProvider>
    </TestThemeProvider>,
  )
  return { onClose, onSubmit, onOpenProfile }
}

it('默认使用最新画像版本和唯一前端仓库，提交仓库来源与所选用例', async () => {
  const { onSubmit, onClose } = mount()
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole('button', { name: '下一步：选择用例' })).toBeEnabled())
  expect(screen.getByRole('button', { name: /v2/ })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('radio', { name: '选择仓库 team/web' })).toBeChecked()
  expect(screen.getByText('a1b2c3d4')).toBeInTheDocument()
  expect(screen.getByText(/启动时使用所选画像版本冻结的 commit/)).toBeInTheDocument()
  expect(screen.queryByText('源码 ZIP')).not.toBeInTheDocument()
  expect(document.querySelector('input[type="file"]')).toBeNull()
  await user.click(screen.getByRole('button', { name: '下一步：选择用例' }))
  await screen.findByRole('checkbox', { name: '选择用例：转换成功' })
  await user.click(screen.getByRole('checkbox', { name: '选择用例：转换失败' }))
  await user.click(screen.getByRole('button', { name: '预览变更' }))
  await user.click(await screen.findByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
    refreshInputs: false,
    functionCaseIds: ['c1'],
    sourceProfileVersionId: 'pv2',
    sourceRepositoryId: 'repo-web',
    sourceCommitMode: 'profile',
  }))
  expect(onClose).toHaveBeenCalled()
})

it('可以切换历史画像版本并同步仓库候选', async () => {
  const { onSubmit } = mount()
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole('button', { name: '下一步：选择用例' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: 'v1' }))
  expect(await screen.findByText('team/old-web')).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: '选择仓库 team/old-web' })).toBeChecked()
  await user.click(screen.getByRole('button', { name: '下一步：选择用例' }))
  await screen.findByRole('checkbox', { name: '选择用例：转换成功' })
  await user.click(screen.getByRole('button', { name: '预览变更' }))
  await user.click(await screen.findByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    sourceProfileVersionId: 'pv1',
    sourceRepositoryId: 'repo-old',
  })))
})

it('多个前端仓库时必须先选择一个才能开始生成', async () => {
  const options = sourceOptions()
  options.profileVersions[0].repositories = [
    repository(),
    repository({
      repositoryId: 'repo-admin',
      pathWithNamespace: 'team/admin',
      confidence: 0.7,
      responsibilitySummary: '后台管理',
    }),
  ]
  const { onSubmit } = mount({ options })
  const user = userEvent.setup()
  expect(screen.getByText('检测到 2 个前端仓库')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '下一步：选择用例' })).toBeDisabled()
  expect(screen.getByRole('radio', { name: '选择仓库 team/web' })).not.toBeChecked()
  await user.click(screen.getByRole('radio', { name: '选择仓库 team/admin' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '下一步：选择用例' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: '下一步：选择用例' }))
  await screen.findByRole('checkbox', { name: '选择用例：转换成功' })
  await user.click(screen.getByRole('button', { name: '预览变更' }))
  await user.click(await screen.findByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    sourceRepositoryId: 'repo-admin',
  })))
})

it('没有画像版本时阻止生成并引导去生成仓库画像', async () => {
  const { onOpenProfile } = mount({
    options: { profileVersions: [], defaultProfileVersionId: '' },
  })
  const user = userEvent.setup()
  expect(await screen.findByText('尚未生成仓库画像')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '下一步：选择用例' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: '去生成仓库画像' }))
  expect(onOpenProfile).toHaveBeenCalled()
})

it('可以切换最新 HEAD 并检查分支更新', async () => {
  vi.spyOn(generationChainApi, 'uiSourceCheck').mockResolvedValue({
    pinnedCommit: 'a1b2c3d4',
    currentCommit: 'fffffff',
    branch: 'main',
    changed: true,
  })
  const { onSubmit } = mount()
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole('button', { name: '下一步：选择用例' })).toBeEnabled())
  await user.click(screen.getByRole('radio', { name: '使用分支最新 HEAD' }))
  expect(screen.getByText(/启动时解析该分支最新 HEAD/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '检查更新' }))
  expect(await screen.findByText('分支已有新提交')).toBeInTheDocument()
  expect(generationChainApi.uiSourceCheck).toHaveBeenCalledWith('req', {
    profileVersionId: 'pv2',
    repositoryId: 'repo-web',
    pinnedCommit: 'a1b2c3d4',
  })
  await user.click(screen.getByRole('button', { name: '下一步：选择用例' }))
  await screen.findByRole('checkbox', { name: '选择用例：转换成功' })
  await user.click(screen.getByRole('button', { name: '预览变更' }))
  await user.click(await screen.findByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    sourceCommitMode: 'latest',
  })))
})

it('检查更新失败时显示接口错误并保留当前选择', async () => {
  vi.spyOn(generationChainApi, 'uiSourceCheck').mockRejectedValue(
    new Error('未找到所选仓库的 GitLab 个人授权，请先配置'),
  )
  const { onSubmit } = mount()
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole('button', { name: '下一步：选择用例' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: '检查更新' }))
  expect(await screen.findByText('未找到所选仓库的 GitLab 个人授权，请先配置')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '下一步：选择用例' })).toBeEnabled()
  expect(onSubmit).not.toHaveBeenCalled()
})

it('更换输入保留原功能用例选择并提交 refreshInputs', async () => {
  const { onSubmit } = mount({
    refreshInputs: true,
    source: {
      sourceKind: 'repository',
      repository: {
        repositoryId: 'repo-web',
        pathWithNamespace: 'team/web',
        branch: 'main',
        commit: 'a1b2c3d4',
        commitMode: 'profile',
        profileVersionId: 'pv2',
        profileVersionNo: 2,
        resolvedAt: '2026-11-09T10:00:00Z',
      },
      cases: [{ caseId: 'c2', title: '历史标题' }],
    },
  })
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole('button', { name: '下一步：选择用例' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: '下一步：选择用例' }))
  expect(await screen.findByRole('checkbox', { name: '选择用例：转换成功' })).not.toBeChecked()
  await user.click(screen.getByRole('button', { name: '预览变更' }))
  await user.click(await screen.findByRole('button', { name: '从元素控件清单重新生成' }))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    refreshInputs: true,
    functionCaseIds: ['c2'],
  })))
})
