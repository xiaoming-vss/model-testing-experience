import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { AppErrorBoundary } from './AppErrorBoundary'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('renders the error instead of a blank page when a child throws', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  function Crash(): never {
    throw new Error('render exploded')
  }

  render(<AppErrorBoundary><Crash /></AppErrorBoundary>)

  expect(screen.getByRole('alert')).toHaveTextContent('页面加载失败')
  expect(screen.getByText('render exploded')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
})

it('explains stale chunk failures instead of showing the raw browser message', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  function Crash(): never {
    throw new Error('Failed to fetch dynamically imported module: https://example.test/assets/a.js')
  }

  render(<AppErrorBoundary><Crash /></AppErrorBoundary>)

  expect(screen.getByText('页面版本已更新，请重新加载以获取最新内容。')).toBeInTheDocument()
  expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument()
})
