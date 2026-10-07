import '@/app/styles/buttons.css'
import { App as AntdApp, ConfigProvider, theme as antdTheme, type ThemeConfig } from 'antd'
import { useEffect, useLayoutEffect, type ReactNode } from 'react'
import { bindFeedbackMessage } from '@/shared/utils/feedback'
import { startThemeSync, useThemeStore } from '@/shared/theme/theme.store'

const themeConfig = {
  token: {
    colorPrimary: '#4e59b8',
    colorInfo: '#4e59b8',
    colorLink: '#4e59b8',
    colorLinkHover: '#3b4597',
    colorLinkActive: '#303b87',
    colorBgBase: '#e8edf6',
    colorBgContainer: '#e8edf6',
    colorBgElevated: '#e8edf6',
    colorBgLayout: '#e2e8f2',
    colorBorder: '#c7d0e3',
    colorBorderSecondary: '#d3ddeb',
    colorText: '#263250',
    colorTextSecondary: '#677493',
    colorTextTertiary: '#677493',
    colorTextQuaternary: '#98a2bd',
    borderRadius: 10,
  },
  components: {
    Button: {
      borderRadius: 8,
      defaultShadow: 'none',
      primaryShadow: 'none',
      dangerShadow: 'none',
      fontWeight: 500,
    },
    Layout: {
      headerBg: '#e8edf6',
      siderBg: '#e2e7f2',
      bodyBg: '#e2e8f2',
      triggerBg: '#e2e7f2',
    },
    Menu: {
      itemBg: 'transparent',
      itemColor: '#455375',
      itemSelectedColor: '#6a4f1f',
      itemHoverColor: '#8b6723',
      itemSelectedBg: '#f6e6bf',
      itemHoverBg: '#d2dbec',
    },
  },
}

// Ant Design needs concrete values for its palette algorithms. Keep these aligned
// with the Primer-inspired primitives in github-dark-tokens.css.
const darkThemeConfig: ThemeConfig = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    ...themeConfig.token,
    colorPrimary: '#58a6ff',
    colorInfo: '#58a6ff',
    colorSuccess: '#3fb950',
    colorWarning: '#d29922',
    colorError: '#f85149',
    colorBgBase: '#0d1117',
    colorBgContainer: '#161b22',
    colorBgElevated: '#1c2128',
    colorBgLayout: '#0d1117',
    colorBorder: '#30363d',
    colorBorderSecondary: '#30363d',
    colorText: '#e6edf3',
    colorTextSecondary: '#8b949e',
    colorTextTertiary: '#8b949e',
    colorTextQuaternary: '#6e7681',
    colorLink: '#58a6ff',
    colorLinkHover: '#79c0ff',
    colorLinkActive: '#58a6ff',
  },
  components: {
    ...themeConfig.components,
    Layout: { headerBg: '#161b22', siderBg: '#161b22', bodyBg: '#0d1117', triggerBg: '#161b22' },
    Menu: {
      itemBg: 'transparent', itemColor: '#8b949e', itemSelectedColor: '#58a6ff',
      itemHoverColor: '#e6edf3', itemSelectedBg: '#21262d', itemHoverBg: '#21262d',
    },
  },
}

function FeedbackProvider({ children }: { children: ReactNode }) {
  const { message } = AntdApp.useApp()

  useEffect(() => {
    bindFeedbackMessage(message)
  }, [message])

  return children
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)
  useLayoutEffect(startThemeSync, [])
  return (
    <ConfigProvider theme={resolvedTheme === 'dark' ? darkThemeConfig : themeConfig}>
      <AntdApp component="div">
        <FeedbackProvider>{children}</FeedbackProvider>
      </AntdApp>
    </ConfigProvider>
  )
}
