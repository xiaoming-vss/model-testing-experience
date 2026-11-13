import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
        documentType="richtext"
        documentContent={'管理员账号登录\n\n支持设备管理与任务作业管理。'}
        documentFilename="requirement.html"
      />
    </QueryClientProvider>,
  )
}

describe('RequirementDocumentPreviewContent', () => {
  it('展示需求原文，不显示旧的增强文本面板', () => {
    const { container } = renderPreview()
    expect(container.querySelectorAll('.requirement-document-pane')).toHaveLength(1)
    expect(container.querySelector('.requirement-document-text-article')).toHaveTextContent('管理员账号登录')
    expect(screen.queryByText('增强文本')).not.toBeInTheDocument()
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

it('需求文档预览网络失败后可重试读取同一文档', async () => {
  const { vi } = await import('vitest')
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('网络连接中断'))
    .mockResolvedValueOnce(new Response(JSON.stringify({ url: 'https://storage.example/content.html' }), { headers: { 'Content-Type': 'application/json' } }))
    .mockResolvedValueOnce(new Response('恢复的原始文档内容'))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  try {
    render(<QueryClientProvider client={client}><RequirementDocumentPreviewContent documentType="richtext" documentDownloadUrl="https://storage.example/source.html" /></QueryClientProvider>)
    expect(await screen.findByRole('alert')).toHaveTextContent('网络连接中断')
    fireEvent.click(screen.getByRole('button', { name: '重试预览' }))
    expect(await screen.findByText('恢复的原始文档内容')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(3)
  } finally { fetchMock.mockRestore(); client.clear() }
})
