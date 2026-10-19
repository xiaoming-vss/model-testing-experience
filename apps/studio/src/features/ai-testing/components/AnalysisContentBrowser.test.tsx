import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { AnalysisContentBrowser } from './AnalysisContentBrowser'
import { AnalysisFactorBrowser } from './AnalysisFactorBrowser'
afterEach(cleanup)

it('搜索、筛选与目录选择同步右侧详情，清空筛选可恢复', async () => {
  const user = userEvent.setup()
  render(<AnalysisContentBrowser title="场景拆解" compact filterStatus entries={[
    { key: 'a', code: 'S01', title: '成功', searchText: '通过', status: 'ready', content: <p>成功详情</p> },
    { key: 'b', code: 'S02', title: '失败', searchText: '异常', status: 'blocked', content: <p>失败详情</p> },
  ]} />)
  await user.click(screen.getByRole('button', { name: 'S02 失败' }))
  expect(screen.getByText('失败详情')).toBeVisible()
  const search = screen.getByRole('searchbox', { name: '搜索场景拆解' })
  await user.type(search, '通过')
  expect(screen.getByText('成功详情')).toBeVisible()
  expect(screen.queryByText('失败详情')).not.toBeInTheDocument()
  await user.clear(search)
  await user.click(screen.getByRole('combobox', { name: '场景生成状态' }))
  await user.click(screen.getByText('暂不可生成测试点'))
  expect(screen.getByText('失败详情')).toBeVisible()
  await user.type(search, '不存在')
  expect(screen.getByText('没有匹配的条目')).toBeVisible()
  expect(screen.queryByText('失败详情')).not.toBeInTheDocument()
  await user.clear(search)
  expect(screen.getByText('失败详情')).toBeVisible()
})

it('因素按内容搜索，保留数组、零值及缺失字段语义', async () => {
  const user = userEvent.setup()
  render(<AnalysisFactorBrowser entries={[
    { factorId: 'F01', name: '数量', confirmedValues: [0, 1], defaultValue: 0, clarificationNeeded: [] },
    { factorId: 'F02', name: '状态', confirmedValues: ['失败'], clarificationNeeded: '重试次数待确认' },
  ]} />)
  expect(within(screen.getByRole('region', { name: '默认值' })).getByText('0')).toBeVisible()
  await user.type(screen.getByRole('searchbox', { name: '搜索场景因素' }), '重试')
  expect(screen.queryByText('数量')).not.toBeInTheDocument()
  expect(screen.getByText('重试次数待确认')).toBeVisible()
  expect(screen.getByText('未明确')).toBeVisible()
  await user.clear(screen.getByRole('searchbox', { name: '搜索场景因素' }))
  await user.click(screen.getByRole('button', { name: 'F01 数量' }))
  expect(within(screen.getByRole('region', { name: '已确认取值' })).getAllByRole('listitem')).toHaveLength(2)
  expect(within(screen.getByRole('region', { name: '待澄清内容' })).getByText('无')).toBeVisible()
})
