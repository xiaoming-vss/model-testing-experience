import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ApiCollectionDetailPage } from '@/features/api-automation/pages/ApiCollectionDetailPage'
import { UiTestSuiteCasePage } from '@/features/ui-automation/pages/UiTestSuiteCasePage'
import { api } from '@/services/api'

vi.mock('@/features/projects/hooks/useProjectAccess', () => ({
  useProjectAccess: () => ({ can: () => true, loading: false }),
}))
vi.mock('@/shared/utils/feedback', () => ({
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

const clients: QueryClient[] = []
const list = <T,>(items: T[]) => Object.assign([...items], { items, total: items.length })

afterEach(() => {
  cleanup()
  clients.forEach(client => client.clear())
  clients.length = 0
  vi.restoreAllMocks()
})

function setup(kind: 'api' | 'ui') {
  vi.spyOn(api, 'getRequirement').mockResolvedValue({ requirementId: 'requirement', sprintId: 'sprint', name: '需求' })
  vi.spyOn(api, 'getSprint').mockResolvedValue({ sprintId: 'sprint', projectId: 'project', name: '迭代', status: 'running' })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/${kind}/target`]}>
        <Routes>
          <Route path="/api/:collectionId" element={<ApiCollectionDetailPage />} />
          <Route path="/ui/:suiteId" element={<UiTestSuiteCasePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

it('API 编辑器打开草稿后保留输入，提交前不创建正式用例', async () => {
  vi.spyOn(api, 'getApiCollection').mockResolvedValue({ collectionId: 'target', requirementId: 'requirement', name: 'API 集合' })
  vi.spyOn(api, 'getApiCases').mockResolvedValue(list([]))
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(list([]))
  vi.spyOn(api, 'getApiCollectionRuns').mockResolvedValue(list([]))
  const create = vi.spyOn(api, 'createApiCase')
  setup('api')

  await screen.findByText('API 集合')
  fireEvent.click(screen.getAllByRole('button', { name: '新建用例' })[0])
  const name = await screen.findByLabelText('用例名称')
  fireEvent.change(name, { target: { value: '未保存的 API 用例' } })

  await waitFor(() => expect(name).toHaveValue('未保存的 API 用例'))
  expect(create).not.toHaveBeenCalled()
})

it('UI 编辑器可在草稿中添加步骤而不触发保存', async () => {
  vi.spyOn(api, 'getUiTestSuite').mockResolvedValue({ suiteId: 'target', requirementId: 'requirement', name: 'UI 套件' })
  vi.spyOn(api, 'getUiTestCases').mockResolvedValue(list([]))
  vi.spyOn(api, 'getUiTestSuiteRuns').mockResolvedValue(list([]))
  const create = vi.spyOn(api, 'createUiTestCase')
  setup('ui')

  await screen.findByText('UI 套件')
  fireEvent.click(screen.getByRole('button', { name: '新建 UI测试用例' }))
  fireEvent.click((await screen.findAllByRole('button', { name: '添加步骤' }))[0])

  await waitFor(() => expect(screen.queryByText('当前还没有步骤')).not.toBeInTheDocument())
  expect(create).not.toHaveBeenCalled()
})
