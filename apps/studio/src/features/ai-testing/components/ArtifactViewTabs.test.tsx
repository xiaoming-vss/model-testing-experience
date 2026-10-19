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
