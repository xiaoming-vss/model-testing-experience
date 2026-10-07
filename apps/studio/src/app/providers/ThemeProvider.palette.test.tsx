import { cleanup, render, screen } from '@testing-library/react'
import { theme } from 'antd'
import { afterEach, expect, it } from 'vitest'
import { ThemeProvider } from './ThemeProvider'
import { useThemeStore } from '@/shared/theme/theme.store'
import light from '@/shared/styles/indigo-amber-light-tokens.css?raw'

const initialState = useThemeStore.getState()
const initialTheme = document.documentElement.dataset.theme
const initialScheme = document.documentElement.style.colorScheme

function PaletteProbe() {
  const { token } = theme.useToken()
  return <output data-testid="palette">{JSON.stringify({
    base: token.colorBgBase, container: token.colorBgContainer,
    elevated: token.colorBgElevated, border: token.colorBorder,
  })}</output>
}

afterEach(() => {
  cleanup()
  useThemeStore.setState(initialState)
  if (initialTheme === undefined) delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = initialTheme
  document.documentElement.style.colorScheme = initialScheme
})

it('aligns Ant Design controls, checkboxes and popup containers with the light CSS surface', () => {
  useThemeStore.setState({ preference: 'light', resolvedTheme: 'light' })
  render(<ThemeProvider><PaletteProbe /></ThemeProvider>)
  const palette = JSON.parse(screen.getByTestId('palette').textContent!)
  const surface = light.match(/--app-surface:\s*([^;]+);/)![1].trim()
  expect([palette.base, palette.container, palette.elevated]).toEqual([surface, surface, surface])
})

it('keeps the existing GitHub Dark controls and popup palette', () => {
  useThemeStore.setState({ preference: 'dark', resolvedTheme: 'dark' })
  render(<ThemeProvider><PaletteProbe /></ThemeProvider>)
  expect(JSON.parse(screen.getByTestId('palette').textContent!)).toEqual({
    base: '#0d1117', container: '#161b22', elevated: '#1c2128', border: '#30363d',
  })
})
