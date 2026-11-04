import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { request } from '@/shared/api/request'
import { StoredImage } from './StoredFile'
import { createLiveArtifactUrl, revokeLiveArtifactUrl } from '@/shared/utils/liveArtifactUrls'

vi.mock('@/shared/api/request', () => ({ request: vi.fn() }))
vi.mock('antd', () => ({
  Image: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
  Typography: { Text: ({ children }: { children: React.ReactNode }) => <span>{children}</span> },
  Button: () => null, message: { error: vi.fn() },
}))
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks() })

it('requests a private file ticket and fetches S3 without platform credentials', async () => {
  vi.mocked(request).mockResolvedValue({ url: 'https://s3.test/signed', filename: 'shot.png' })
  const fetchMock = vi.fn().mockResolvedValue(new Response('png'))
  vi.stubGlobal('fetch', fetchMock)
  URL.createObjectURL = vi.fn(() => 'blob:shot')
  URL.revokeObjectURL = vi.fn()
  const { unmount } = render(<StoredImage src="/v1/files/f/download" alt="截图" />)
  await waitFor(() => expect(screen.getByAltText('截图')).toHaveAttribute('src', 'blob:shot'))
  expect(request).toHaveBeenCalledWith('/v1/files/f/download')
  expect(fetchMock).toHaveBeenCalledWith('https://s3.test/signed', { credentials: 'omit' })
  unmount()
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:shot')
})

it('does not fall back to public worker URLs for legacy screenshots', async () => {
  render(<StoredImage src="http://worker:9010/old.png" alt="历史截图" />)
  expect(await screen.findByText('历史文件未存入 S3，请重新执行任务')).toBeInTheDocument()
  expect(request).not.toHaveBeenCalled()
})

it('renders registered live screenshots and rejects other object URLs', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(['png'], { type: 'image/png' })))
  vi.stubGlobal('fetch', fetchMock)
  URL.createObjectURL = vi.fn().mockReturnValueOnce('blob:live').mockReturnValueOnce('blob:display')
  URL.revokeObjectURL = vi.fn()
  const live = createLiveArtifactUrl([new Uint8Array([1, 2, 3])], 'image/png')
  const { unmount } = render(<StoredImage src={live} alt="临时截图" />)
  await waitFor(() => expect(screen.getByAltText('临时截图')).toHaveAttribute('src', 'blob:display'))
  expect(fetchMock).toHaveBeenCalledWith('blob:live')
  expect(request).not.toHaveBeenCalled()
  unmount()
  revokeLiveArtifactUrl(live)
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:live')

  render(<StoredImage src="blob:unregistered" alt="未授权" />)
  expect(await screen.findByText('历史文件未存入 S3，请重新执行任务')).toBeInTheDocument()
})
