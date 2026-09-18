import '@/app/styles/buttons.css'
import { App as AntdApp, ConfigProvider, theme as antdTheme } from 'antd'
import { useEffect, useMemo, type ReactNode } from 'react'
import { useThemeStore } from '@/shared/store/theme.store'
import { bindFeedbackMessage } from '@/shared/utils/feedback'

function FeedbackProvider({ children }: { children: ReactNode }) {
  const { message } = AntdApp.useApp()

  useEffect(() => {
    bindFeedbackMessage(message)
  }, [message])

  return children
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const mode = useThemeStore((state) => state.mode)

  useEffect(() => {
    document.documentElement.dataset.theme = mode
    document.body.dataset.theme = mode
  }, [mode])

  const themeConfig = useMemo(
    () => ({
      algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      token:
        mode === 'dark'
          ? {
              colorPrimary: '#7cc3a3',
              colorInfo: '#7cc3a3',
              colorSuccess: '#7cc3a3',
              colorWarning: '#f5c26b',
              colorError: '#ff6b81',
              colorBgBase: '#191d27',
              colorBgContainer: '#202531',
              colorBgElevated: '#262c39',
              colorTextBase: '#e6edf7',
              colorText: '#e6edf7',
              colorTextSecondary: '#96a0b5',
              colorBorder: '#2f3544',
              colorSplit: '#2a3040',
              borderRadius: 10,
            }
          : {
              colorPrimary: '#1677ff',
              colorInfo: '#1677ff',
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
          headerBg: mode === 'dark' ? '#1d2230' : '#ffffff',
          siderBg: mode === 'dark' ? '#171c28' : '#f2f3ff',
          bodyBg: mode === 'dark' ? '#171b26' : '#faf9ff',
          triggerBg: mode === 'dark' ? '#171c28' : '#f2f3ff',
        },
        Menu: {
          itemBg: 'transparent',
          itemColor: mode === 'dark' ? '#96a0b5' : '#667085',
          itemSelectedColor: mode === 'dark' ? '#7cc3a3' : '#6d5dfc',
          itemHoverColor: mode === 'dark' ? '#7cc3a3' : '#6d5dfc',
          itemSelectedBg: 'transparent',
          itemHoverBg: mode === 'dark' ? 'rgba(124, 195, 163, 0.08)' : 'rgba(109, 93, 252, 0.08)',
        },
      },
    }),
    [mode],
  )

  return (
    <ConfigProvider theme={themeConfig}>
      <AntdApp component="div">
        <FeedbackProvider>{children}</FeedbackProvider>
      </AntdApp>
    </ConfigProvider>
  )
}
