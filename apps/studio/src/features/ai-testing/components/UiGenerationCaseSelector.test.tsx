import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { UiGenerationCaseSelector } from './UiGenerationCaseSelector'

const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks() })
function mount(size = 2) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = new URL(String(input), 'http://localhost').pathname
    const rows = path.endsWith('/function-test-suites') ? [{ suiteId: 'a', name: '检索用例集' }, { suiteId: 'b', name: '转换用例集' }]
      : path.includes('/a/cases') ? Array.from({ length: size }, (_, i) => ({ caseId: `a-${i + 1}`, title: `检索记录${i + 1}` }))
      : [{ caseId: 'b-1', title: '转换成功' }]
    return new Response(JSON.stringify({ code: 0, data: { items: rows, total: rows.length } }), { headers: { 'Content-Type': 'application/json' } })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  function Host() {
    const [ids, setIds] = useState<string[]>()
    const [ready, setReady] = useState(false)
    return <><UiGenerationCaseSelector requirementId="req" open value={ids} onChange={setIds} onReady={setReady} />
      <output aria-label="已选编号">{ids?.join(',')}</output><button disabled={!ready}>提交生成</button></>
  }
  render(<TestThemeProvider><QueryClientProvider client={client}><Host /></QueryClientProvider></TestThemeProvider>)
}
async function filterSuite(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole('combobox', { name: '按用例集筛选' }))
  await user.click(screen.getByText(name, { selector: '.ant-select-item-option-content' }))
  await user.keyboard('{Escape}')
}
it('提供复选框多选，按用例集和标题筛选且保留隐藏用例的选择', async () => {
  mount()
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole('button', { name: '提交生成' })).toBeEnabled())
  expect(screen.getByRole('checkbox', { name: '选择用例：转换成功' })).toBeChecked()
  await filterSuite(user, '检索用例集')
  expect(screen.queryByRole('checkbox', { name: '选择用例：转换成功' })).not.toBeInTheDocument()
  expect(screen.getByText('已选 3 / 3 条')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '取消筛选结果' }))
  expect(screen.getByLabelText('已选编号')).toHaveTextContent('b-1')
  await user.type(screen.getByRole('searchbox', { name: '搜索用例' }), '记录2')
  expect(screen.queryByRole('checkbox', { name: '选择用例：检索记录1' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '全选筛选结果' }))
  expect(screen.getByLabelText('已选编号')).toHaveTextContent('b-1,a-2')
  await user.clear(screen.getByRole('searchbox', { name: '搜索用例' }))
  await filterSuite(user, '检索用例集')
  expect(screen.getByRole('checkbox', { name: '选择用例：转换成功' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: '选择用例：检索记录1' })).not.toBeChecked()
  expect(screen.getByRole('checkbox', { name: '选择用例：检索记录2' })).toBeChecked()
  await user.click(screen.getByRole('button', { name: '清空选择' }))
  expect(screen.getByRole('button', { name: '提交生成' })).toBeDisabled()
})
it('分页选择不会丢掉其他页面的用例，表头只取消当前页', async () => {
  mount(25)
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByText('已选 26 / 26 条')).toBeInTheDocument())
  await user.click(screen.getByRole('checkbox', { name: '选择当前页用例' }))
  expect(screen.getByText('已选 6 / 26 条')).toBeInTheDocument()
  await user.click(screen.getByTitle('2'))
  expect(screen.getByRole('checkbox', { name: '选择用例：检索记录21' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: '选择用例：转换成功' })).toBeChecked()
  await user.click(screen.getByRole('checkbox', { name: '选择用例：转换成功' }))
  expect(screen.getByText('已选 5 / 26 条')).toBeInTheDocument()
})
