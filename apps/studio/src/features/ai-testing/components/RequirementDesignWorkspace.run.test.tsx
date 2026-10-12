import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { api } from '@/services/api'
import { requirementDesignApi } from '../api/requirementDesign.api'
import { RequirementDesignWorkspace } from './RequirementDesignWorkspace'

vi.mock('@/features/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))
vi.mock('./RequirementTaskRunDialogs', () => ({ RequirementTaskRunDialogs: () => null }))
const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks() })

it.each(['requirement_analysis', 'function', 'api', 'ui'] as const)('%s 默认人工审核，支持关闭、取消及下次重置，单授权也需确认', async kind => {
  const connections = [{ connectionId: 'mine', name: '本人模型', status: 'active' as const, provider: 'openai', baseUrl: 'https://example.test', authType: 'api_key', account: '', hasAccessToken: true }]
  vi.spyOn(api, 'getLlmConnections').mockResolvedValue(Object.assign(connections, { items: [...connections], total: connections.length }))
  vi.spyOn(requirementDesignApi, 'overview').mockResolvedValue({ tasks: [{ taskId: 'task', kind, name: '任务', sourceType: 'requirement', hasSource: true, sourceFilename: '' }], runCounts: { requirement_analysis: 0, function: 0, api: 0, ui: 0 }, adoptedUnderstanding: true })
  vi.spyOn(requirementDesignApi, 'history').mockResolvedValue({ items: [], total: 0 })
  const start = vi.spyOn(requirementDesignApi, 'start').mockResolvedValue({ runId: 'run' })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<MemoryRouter><TestThemeProvider><QueryClientProvider client={client}><RequirementDesignWorkspace requirementId="req" projectId="project" canWrite canExecute canReview /></QueryClientProvider></TestThemeProvider></MemoryRouter>)
  const user = userEvent.setup()
  if (kind !== 'requirement_analysis') await user.click(await screen.findByRole('tab', { name: { function: '功能测试0', api: 'API 测试0', ui: 'UI 测试0' }[kind] }))
  const run = await screen.findByRole('button', { name: kind === 'requirement_analysis' ? '运行分析' : '生成用例' })
  await waitFor(() => expect(run).toBeEnabled())
  await user.click(run)
  const hasCheckpoint = kind === 'requirement_analysis' || kind === 'function'
  if (hasCheckpoint) expect(await screen.findByRole('switch', { name: '人工审核' })).toBeChecked()
  else expect(screen.queryByRole('switch', { name: '人工审核' })).not.toBeInTheDocument()
  expect(start).not.toHaveBeenCalled()
  await user.type(await screen.findByRole('textbox', { name: '补充指令' }), '重点验证边界条件')
  await user.click(screen.getByRole('radio', { name: '本人模型' }))
  await user.click(screen.getByRole('button', { name: '确认运行' }))
  await waitFor(() => expect(start).toHaveBeenLastCalledWith('req', kind, expect.objectContaining({ connectionId: 'mine', checkpointEnabled: hasCheckpoint, instruction: '重点验证边界条件' })))
  await waitFor(() => expect(run).toBeEnabled())
  await user.click(run)
  expect(await screen.findByRole('textbox', { name: '补充指令' })).toHaveValue('')
  if (hasCheckpoint) await user.click(await screen.findByRole('switch', { name: '人工审核' }))
  await user.click(screen.getByRole('radio', { name: '本人模型' }))
  await user.click(screen.getByRole('button', { name: '确认运行' }))
  await waitFor(() => expect(start).toHaveBeenLastCalledWith('req', kind, expect.objectContaining({ checkpointEnabled: false, instruction: '' })))
  await waitFor(() => expect(run).toBeEnabled())
  await user.click(run)
  if (hasCheckpoint) expect(await screen.findByRole('switch', { name: '人工审核' })).toBeChecked()
  await user.type(await screen.findByRole('textbox', { name: '补充指令' }), '取消不提交')
  await user.click(screen.getByRole('button', { name: /^取\s*消$/ }))
  await waitFor(() => expect(run).toBeEnabled())
  expect(start).toHaveBeenCalledTimes(2)
})
