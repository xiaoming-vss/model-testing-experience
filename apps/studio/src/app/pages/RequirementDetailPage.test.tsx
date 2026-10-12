import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import * as downloads from '@/shared/utils/download'
import { requirementsApi } from '@/features/requirements/api/requirements.api'
import { RequirementDetailPage } from './RequirementDetailPage'

vi.mock('@/features/ai-testing/components/RequirementDesignWorkspace', () => ({
  RequirementDesignWorkspace: ({ requirementId, projectId, activeTab, onTabChange, document }: {
    requirementId: string; projectId: string; activeTab: string; onTabChange: (tab: string) => void; document: React.ReactNode
  }) => <div>
    <button role="tab" aria-selected={activeTab === 'content'} onClick={() => onTabChange('content')}>需求文档</button>
    <button role="tab" aria-selected={activeTab === 'requirement_analysis'} onClick={() => onTabChange('requirement_analysis')}>需求分析</button>
    <div hidden={activeTab !== 'content'}>{document}</div>
    {activeTab !== 'content' ? <div data-testid="generation-workspace">{requirementId} · {projectId}</div> : null}
  </div>,
}))
vi.mock('@/features/requirements/components/RequirementDocumentPreviewModal', () => ({
  RequirementDocumentPreviewContent: () => <div>需求正文内容</div>,
  RequirementDocumentPreviewModal: () => null,
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
it('默认阅读文档，切换测试设计使用真实需求且保留文档节点', async () => {
  mount()
  expect(await screen.findByRole('heading', { name: '登录需求' })).toBeInTheDocument()
  const document = await screen.findByText('需求正文内容')
  expect(screen.queryByTestId('generation-workspace')).not.toBeInTheDocument()
  await waitFor(() => expect(useWorkbenchStore.getState()).toMatchObject({ activeProjectId: 'canonical-project', activeSprintId: 'sprint' }))
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab', { name: '需求分析' }))
  expect(await screen.findByTestId('generation-workspace')).toHaveTextContent('req · canonical-project')
  expect(screen.queryByRole('separator')).not.toBeInTheDocument()
  expect(document).not.toBeVisible()
  await user.click(screen.getByRole('tab', { name: '需求文档' }))
  expect(screen.getByText('需求正文内容')).toBe(document)
  expect(document).toBeVisible()
})
it.each(['design', 'requirement_analysis', 'function', 'api', 'ui'])('tab=%s 链接直接进入设计工作区', async tab => {
  mount(false, `/requirements/req?tab=${tab}`)
  expect(await screen.findByTestId('generation-workspace')).toHaveTextContent('req · canonical-project')
  expect(screen.getByText('需求正文内容')).not.toBeVisible()
})
it.each(['requirement_analysis', 'function', 'api', 'ui', 'codeRisk'])('tab=%s 工作区不显示编辑需求入口', async tab => {
  mount(false, `/requirements/req?tab=${tab}`)
  expect(await screen.findByRole('heading', { name: '登录需求' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '编辑需求' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('tab', { name: '需求文档' }))
  expect(await screen.findByRole('button', { name: '编辑需求' })).toBeInTheDocument()
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
  await user.click(await screen.findByRole('button', { name: '编辑需求' }))
  expect(await screen.findByRole('heading', { name: '从 S3 加载的正文' })).toBeInTheDocument()
  expect(download).toHaveBeenCalledWith('req')
  await user.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(replace).toHaveBeenCalledWith('req', expect.objectContaining({ documentType: 'richtext', documentContent: html, name: '登录需求' })))
  expect(update).not.toHaveBeenCalled()
})

it('源文件缺失仍可切换富文本并重新填写保存', async () => {
  vi.spyOn(requirementsApi, 'downloadRequirementDocument').mockRejectedValue(new Error('需求原文件未存储到 S3'))
  const replace = vi.spyOn(requirementsApi, 'replaceRequirementDocument').mockResolvedValue({ name: '登录需求', documentType: 'richtext' })
  mount(false, '/requirements/req', 'text')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '编辑需求' }))
  await screen.findByText(/需求正文加载失败/)
  expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
  await user.click(screen.getByRole('combobox', { name: '需求文档类型' }))
  await user.click(screen.getByText('富文本', { selector: '.ant-select-item-option-content' }))
  expect(screen.queryByText(/需求正文加载失败/)).not.toBeInTheDocument()
  pasteRequirementText('重新填写的正文')
  await user.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(replace).toHaveBeenCalledWith('req', expect.objectContaining({ documentType: 'richtext', documentContent: '<p>重新填写的正文</p>' })))
})

it.each(['resolve', 'reject'])('类型切换后忽略旧下载的迟到结果：%s', async outcome => {
  let resolve!: (response: Awaited<ReturnType<typeof requirementsApi.downloadRequirementDocument>>) => void
  let reject!: (error: Error) => void
  vi.spyOn(requirementsApi, 'downloadRequirementDocument').mockReturnValue(new Promise((yes, no) => { resolve = yes; reject = no }))
  mount(false, '/requirements/req', 'text')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '编辑需求' }))
  await user.click(screen.getByRole('combobox', { name: '需求文档类型' }))
  await user.click(screen.getByText('富文本', { selector: '.ant-select-item-option-content' }))
  pasteRequirementText('新正文')
  const blob = await new Response('旧正文').blob()
  await act(async () => {
    if (outcome === 'resolve') resolve({ blob, filename: 'old.txt' })
    else reject(new Error('迟到的错误'))
  })
  expect(screen.getByLabelText('需求正文')).toHaveTextContent('新正文')
  expect(screen.queryByText(/迟到的错误/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '保存' })).toBeEnabled()
})

it('从富文本切换 Word 后必须上传新文件，再同时保存名称与文件', async () => {
  vi.spyOn(requirementsApi, 'downloadRequirementDocument').mockRejectedValue(new Error('文件缺失'))
  const replace = vi.spyOn(requirementsApi, 'replaceRequirementDocument').mockResolvedValue({ name: '更新需求', documentType: 'docx' })
  const update = vi.spyOn(requirementsApi, 'updateRequirement')
  mount(false, '/requirements/req', 'richtext')
  const user = userEvent.setup()
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


function pasteRequirementText(text: string) {
  const editor = screen.getByLabelText('需求正文')
  act(() => { editor.focus() })
  fireEvent.paste(editor, { clipboardData: { getData: (type: string) => type === 'text/plain' ? text : '', types: ['text/plain'], files: [] } })
}

it('切换多个 Tab 后返回需求列表，保留当前项目与迭代范围', async () => {
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('tab', { name: '需求分析' }))
  await user.click(screen.getByRole('tab', { name: '需求文档' }))
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
  const button = await screen.findByRole('button', { name: '下载原文件' })
  expect(button.closest('.requirement-detail-header')).not.toBeNull()
  await user.click(button)
  await waitFor(() => expect(saveBlob).toHaveBeenCalledWith(blob, '原始需求.docx'))
  expect(download).toHaveBeenCalledWith('req')
})
