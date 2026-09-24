import '@/app/styles/buttons.css'
import { App as AntdApp, ConfigProvider } from 'antd'
import { useEffect, type ReactNode } from 'react'
import { bindFeedbackMessage } from '@/shared/utils/feedback'

const themeConfig = {
  token: {
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
      headerBg: '#ffffff',
      siderBg: '#f2f3ff',
      bodyBg: '#faf9ff',
      triggerBg: '#f2f3ff',
    },
    Menu: {
      itemBg: 'transparent',
      itemColor: '#667085',
      itemSelectedColor: '#6d5dfc',
      itemHoverColor: '#6d5dfc',
      itemSelectedBg: 'transparent',
      itemHoverBg: 'rgba(109, 93, 252, 0.08)',
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
  return (
    <ConfigProvider theme={themeConfig}>
      <AntdApp component="div">
        <FeedbackProvider>{children}</FeedbackProvider>
      </AntdApp>
    </ConfigProvider>
  )
}
