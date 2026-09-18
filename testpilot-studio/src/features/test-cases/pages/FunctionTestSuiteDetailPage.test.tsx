import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { FunctionTestSuiteDetailPage } from './FunctionTestSuiteDetailPage'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it.each([false, true])('批量删除只提交勾选项，失败保留选择（失败=%s）', async (fail) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  seedOwnerProject(client)
  client.setQueryData(['functionTestSuite', 'suite-1'], { suiteId: 'suite-1', name: '测试集', requirementId: 'req-1' })
  client.setQueryData(['requirement', 'req-1'], { requirementId: 'req-1', name: '需求', sprintId: 'sprint-1' })
  client.setQueryData(['sprint', 'sprint-1'], { sprintId: 'sprint-1', name: '迭代', projectId: 'project-1' })
  let items = [{ caseId: 'case-1', suiteId: 'suite-1', title: '用例甲' }, { caseId: 'case-2', suiteId: 'suite-1', title: '用例乙' }]
  client.setQueryData(['functionTestCases', 'suite-1'], { items, total: 2 })
  for (const item of items) client.setQueryData(['functionTestCase', item.caseId], item)
  vi.spyOn(api, 'getFunctionTestCases').mockImplementation(async () => Object.assign([...items], { items, total: items.length }))
  const remove = vi.spyOn(api, 'batchDeleteFunctionTestCases').mockImplementation(async () => {
    if (fail) throw new Error('删除失败')
    items = items.filter(item => item.caseId !== 'case-1')
    return { deletedIds: ['case-1'], deletedCount: 1 }
  })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/suites/suite-1']}>
    <Routes><Route path="/suites/:suiteId" element={<FunctionTestSuiteDetailPage />} /></Routes>
  </MemoryRouter></QueryClientProvider>)
  const user = userEvent.setup()
  expect(await screen.findByRole('button', { name: '批量删除' })).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: '选择用例：用例甲' }))
  await user.click(screen.getByRole('button', { name: '批量删除（1）' }))
  expect(remove).not.toHaveBeenCalled()
  await user.click(await screen.findByRole('button', { name: '确认删除' }))
  await waitFor(() => expect(remove).toHaveBeenCalledExactlyOnceWith('suite-1', ['case-1']))
  if (fail) {
    expect(screen.getByRole('checkbox', { name: '选择用例：用例甲' })).toBeChecked()
  } else {
    await waitFor(() => expect(screen.queryByRole('checkbox', { name: '选择用例：用例甲' })).not.toBeInTheDocument())
    expect(screen.getByRole('checkbox', { name: '选择用例：用例乙' })).not.toBeChecked()
    expect(screen.getByRole('button', { name: '批量删除' })).toBeDisabled()
  }
  client.clear()
})
