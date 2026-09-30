import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { request } from '@/shared/api/request'
import { RichTextEditor } from './RichTextEditor'
vi.mock('@/shared/api/request', () => ({ request: vi.fn() }))
vi.mock('@/shared/utils/feedback', () => ({ message: { error: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
it('编辑已有图片时加载地址，输出仍只保留文件 ID', async () => {
  vi.mocked(request).mockResolvedValue({ url: 'https://example.test/image.png' })
  const onChange = vi.fn()
  render(<RichTextEditor value='<p>原有描述</p><img data-file-id="image-1" alt="截图">' onChange={onChange} />)
  await waitFor(() => expect(screen.getByRole('img', { name: '截图' })).toHaveAttribute('src', 'https://example.test/image.png'))
  expect(screen.getByText('原有描述')).toBeInTheDocument()
  expect(request).toHaveBeenCalledWith('/v1/files/image-1/download')
  for (const [html] of onChange.mock.calls) {
    expect(html).toContain('data-file-id="image-1"')
    expect(html).not.toContain('https://example.test')
  }
})
