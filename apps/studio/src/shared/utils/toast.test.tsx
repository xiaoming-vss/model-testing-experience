import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import styles from '@/shared/styles/notify.module.css'
import { message } from './feedback'
import { notify } from './toast'

vi.mock('./feedback', () => ({
  message: { open: vi.fn(), destroy: vi.fn() },
}))

const openMock = vi.mocked(message.open)
const destroyMock = vi.mocked(message.destroy)

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('notify', () => {
  it('uses the success defaults', () => {
    notify.success({ title: '已采用该候选', description: '正式用例尚未改变。' })

    const options = openMock.mock.calls[0][0]
    expect(options.duration).toBe(4.8)
    expect(options.className).toContain(styles.notice)
    expect(options.className).toContain(styles.success)
    expect(options.key).toMatch(/^app-notify-/)
    render(options.content)
    expect(screen.getByRole('status')).toHaveTextContent('已采用该候选正式用例尚未改变。')
  })

  it('keeps errors visible longer and marks them as alerts', () => {
    notify.error('操作未完成')

    const options = openMock.mock.calls[0][0]
    expect(options.duration).toBe(6)
    expect(options.className).toContain(styles.notice)
    expect(options.className).toContain(styles.error)
    render(options.content)
    expect(screen.getByRole('alert')).toHaveTextContent('操作未完成')
  })

  it('closes the toast by its key', async () => {
    notify.success({ title: '已保存', key: 'save' })

    const options = openMock.mock.calls[0][0]
    expect(options.key).toBe('save')
    render(options.content)
    await userEvent.click(screen.getByRole('button', { name: '关闭提示' }))
    expect(destroyMock).toHaveBeenCalledWith('save')
  })
})
