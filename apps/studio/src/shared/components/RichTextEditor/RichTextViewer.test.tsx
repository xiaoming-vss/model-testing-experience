import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { RichTextViewer } from './RichTextViewer'
import * as files from '@/shared/api/files'

afterEach(() => vi.restoreAllMocks())

it('displays historical images through blob URLs and releases them on unmount', async () => {
  vi.spyOn(files, 'downloadStoredFile').mockResolvedValue({ blob: new Blob(['image']), filename: 'evidence.png' })
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:evidence')
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const view = render(<RichTextViewer html='<p>历史证据</p><img data-file-id="file-1" alt="evidence" />' />)
  await waitFor(() => expect(screen.getByAltText('evidence')).toHaveAttribute('src', 'blob:evidence'))
  expect(create).toHaveBeenCalledTimes(1)
  view.unmount()
  expect(revoke).toHaveBeenCalledWith('blob:evidence')
})

it('allows a failed historical image to be authorized again on manual recovery', async () => {
  const download = vi.spyOn(files, 'downloadStoredFile').mockRejectedValueOnce(new Error('对象存储暂不可用'))
    .mockResolvedValueOnce({ blob: new Blob(['image']), filename: 'image.png' })
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:recovered')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  render(<RichTextViewer html='<img data-file-id="file-1" alt="evidence" />' />)
  fireEvent.click(await screen.findByRole('button', { name: '重新加载图片' }))
  await waitFor(() => expect(screen.getByAltText('evidence')).toHaveAttribute('src', 'blob:recovered'))
  expect(download).toHaveBeenCalledTimes(2)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
