import { useState, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import * as downloads from '@/shared/utils/download'
import { requirementsApi } from '@/features/requirements/api/requirements.api'
import { RequirementDetailPage } from './RequirementDetailPage'

vi.mock('@/features/ai-testing/components/RequirementDesignWorkspace', () => ({
  RequirementDesignWorkspace: ({ requirementId, projectId, documentPreview, onReadingNodeChange }: {
    requirementId: string; projectId: string; documentPreview?: ReactNode
    onReadingNodeChange?: (node: { label: string; status?: string; tone?: string; kind?: 'document' } | null) => void
  }) => {
    const [open, setOpen] = useState(false)
    const toggle = () => {
      const next = !open
      setOpen(next)
      onReadingNodeChange?.(next ? { label: '需求文档', status: '只读来源', tone: 'is-muted', kind: 'document' } : null)
    }
    return <div data-testid="generation-workspace">
      {requirementId} · {projectId}
      <button type="button" onClick={toggle}>查看需求文档</button>
      {open ? <div role="dialog" aria-label="需求文档">{documentPreview}</div> : null}
    </div>
  },
}))
vi.mock('@/features/requirements/components/RequirementDocumentPreviewModal', () => ({
  RequirementDocumentPreviewContent: () => <div>需求正文内容</div>,
}))
const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks(); useWorkbenchStore.setState({ activeProjectId: undefined, activeSprintId: undefined }) })
function response(data: unknown, status = 200) { return new Response(JSON.stringify({ code: status === 200 ? 0 : status, message: status === 200 ? 'ok' : '无权访问需求', data }), { status, headers: { 'Content-Type': 'application/json' } }) }
function mount(forbidden = false, entry = '/requirements/req', documentType = 'docx') {
  useWorkbenchStore.setState({ activeProjectId: 'other-project', activeSprintId: 'other-sprint' })
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (path === '/v1/requirements/req') return forbidden ? response({}, 403) : response({ requirementId: 'req', sprintId: 'sprint', name: '登录需求', documentType, documentFilename: 'prd.docx' })
    if (path === '/v1/sprints/sprint') return response({ sprintId: 'sprint', projectId: 'canonical-project', name: '当前需求迭代' })
    if (path === '/v1/projects/canonical-project') return response({ projectId: 'canonical-project', role: 'owner', permissions: ['read', 'write', 'execute', 'review'] })
    return response({ items: [], total: 0 })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); clients.push(client)
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter initialEntries={[entry]}><Routes><Route path="/projects" element={<div>需求列表页面</div>} /><Route path="/requirements/:requirementId" element={<RequirementDetailPage />} /></Routes></MemoryRouter></QueryClientProvider></TestThemeProvider>)
}
it('进入需求直接展示生成全景，文档交给工作区在画布内打开', async () => {
  mount()
  expect(await screen.findByRole('heading', { name: '登录需求' })).toBeInTheDocument()
  // 标题栏与生成全景共用同一个容器。
  const header = screen.getByRole('heading', { name: '登录需求' }).closest('.requirement-detail-header')
  expect(header?.parentElement).toHaveClass('requirement-detail-main')
  expect(header?.closest('.requirement-detail-page')).not.toBeNull()
  expect(await screen.findByTestId('generation-workspace')).toHaveTextContent('req · canonical-project')
  expect(screen.queryByRole('tablist', { name: '需求工作区' })).not.toBeInTheDocument()
  expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  expect(screen.queryByText('需求正文内容')).not.toBeInTheDocument()
  await waitFor(() => expect(useWorkbenchStore.getState()).toMatchObject({ activeProjectId: 'canonical-project', activeSprintId: 'sprint' }))
  await userEvent.setup().click(screen.getByRole('button', { name: '查看需求文档' }))
  expect(await screen.findByRole('dialog', { name: '需求文档' })).toBeInTheDocument()
  const crumbs = document.querySelector('.requirement-detail-crumbs')
  expect(crumbs).toHaveTextContent('需求文档')
  expect(crumbs).not.toHaveTextContent('只读来源')
})
it.each(['design', 'requirement_analysis', 'function', 'api', 'ui', 'codeRisk', 'content'])('旧 tab=%s 链接仍直接展示生成全景', async tab => {
  mount(false, `/requirements/req?tab=${tab}`)
  expect(await screen.findByTestId('generation-workspace')).toHaveTextContent('req · canonical-project')
  expect(screen.queryByRole('tab')).not.toBeInTheDocument()
})
it('下载与编辑只在打开需求文档时出现，生成链刷新始终可用', async () => {
  mount()
  expect(await screen.findByRole('heading', { name: '登录需求' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '编辑需求' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '下载原文件' })).not.toBeInTheDocument()
  // 刷新从生成全景移到需求标题栏。
  const refresh = await screen.findByRole('button', { name: '刷新' })
  expect(refresh.closest('.requirement-detail-header')).not.toBeNull()
  await userEvent.setup().click(screen.getByRole('button', { name: '查看需求文档' }))
  expect(await screen.findByRole('dialog', { name: '需求文档' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '编辑需求' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '下载原文件' })).toBeInTheDocument()
})

it('无权读取需求时隐藏工作区且不改变当前项目范围', async () => {
  mount(true)
  await screen.findByText('无权访问需求')
  expect(screen.queryByTestId('generation-workspace')).not.toBeInTheDocument()
  expect(useWorkbenchStore.getState().activeProjectId).toBe('other-project')
})


it('详情编辑从源文件加载富文本，并保存为新的正文文件', async () => {
  const html = '<h2>从 S3 加载的正文</h2><p>清洗开关</p>'
  const download = vi.spyOn(requirementsApi, 'downloadRequirementDocument').mockResolvedValue({ blob: await new Response(html).blob(), filename: 'requirement.html' })
  const replace = vi.spyOn(requirementsApi, 'replaceRequirementDocument').mockResolvedValue({ name: '登录需求', documentType: 'richtext' })
  const update = vi.spyOn(requirementsApi, 'updateRequirement')
  mount(false, '/requirements/req', 'richtext')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '查看需求文档' }))
  await user.click(await screen.findByRole('button', { name: '编辑需求' }))
  expect(await screen.findByRole('heading', { name: '从 S3 加载的正文' })).toBeInTheDocument()
  expect(download).toHaveBeenCalledWith('req')
  await user.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(replace).toHaveBeenCalledWith('req', expect.objectContaining({ documentType: 'richtext', documentContent: html, name: '登录需求' })))
  expect(update).not.toHaveBeenCalled()
})

it('从富文本切换 Word 后必须上传新文件，再同时保存名称与文件', async () => {
  vi.spyOn(requirementsApi, 'downloadRequirementDocument').mockRejectedValue(new Error('文件缺失'))
  const replace = vi.spyOn(requirementsApi, 'replaceRequirementDocument').mockResolvedValue({ name: '更新需求', documentType: 'docx' })
  const update = vi.spyOn(requirementsApi, 'updateRequirement')
  mount(false, '/requirements/req', 'richtext')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '查看需求文档' }))
  await user.click(await screen.findByRole('button', { name: '编辑需求' }))
  await screen.findByText(/需求正文加载失败/)
  await user.click(screen.getByRole('combobox', { name: '需求文档类型' }))
  await user.click(screen.getByText('Word', { selector: '.ant-select-item-option-content' }))
  await user.click(screen.getByRole('button', { name: '保存' }))
  expect(await screen.findByText('请上传 Word 文件')).toBeInTheDocument()
  expect(replace).not.toHaveBeenCalled()
  const file = new File(['docx fixture'], 'new.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
  fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } })
  await user.clear(screen.getByLabelText('需求名称'))
  await user.type(screen.getByLabelText('需求名称'), '更新需求')
  await user.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(replace).toHaveBeenCalledWith('req', expect.objectContaining({ name: '更新需求', documentType: 'word', file })))
  expect(update).not.toHaveBeenCalled()
})


it('从生成全景返回需求列表，保留当前项目与迭代范围', async () => {
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '查看需求文档' }))
  await user.click(screen.getByRole('button', { name: '返回需求列表' }))
  expect(await screen.findByText('需求列表页面')).toBeInTheDocument()
  expect(useWorkbenchStore.getState()).toMatchObject({ activeProjectId: 'canonical-project', activeSprintId: 'sprint' })
})

it('需求读取失败可就地重试恢复正文', async () => {
  const read = vi.spyOn(requirementsApi, 'getRequirement').mockRejectedValueOnce(new Error('连接中断'))
    .mockResolvedValue({ requirementId: 'req', sprintId: 'sprint', name: '恢复后的需求', documentType: 'docx' })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '重试读取' }))
  expect(await screen.findByRole('heading', { name: '恢复后的需求' })).toBeInTheDocument()
  expect(read).toHaveBeenCalledTimes(2)
})

it('顶部下载原文件使用当前需求并保留服务端文件名', async () => {
  const blob = new Blob(['original'])
  const download = vi.spyOn(requirementsApi, 'downloadRequirementDocument').mockResolvedValue({ blob, filename: '原始需求.docx' })
  const saveBlob = vi.spyOn(downloads, 'saveBlob').mockImplementation(() => {})
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '查看需求文档' }))
  const button = await screen.findByRole('button', { name: '下载原文件' })
  expect(button.closest('.requirement-detail-header')).not.toBeNull()
  await user.click(button)
  await waitFor(() => expect(saveBlob).toHaveBeenCalledWith(blob, '原始需求.docx'))
  expect(download).toHaveBeenCalledWith('req')
})
