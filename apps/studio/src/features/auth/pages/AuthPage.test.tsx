import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AuthPage } from './AuthPage'
import '../styles/auth.css'

afterEach(() => {
  cleanup()
  delete document.documentElement.dataset.theme
})

describe('登录页', () => {
  it('在暗色模式使用深色卡片和高对比度文字，并显示 2026 版权年份', () => {
    document.documentElement.dataset.theme = 'dark'
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
    expect(getComputedStyle(shell!).backgroundImage).not.toContain('rgba(255, 255, 255')
    expect(getComputedStyle(title).color).toBe('rgb(240, 246, 252)')
    expect(screen.getByText('© 2026 MTX. 版权所有')).toBeInTheDocument()
  })
})
