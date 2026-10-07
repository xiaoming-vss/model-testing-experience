import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import * as filesApi from '@/shared/api/files'
import { BugEvidencePanel } from './BugEvidencePanel'
afterEach(() => { cleanup(); vi.restoreAllMocks() })
it('排除富文本图片，默认不请求预览，点击后展示并可收起', async () => {
  const request = vi.spyOn(filesApi, 'downloadStoredFile').mockResolvedValue({ blob: new Blob(['png']), filename: '附件.png' })
  URL.createObjectURL = vi.fn(() => 'blob:evidence'); URL.revokeObjectURL = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><BugEvidencePanel
    descriptionHtml='<p><img data-file-id="inline"></p>'
    attachments={[{ fileId: 'inline', filename: '正文.png', size: 10, contentType: 'image/png' },
      { fileId: 'file', filename: '附件.png', size: 10, contentType: 'image/png' }]}
    download={vi.fn()} /></QueryClientProvider>)
  expect(screen.queryByText('正文.png')).not.toBeInTheDocument()
  expect(screen.getByText('1 个附件')).toBeInTheDocument()
  expect(request).not.toHaveBeenCalled()
  expect(screen.queryByRole('img', { name: '附件.png' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '附件.png' }))
  expect(await screen.findByRole('img', { name: '附件.png' })).toBeInTheDocument()
  expect(request).toHaveBeenCalledWith('file')
  await userEvent.click(screen.getByRole('button', { name: '收起预览' }))
  expect(screen.queryByRole('img', { name: '附件.png' })).not.toBeInTheDocument()
  client.clear()
})
