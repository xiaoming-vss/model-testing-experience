import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { BugAttachmentUploader } from './BugAttachmentUploader'
afterEach(cleanup)
it('回显已有附件并保留本次新选附件', () => {
  render(<BugAttachmentUploader existing={[{ fileId: 'f1', filename: '已有日志.txt', size: 10, contentType: 'text/plain' }]}
    items={[{ uid: 'new', name: '新增.txt', file: new File(['new'], '新增.txt') }]} onChange={vi.fn()} />)
  expect(screen.getByText('已有日志.txt')).toBeInTheDocument()
  expect(screen.getByText('新增.txt')).toBeInTheDocument()
})
