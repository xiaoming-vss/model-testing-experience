import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AuthPage } from './AuthPage'
import '../styles/auth.css'

afterEach(() => {
  cleanup()
})

describe('登录页', () => {
  it('使用高对比度标题文字，并显示 2026 版权年份', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AuthPage mode="login" />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const shell = document.querySelector('.auth-shell')
    const title = screen.getByRole('heading', { name: '欢迎回来' })

    expect(shell).toBeInTheDocument()
    expect(getComputedStyle(title).color).toBe('rgb(24, 32, 45)')
    expect(screen.getByText('© 2026 MTX. 版权所有')).toBeInTheDocument()
  })
})
