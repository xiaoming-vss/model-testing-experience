import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { ArtifactViewTabs } from './ArtifactViewTabs'
import { message } from '@/shared/utils/feedback'
vi.mock('@/shared/utils/feedback', async importOriginal => ({ ...await importOriginal<typeof import('@/shared/utils/feedback')>(), message: { success: vi.fn(), error: vi.fn() } }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })
it('copies the current JSON draft only from JSON mode and reports clipboard failure', async () => {
  const user = userEvent.setup()
  const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
  const items = [{ key: 'business', label: '业务内容', children: '内容' }, { key: 'json', label: 'JSON', children: 'JSON 内容' }]
  const view = render(<TestThemeProvider><ArtifactViewTabs items={items} jsonCopyText='{"a":1}' /></TestThemeProvider>)
  expect(screen.queryByRole('button', { name: '复制 JSON' })).toBeNull()
  await user.click(screen.getByText('JSON', { exact: true }))
  view.rerender(<TestThemeProvider><ArtifactViewTabs items={items} jsonCopyText='{"a":2}' /></TestThemeProvider>)
  await user.click(screen.getByRole('button', { name: '复制 JSON' }))
  expect(copy).toHaveBeenCalledWith('{"a":2}')
  copy.mockRejectedValueOnce(new Error('denied'))
  await user.click(screen.getByRole('button', { name: '复制 JSON' }))
  await waitFor(() => expect(message.error).toHaveBeenCalled())
})

it('隐藏的页签保留状态，但不跟着父级更新重渲染', async () => {
  const user = userEvent.setup()
  const renders = { visual: 0 }
  function Probe({ text }: { text: string }) {
    renders.visual += 1
    return <p>{text}</p>
  }
  const renderTabs = (text: string) => (
    <TestThemeProvider>
      <ArtifactViewTabs defaultActiveKey="visual" items={[
        { key: 'visual', label: '可视化', children: <Probe text={text} /> },
        { key: 'json', label: 'JSON', children: 'JSON 内容' },
      ]} />
    </TestThemeProvider>
  )
  const view = render(renderTabs('第一版'))
  expect(screen.getByText('第一版')).toBeInTheDocument()
  await user.click(screen.getByText('JSON', { exact: true }))
  const rendersAfterSwitch = renders.visual

  view.rerender(renderTabs('第二版'))
  expect(renders.visual).toBe(rendersAfterSwitch)

  await user.click(screen.getByText('可视化', { exact: true }))
  expect(await screen.findByText('第二版')).toBeInTheDocument()
  expect(renders.visual).toBeGreaterThan(rendersAfterSwitch)
})
