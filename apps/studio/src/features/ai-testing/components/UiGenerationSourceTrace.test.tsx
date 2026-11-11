import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import type { UiGenerationSourceInputs } from '../api/generationChain.api'
import { UiGenerationSourceTrace } from './UiGenerationSourceTrace'

afterEach(cleanup)

function source(overrides: Partial<UiGenerationSourceInputs['repository']> = {}): UiGenerationSourceInputs {
  return {
    sourceKind: 'repository',
    repository: {
      repositoryId: 'repo-web',
      pathWithNamespace: 'team/web',
      branch: 'main',
      commit: 'a1b2c3d4',
      commitMode: 'latest',
      profileVersionId: 'profile-v3',
      profileVersionNo: 3,
      resolvedAt: '2026-11-09T10:00:00Z',
      ...overrides,
    },
    cases: [{ caseId: 'c1', title: '转换成功', suiteName: '转换套件', content: { steps: ['原始操作'] } }],
  }
}

it('来源追溯展示仓库、分支、commit、画像版本和功能用例', async () => {
  render(<TestThemeProvider><UiGenerationSourceTrace source={source()} /></TestThemeProvider>)
  const user = userEvent.setup()
  const trigger = screen.getByRole('button', { name: '查看仓库和功能用例快照' })
  expect(trigger).toHaveTextContent('仓库：team/web')
  expect(trigger).toHaveTextContent('功能用例：1 条')
  await user.click(trigger)
  const region = await screen.findByRole('region', { name: '生成输入快照' })
  expect(region).toHaveTextContent('team/web')
  expect(region).toHaveTextContent('main')
  expect(region).toHaveTextContent('a1b2c3d4')
  expect(region).toHaveTextContent('分支最新 HEAD')
  expect(region).toHaveTextContent('v3')
  expect(region).toHaveTextContent('整个仓库')
  expect(region).toHaveTextContent('功能用例 · 1 条')
  expect(screen.getByText(/原始操作/)).toBeInTheDocument()
  expect(region).not.toHaveTextContent('ZIP')
  expect(region).not.toHaveTextContent('SHA256')
  expect(region).not.toHaveTextContent('文件编号')
})

it('历史运行没有仓库快照时不冒充来源', () => {
  render(<TestThemeProvider><UiGenerationSourceTrace /></TestThemeProvider>)
  expect(screen.getByText(/历史来源未记录/)).toBeInTheDocument()
  expect(screen.queryByText('需求材料')).not.toBeInTheDocument()
})

it('旧快照缺少仓库字段时只展示历史提示', async () => {
  render(<TestThemeProvider><UiGenerationSourceTrace source={{ cases: [] } as unknown as UiGenerationSourceInputs} /></TestThemeProvider>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '查看仓库和功能用例快照' }))
  const region = await screen.findByRole('region', { name: '生成输入快照' })
  expect(region).toHaveTextContent('历史来源未记录仓库信息。')
  expect(region).not.toHaveTextContent('ZIP')
})
