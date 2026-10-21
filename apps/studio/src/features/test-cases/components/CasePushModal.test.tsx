import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { functionTestingApi } from '../api/functionTesting.api'
import { CasePushModal } from './CasePushModal'

const access = vi.hoisted(() => ({ role: 'owner' }))
vi.mock('@/features/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ project: { role: access.role }, can: () => true }) }))
const row = { caseId: 'case', title: '登录成功', candidates: [{ id: 41, title: '登录成功' }], mappedRemoteCaseId: null, operation: null }
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><CasePushModal projectId="project" suiteId="suite" caseIds={['case']} count={1} onClose={vi.fn()} /></QueryClientProvider>)
  return client
}
beforeEach(() => { access.role = 'owner' })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('同名用例没有默认覆盖选项，显式选择后才可提交', async () => {
  vi.spyOn(functionTestingApi, 'previewFunctionCasePush').mockResolvedValue({ canConfirmNotApplied: access.role === 'owner', items: [row] })
  const push = vi.spyOn(functionTestingApi, 'importFunctionTestCasesToZentao').mockResolvedValue({ status: 'success', importedCaseCount: 1, items: [{ caseId: 'case', status: 'success', remoteCaseId: 41 }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: '预览并核对' }))
  await screen.findByText('登录成功')
  expect(screen.getByRole('button', { name: '确认推送' })).toBeDisabled()
  await userEvent.click(screen.getByLabelText('推送方式：登录成功'))
  await userEvent.click(await screen.findByText('绑定 #41 · 登录成功'))
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(push).toHaveBeenCalledWith('suite', expect.objectContaining({ choices: { case: 41 }, requestId: expect.any(String) })))
})

it('请求失败后重试复用原编号和内容', async () => {
  vi.spyOn(functionTestingApi, 'previewFunctionCasePush').mockResolvedValue({ canConfirmNotApplied: access.role === 'owner', items: [{ ...row, candidates: [] }] })
  const push = vi.spyOn(functionTestingApi, 'importFunctionTestCasesToZentao').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValue({ status: 'success', importedCaseCount: 1 })
  mount()
  await userEvent.click(screen.getByRole('button', { name: '预览并核对' }))
  await screen.findByText('登录成功')
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await screen.findByText(/连接中断/)
  await userEvent.click(await screen.findByRole('button', { name: '用原请求查询／重试' }))
  await waitFor(() => expect(push).toHaveBeenCalledTimes(2))
  expect(push.mock.calls[1][1]).toEqual(push.mock.calls[0][1])
})

it('重新打开时读取未决记录，阻止推送并提供核对入口', async () => {
  vi.spyOn(functionTestingApi, 'previewFunctionCasePush').mockResolvedValue({ canConfirmNotApplied: access.role === 'owner', items: [{ ...row, operation: { caseId: 'case', operationId: 'operation', status: 'uncertain' } }] })
  const reconcile = vi.spyOn(functionTestingApi, 'reconcileFunctionCasePush').mockResolvedValue({ status: 'success', remoteCaseId: 41 })
  mount()
  await userEvent.click(screen.getByRole('button', { name: '预览并核对' }))
  await screen.findByText('存在未决写入，暂不能推送')
  expect(screen.getByRole('button', { name: '确认推送' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: '核对结果' }))
  await userEvent.type(screen.getByLabelText('已找到的禅道用例 ID'), '41')
  await userEvent.click(screen.getByRole('button', { name: '确认已有结果' }))
  await waitFor(() => expect(reconcile).toHaveBeenCalledWith('suite', 'operation', { resolution: 'confirm', remoteCaseId: 41 }))
})

it('普通成员不能看到人工解除未写入的操作', async () => {
  access.role = 'member'
  vi.spyOn(functionTestingApi, 'previewFunctionCasePush').mockResolvedValue({ canConfirmNotApplied: access.role === 'owner', items: [{ ...row, operation: { caseId: 'case', operationId: 'operation', status: 'uncertain' } }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: '预览并核对' }))
  await userEvent.click(await screen.findByRole('button', { name: '核对结果' }))
  expect(screen.queryByRole('button', { name: '确认未写入并解除锁定' })).not.toBeInTheDocument()
})

it('恢复环境需要所有者额外确认远端核对', async () => {
  vi.spyOn(functionTestingApi, 'previewFunctionCasePush').mockResolvedValue({ restoreRequired: true, canConfirmNotApplied: true, items: [{ ...row, candidates: [] }] })
  const push = vi.spyOn(functionTestingApi, 'importFunctionTestCasesToZentao').mockResolvedValue({ status: 'success', importedCaseCount: 1 })
  mount()
  await userEvent.click(screen.getByRole('button', { name: '预览并核对' }))
  await screen.findByText('数据库恢复后的远端核对')
  expect(screen.getByRole('button', { name: '确认推送' })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /项目所有者确认/ }))
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(push).toHaveBeenCalledWith('suite', expect.objectContaining({ restoreConfirmed: true })))
})
