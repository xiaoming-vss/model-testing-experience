import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button, Result } from 'antd'
import '../styles/error-boundary.css'

type AppErrorBoundaryState = {
  error: Error | null
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled Studio render error', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children

    return <main className="app-error-boundary" role="alert">
      <Result
        status="error"
        title="页面加载失败"
        subTitle={this.state.error.message || '发生了未处理的错误，请重新加载页面。'}
        extra={<Button type="primary" onClick={() => window.location.reload()}>重新加载</Button>}
      />
    </main>
  }
}
