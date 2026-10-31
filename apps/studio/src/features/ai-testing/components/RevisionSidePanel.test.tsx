import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { seedOwnerProject } from '@/test/projectAccess'
import { downloadStoredFile, uploadStoredFile } from '@/shared/api/files'
import { RevisionSidePanel } from './RevisionSidePanel'
import { useRevisionAttachments } from '../hooks/useRevisionAttachments'

vi.mock('@/shared/api/files', () => ({
  uploadStoredFile: vi.fn(async () => 'image-1'),
  downloadStoredFile: vi.fn(async () => ({
    blob: new Blob(['png'], { type: 'image/png' }),
    filename: 'login.png',
  })),
}))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function Harness({ onSubmit }: { onSubmit: (connectionId: string) => void }) {
  const revision = useRevisionAttachments()
  const [value, setValue] = useState('')
  return <RevisionSidePanel
    projectId="project-1"
    value={value}
    onChange={setValue}
    attachments={revision.attachments}
    onAddAttachment={revision.addAttachment}
    onRemoveAttachment={revision.removeAttachment}
    onSubmit={onSubmit}
    onCancel={() => undefined}
    loading={false}
  />
}

function setup() {
  vi.clearAllMocks()
  const onSubmit = vi.fn()
  URL.createObjectURL = vi.fn(() => 'blob:attachment-1')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = new URL(String(input), 'http://localhost').pathname
    const data = path.includes('/integrations/llm/connections')
      ? { items: [{ connectionId: 'mine', name: '本人模型', status: 'active' }], total: 1 }
      : { items: [], total: 0 }
    return new Response(JSON.stringify({ code: 0, message: 'ok', data }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  render(<QueryClientProvider client={client}><Harness onSubmit={onSubmit} /></QueryClientProvider>)
  return onSubmit
}

it('上传图片后展示预览，并可随优化指令一起提交', async () => {
  const onSubmit = setup()
  const user = userEvent.setup()
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(input, new File(['png'], 'login.png', { type: 'image/png' }))
  expect(await screen.findByAltText('login.png')).toHaveAttribute('src', 'blob:attachment-1')
  expect(vi.mocked(uploadStoredFile)).toHaveBeenCalledWith(
    'project-1', expect.any(File), 'attachment'
  )
  expect(vi.mocked(downloadStoredFile)).toHaveBeenCalledWith('image-1')
  await user.type(screen.getByLabelText('优化指令'), '按截图补充登录异常')
  await waitFor(() => expect(screen.getByRole('button', { name: '提交优化' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: '提交优化' }))
  expect(onSubmit).toHaveBeenCalledWith('mine')
})

it('粘贴截图会进入同一上传流程，移除图片后释放预览地址', async () => {
  setup()
  const textarea = screen.getByLabelText('优化指令')
  fireEvent.paste(textarea, {
    clipboardData: {
      files: [new File(['png'], 'paste.png', { type: 'image/png' })],
      getData: () => '',
    },
  })
  expect(await screen.findByAltText('paste.png')).toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('button', { name: '移除图片 paste.png' }))
  expect(screen.queryByAltText('paste.png')).toBeNull()
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:attachment-1')
})

it('非 PNG/JPEG 文件不会上传', async () => {
  setup()
  const user = userEvent.setup()
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(input, new File(['pdf'], 'requirement.pdf', { type: 'application/pdf' }))
  expect(vi.mocked(uploadStoredFile)).not.toHaveBeenCalled()
})
