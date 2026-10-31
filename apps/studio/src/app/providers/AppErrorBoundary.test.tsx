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
