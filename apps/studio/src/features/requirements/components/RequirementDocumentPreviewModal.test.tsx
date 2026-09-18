import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { RequirementDocumentPreviewContent } from './RequirementDocumentPreviewModal'

afterEach(cleanup)

function renderPreview() {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <RequirementDocumentPreviewContent
        requirementName="EGO 配套本地 Server 端"
        documentType="text"
        documentContent={'管理员账号登录\n\n支持设备管理与任务作业管理。'}
        documentFilename="ego-local-server.txt"
      />
    </QueryClientProvider>,
  )
}

describe('RequirementDocumentPreviewContent', () => {
  it('renders comparison mode without focused-reading tabs', () => {
    const { container } = renderPreview()

    expect(screen.queryByText('左右内容可独立滚动')).not.toBeInTheDocument()
    expect(screen.queryByText('对照阅读')).not.toBeInTheDocument()
    expect(container.querySelectorAll('.requirement-document-pane')).toHaveLength(2)
    expect(screen.getByText('管理员账号登录')).toBeInTheDocument()
    expect(screen.queryByText('仅看原文')).not.toBeInTheDocument()
    expect(screen.queryByText('仅看增强文本')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '放大预览' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '需求文档全屏阅读' })).not.toBeInTheDocument()
    expect(screen.getByText('已提取')).toBeInTheDocument()
  })

  it('supports keyboard resizing of the comparison split', () => {
    renderPreview()

    const separator = screen.getByRole('separator', { name: '调整原文与增强文本宽度' })
    expect(separator).toHaveAttribute('aria-valuenow', '50')

    fireEvent.keyDown(separator, { key: 'ArrowRight' })

    expect(separator).toHaveAttribute('aria-valuenow', '52')
  })
})
