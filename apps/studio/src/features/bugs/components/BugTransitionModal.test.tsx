import { ConfigProvider } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import type { Bug } from '../types'
import { BugTransitionModal } from './BugTransitionModal'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
const bug: Bug = {
  id: 1, bugId: 'bug', bugNo: 1, projectId: 'p', title: '登录失败', descriptionHtml: '<p>复现</p>',
  status: 'active', confirmed: true, resolution: '', severity: 'normal', priority: 'medium',
  reporterUserId: 'u', assigneeUserId: 'u', foundSprintId: 's', plannedFixSprintId: '',
  requirementId: '', requirementName: '', sourceOrderId: '', sourceEntryId: '', sourceCaseId: '',
  sourceOrderName: '', sourceCaseTitle: '',
}
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<ConfigProvider theme={{ token: { motion: false } }}><QueryClientProvider client={client}>
    <BugTransitionModal bug={bug} action="resolve" onClose={vi.fn()} />
  </QueryClientProvider></ConfigProvider>)
  return client
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('已修复必须填写实际解决版本，提交版本和修复说明', async () => {
  const transition = vi.spyOn(api, 'transitionBug').mockResolvedValue({ ...bug, status: 'resolved', resolution: 'fixed', resolvedBuild: 'v1.2' })
  const client = show()
  await userEvent.type(screen.getByLabelText('处理说明'), '修复阈值')
  await userEvent.click(screen.getByRole('button', { name: '确认' }))
  expect(await screen.findByText('请填写解决版本')).toBeInTheDocument()
  expect(transition).not.toHaveBeenCalled()
  await userEvent.type(await screen.findByLabelText('解决版本'), 'v1.2')
  await userEvent.click(screen.getByRole('button', { name: '确认' }))
  await waitFor(() => expect(transition).toHaveBeenCalledWith('bug', {
    action: 'resolve', content: '修复阈值', resolution: 'fixed', resolvedBuild: 'v1.2', duplicateBug: undefined,
  }))
  client.clear()
})

it('延期处理不会携带已修复版本，也不会提交旧拒绝动作', async () => {
  const transition = vi.spyOn(api, 'transitionBug').mockResolvedValue({ ...bug, status: 'resolved', resolution: 'postponed' })
  const client = show()
  await userEvent.type(await screen.findByLabelText('解决版本'), 'v1.2')
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '解决方案' }))
  await userEvent.click((await screen.findAllByText('延期处理')).at(-1)!)
  expect(screen.queryByLabelText('解决版本')).not.toBeInTheDocument()
  expect(screen.getByText('延期处理会保留为已解决、未关闭，后续可重新激活。')).toBeInTheDocument()
  await userEvent.type(screen.getByLabelText('处理说明'), '下一版本处理')
  await userEvent.click(screen.getByRole('button', { name: '确认' }))
  await waitFor(() => expect(transition).toHaveBeenCalledWith('bug', {
    action: 'resolve', content: '下一版本处理', resolution: 'postponed', resolvedBuild: undefined, duplicateBug: undefined,
  }))
  client.clear()
})
