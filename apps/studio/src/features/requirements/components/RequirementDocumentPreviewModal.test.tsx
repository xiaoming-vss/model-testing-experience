import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import understandingSource from '@/domain/requirements/fixtures/requirement-understanding.example.json?raw'
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
    expect(screen.getByText('已有内容')).toBeInTheDocument()
  })

  it('supports keyboard resizing of the comparison split', () => {
    renderPreview()

    const separator = screen.getByRole('separator', { name: '调整原文与增强文本宽度' })
    expect(separator).toHaveAttribute('aria-valuenow', '50')

    fireEvent.keyDown(separator, { key: 'ArrowRight' })

    expect(separator).toHaveAttribute('aria-valuenow', '52')
  })

  it('结构化需求理解产物在增强文本面板折叠展示 UI 交互章节', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    try {
      render(
        <QueryClientProvider client={client}>
          <RequirementDocumentPreviewContent requirementName="EGO 配套本地 Server 端" documentType="text" documentContent={understandingSource} documentFilename="understanding.json" />
        </QueryClientProvider>,
      )

      expect(screen.getByRole('heading', { name: 'UI 交互' })).toBeInTheDocument()
      const entry = screen.getByRole('button', { name: /转换数据 \/ 筛选任务列表$/ })
      expect(entry).toHaveAttribute('aria-expanded', 'false')
      await userEvent.setup().click(entry)
      expect(entry).toHaveAttribute('aria-expanded', 'true')
      expect(screen.getByRole('button', { name: /转换类型$/ })).toBeInTheDocument()
      expect(screen.queryByText('交互说明')).not.toBeInTheDocument()
    } finally {
      client.clear()
    }
  })
})

it('renders downloaded HTML as formatted requirement content', async () => {
  const { vi } = await import('vitest')
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    if (String(input).includes('/download')) return new Response(JSON.stringify({ url: 'https://storage.example/requirement.html' }), { headers: { 'Content-Type': 'application/json' } })
    return new Response('<h2>图文需求标题</h2><table><tbody><tr><td>表格内容</td></tr></tbody></table>')
  })
  const client = new QueryClient()
  try {
    render(<QueryClientProvider client={client}><RequirementDocumentPreviewContent requirementId="rich" documentType="richtext" documentFilename="requirement.html" /></QueryClientProvider>)
    await waitFor(() => expect(screen.getByRole('heading', { name: '图文需求标题' })).toBeInTheDocument())
    expect(screen.getByRole('cell', { name: '表格内容' })).toBeInTheDocument()
    expect(screen.getByText('富文本需求')).toBeInTheDocument()
  } finally {
    fetchMock.mockRestore()
    client.clear()
  }
})

it('文本预览网络失败后可重试读取同一文档', async () => {
  const { vi } = await import('vitest')
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('网络连接中断'))
    .mockResolvedValueOnce(new Response(JSON.stringify({ url: 'https://storage.example/content.txt' }), { headers: { 'Content-Type': 'application/json' } }))
    .mockResolvedValueOnce(new Response('恢复的原始文档内容'))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  try {
    render(<QueryClientProvider client={client}><RequirementDocumentPreviewContent documentType="text" documentDownloadUrl="https://storage.example/source.txt" /></QueryClientProvider>)
    expect(await screen.findByRole('alert')).toHaveTextContent('网络连接中断')
    fireEvent.click(screen.getByRole('button', { name: '重试预览' }))
    expect(await screen.findByText('恢复的原始文档内容')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(3)
  } finally { fetchMock.mockRestore(); client.clear() }
})
