import { ConfigProvider } from 'antd'
import type { ReactNode } from 'react'
import { ThemeProvider } from '@/app/providers/ThemeProvider'

// jsdom does not play CSS animations; modal enter classes otherwise keep opacity at zero.
// Retain the real theme and accessibility styles while making transitions immediate.
export function TestThemeProvider({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <ConfigProvider theme={{ token: { motion: false } }}>{children}</ConfigProvider>
    </ThemeProvider>
  )
}
