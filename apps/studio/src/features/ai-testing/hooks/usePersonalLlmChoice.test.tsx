import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { usePersonalLlmChoice } from './usePersonalLlmChoice'

vi.mock('@/features/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))
const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks() })
function mount(count = 1, alwaysConfirm = true) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify({ code: 0, data: {
    items: Array.from({ length: count }, (_, index) => ({ connectionId: `llm-${index}`, name: `本人模型 ${index}`, status: 'active', modelId: `model-${index}` })), total: count,
  } }), { headers: { 'Content-Type': 'application/json' } }))
  const onChosen = vi.fn()
  const onRejected = vi.fn()
  function Host() {
    const choice = usePersonalLlmChoice('project')
    return <><button onClick={() => { void choice.choose({ alwaysConfirm }).then(onChosen).catch(onRejected) }}>运行阶段</button>{choice.dialog}</>
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter><Host /></MemoryRouter></QueryClientProvider></TestThemeProvider>)
  return { onChosen, onRejected }
}
it('只有一个授权时也先弹框，明确选择并确认后才运行', async () => {
  const { onChosen } = mount()
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '运行阶段' }))
  expect(await screen.findByText('选择本人 LLM 授权')).toBeInTheDocument()
  const radio = await screen.findByRole('radio', { name: /本人模型 0/ })
  expect(onChosen).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '确认运行' })).toBeDisabled()
  await user.click(radio)
  await user.click(screen.getByRole('button', { name: '确认运行' }))
  await waitFor(() => expect(onChosen).toHaveBeenCalledWith('llm-0'))
})
it('取消模型选择不派发运行', async () => {
  const { onChosen, onRejected } = mount()
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '运行阶段' }))
  await screen.findByText('选择本人 LLM 授权')
  await user.click(screen.getByRole('button', { name: /^取\s*消$/ }))
  await waitFor(() => expect(onRejected).toHaveBeenCalledWith(expect.objectContaining({ message: '已取消操作' })))
  expect(onChosen).not.toHaveBeenCalled()
})
it('多个授权时按本次选择返回模型', async () => {
  const { onChosen } = mount(2)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '运行阶段' }))
  await user.click(await screen.findByRole('radio', { name: /本人模型 1/ }))
  await user.click(screen.getByRole('button', { name: '确认运行' }))
  await waitFor(() => expect(onChosen).toHaveBeenCalledWith('llm-1'))
})

it('其他入口未要求确认时保留单授权自动选择行为', async () => {
  const { onChosen } = mount(1, false)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '运行阶段' }))
  await waitFor(() => expect(onChosen).toHaveBeenCalledWith('llm-0'))
  expect(screen.queryByText('选择本人 LLM 授权')).not.toBeInTheDocument()
})

it('API 运行选择模型时填写本次生成要求', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify({ code: 0, data: { items: [{ connectionId: 'llm', name: '本人模型', status: 'active', modelId: 'model' }], total: 1 } }), { headers: { 'Content-Type': 'application/json' } }))
  const onChosen = vi.fn()
  function Host() {
    const choice = usePersonalLlmChoice('project')
    return <><button onClick={() => { void choice.chooseRun(false, { label: '生成要求（选填）' }).then(onChosen) }}>运行 API</button>{choice.dialog}</>
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter><Host /></MemoryRouter></QueryClientProvider></TestThemeProvider>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '运行 API' }))
  await user.click(await screen.findByRole('radio', { name: /本人模型/ }))
  expect(screen.getByText('仅用于本次阶段运行')).toBeInTheDocument()
  await user.type(screen.getByRole('textbox', { name: '生成要求（选填）' }), '只覆盖登录鉴权')
  await user.click(screen.getByRole('button', { name: '确认运行' }))
  await waitFor(() => expect(onChosen).toHaveBeenCalledWith(expect.objectContaining({ connectionId: 'llm', instruction: '只覆盖登录鉴权' })))
})
