import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { BugDescriptionTemplates } from './BugDescriptionTemplates'
afterEach(cleanup)
it('空描述直接插入标准模板', async () => {
  const onChange = vi.fn()
  render(<TestThemeProvider><BugDescriptionTemplates value="<p><br></p>" onChange={onChange} /></TestThemeProvider>)
  await userEvent.click(screen.getByRole('button', { name: '标准模板' }))
  expect(onChange).toHaveBeenCalledWith(expect.stringContaining('【复现步骤】'))
  expect(onChange).toHaveBeenCalledWith(expect.stringContaining('【预期结果】'))
})
it('已有截图时必须确认，取消不修改内容', async () => {
  const onChange = vi.fn()
  render(<TestThemeProvider><BugDescriptionTemplates value='<p><img src="/screenshot.png"></p>' onChange={onChange} /></TestThemeProvider>)
  await userEvent.click(screen.getByRole('button', { name: '接口异常' }))
  await userEvent.click(await screen.findByRole('button', { name: '保留原内容' }))
  expect(onChange).not.toHaveBeenCalled()
  await waitFor(() => expect(screen.queryByRole('button', { name: '保留原内容' })).not.toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: '崩溃 Crash' }))
  await userEvent.click(await screen.findByRole('button', { name: '替 换' }))
  expect(onChange).toHaveBeenCalledWith(expect.stringContaining('【错误日志 / 堆栈】'))
})
