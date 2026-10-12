import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { request } from '@/shared/api/request'
import { RichTextEditor } from './RichTextEditor'
vi.mock('@/shared/api/request', () => ({ request: vi.fn() }))
vi.mock('@/shared/utils/feedback', () => ({ message: { error: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals() })
it('编辑已有图片时加载地址，输出仍只保留文件 ID', async () => {
  vi.mocked(request).mockResolvedValue({ url: 'https://example.test/image.png' })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('image')))
  URL.createObjectURL = vi.fn(() => 'blob:editor-image')
  URL.revokeObjectURL = vi.fn()
  const onChange = vi.fn()
  render(<RichTextEditor value='<p>原有描述</p><img data-file-id="image-1" alt="截图">' onChange={onChange} />)
  await waitFor(() => expect(screen.getByRole('img', { name: '截图' })).toHaveAttribute('src', 'blob:editor-image'))
  expect(screen.getByText('原有描述')).toBeInTheDocument()
  expect(request).toHaveBeenCalledWith('/v1/files/image-1/download')
  for (const [html] of onChange.mock.calls) {
    expect(html).toContain('data-file-id="image-1"')
    expect(html).not.toContain('blob:'); expect(html).not.toContain('https://example.test')
  }
})

it('hydrates asynchronously loaded content and updates the disabled state', async () => {
  const onChange = vi.fn()
  const { rerender } = render(<RichTextEditor value="" onChange={onChange} disabled ariaLabel="需求正文" />)
  expect(screen.getByLabelText('需求正文')).toHaveAttribute('contenteditable', 'false')
  rerender(<RichTextEditor value="<h2>加载的需求</h2><p>正文</p>" onChange={onChange} ariaLabel="需求正文" />)
  await waitFor(() => expect(screen.getByRole('heading', { name: '加载的需求' })).toBeInTheDocument())
  expect(screen.getByLabelText('需求正文')).toHaveAttribute('contenteditable', 'true')
  expect(onChange).not.toHaveBeenCalled()
  rerender(<RichTextEditor value="<p>另一条需求</p>" onChange={onChange} ariaLabel="需求正文" />)
  await waitFor(() => expect(screen.getByText('另一条需求')).toBeInTheDocument())
  expect(screen.queryByText('加载的需求')).not.toBeInTheDocument()
})

it('放大编辑在弹框中打开同一编辑器，输入保留并恢复内联', async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<RichTextEditor value="<p>原始内容</p>" onChange={onChange} ariaLabel="需求文档" />)
  const expand = screen.getByRole('button', { name: '放大编辑' })
  await user.click(expand)
  const dialog = screen.getByRole('dialog', { name: '放大编辑' })
  // 内联编辑面卸载，编辑器整体移动到弹框中。
  expect(screen.queryByRole('button', { name: '放大编辑' })).not.toBeInTheDocument()
  const expandedToggle = within(dialog).getByRole('button', { name: '恢复内联编辑', pressed: true })
  expect(expandedToggle).toHaveAttribute('aria-pressed', 'true')
  const expandedEditor = within(dialog).getByLabelText('需求文档')
  expect(within(dialog).getByText('原始内容')).toBeInTheDocument()
  expect(expandedEditor).toHaveAttribute('contenteditable', 'true')
  // jsdom 无法建立 prosemirror 选区（缺 elementFromPoint），编辑交互由浏览器验收覆盖。
  // jsdom 中离场动画不结束，只断言内联编辑面恢复，不等待弹框节点移除。
  await user.click(within(dialog).getByRole('button', { name: 'Close' }))
  expect(await screen.findByRole('button', { name: '放大编辑' })).toBeInTheDocument()
  expect(screen.getByText('原始内容')).toBeInTheDocument()
  // 回归：antd 关闭后默认保留弹框节点，二次打开必须重新挂载编辑器而不是空弹框。
  await user.click(screen.getByRole('button', { name: '放大编辑' }))
  const reopened = await screen.findByRole('dialog', { name: '放大编辑' })
  expect(within(reopened).getByLabelText('需求文档')).toBeInTheDocument()
  expect(within(reopened).getByText('原始内容')).toBeInTheDocument()
})

it('禁用态不提供放大编辑', () => {
  render(<RichTextEditor value="" disabled ariaLabel="需求文档" />)
  expect(screen.getByRole('button', { name: '放大编辑' })).toBeDisabled()
})
