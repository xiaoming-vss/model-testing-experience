import '@/app/styles/buttons.css'
import { App as AntdApp, ConfigProvider, theme as antdTheme, type ThemeConfig } from 'antd'
import { useEffect, useLayoutEffect, type ReactNode } from 'react'
import { bindFeedbackMessage } from '@/shared/utils/feedback'
import { startThemeSync, useThemeStore } from '@/shared/theme/theme.store'

const themeConfig = {
  token: {
    fontFamily: 'var(--app-font-sans)',
    fontSize: 13,
    colorPrimary: '#2563c9',
    colorInfo: '#2563c9',
    colorLink: '#2563c9',
    colorLinkHover: '#1d4fa5',
    colorLinkActive: '#193f83',
    colorBgBase: '#f5f8fc',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBgLayout: '#f0f4f9',
    colorBorder: '#c7d0e3',
    colorBorderSecondary: '#d3ddeb',
    colorText: '#35455d',
    colorTextSecondary: '#5d6e87',
    colorTextTertiary: '#65758d',
    colorTextQuaternary: '#98a2bd',
    borderRadius: 10,
  },
  components: {
    Input: { colorBgContainer: '#f5f8fc', colorBorder: '#d3e0f0' },
    Select: { colorBgContainer: '#f5f8fc', colorBorder: '#d3e0f0' },
    Button: {
      borderRadius: 8,
      defaultShadow: 'none',
      primaryShadow: 'none',
      dangerShadow: 'none',
      fontWeight: 500,
    },
    Layout: {
      headerBg: '#f5f8fc',
      siderBg: '#f5f8fc',
      bodyBg: '#f0f4f9',
      triggerBg: '#f5f8fc',
    },
    Menu: {
      itemBg: 'transparent',
      itemColor: '#5d6e87',
      itemSelectedColor: '#2563c9',
      itemHoverColor: '#1d4fa5',
      itemSelectedBg: '#e8f1ff',
      itemHoverBg: '#eaf1fb',
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
    Button: themeConfig.components.Button,
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
