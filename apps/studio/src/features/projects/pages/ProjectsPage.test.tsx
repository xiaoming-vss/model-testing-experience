import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import userEvent from '@testing-library/user-event'
import { ProjectsPage } from './ProjectsPage'
import { useWorkbenchStore } from '../store/workbench.store'

const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.splice(0).forEach(client => client.clear()); vi.restoreAllMocks() })

function mount(board: string, selectedSprint: string | null = 's1', documentType = 'word') {
  useWorkbenchStore.setState({ activeProjectId: 'p1', activeSprintId: selectedSprint, activeSprintProjectId: 'p1', projectModalOpen: false, editingProject: null })
  const paths: string[] = []
  const project = { projectId: 'p1', name: '项目', role: 'owner', permissions: ['read', 'write', 'manage'] }
  const binding = { provider: 'zentao', bindingId: 'b1', status: 'active', remoteResourceId: '301', remoteNameSnapshot: '绑定对象' }
  const sprints = [1, 2, 3].map(n => ({ sprintId: `s${n}`, projectId: 'p1', name: `迭代${n}`, status: 'planned', zentaoBinding: n === 1 ? binding : null }))
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = String(input)
    paths.push(path)
    const url = new URL(path, 'http://localhost')
    const page = Number(url.searchParams.get('page') ?? 1)
    const sprintId = url.searchParams.get('sprintId') ?? url.pathname.match(/\/sprints\/(s\d)\//)?.[1] ?? 's1'
    const requirements = Array.from({ length: page === 1 ? 8 : 1 }, (_, n) => ({ requirementId: `${sprintId}-r${page}-${n}`, sprintId, sprintName: `迭代${sprintId.slice(1)}`, name: `需求${page}-${n}`, createdAt: '2026-10-13T05:21:04Z', codeBindings: n === 0 ? [{ repository: 'team/service', branch: 'dev' }, { repository: 'team/web', branch: 'main' }] : [], documentType, documentFileId: n === 0 ? 'file-1' : undefined, documentFilename: n === 0 ? '需求说明.docx' : undefined, zentaoBinding: n === 0 ? binding : null }))
    const data = path === '/v1/projects' ? { items: [project], total: 1 }
      : path === '/v1/projects/p1' ? project
        : path.endsWith('/sprints') ? { items: sprints, total: 3 }
          : url.pathname.endsWith('/requirements') ? { items: requirements, total: selectedSprint ? 8 : 21 }
            : { items: [], total: 0 }
    return new Response(JSON.stringify({ code: 0, message: 'ok', data }))
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/projects?board=${board}`]}><ProjectsPage /></MemoryRouter></QueryClientProvider>)
  return { paths, client }
}

it.each(['sprints', 'requirements'])('进入 %s 列表不逐条查询绑定，需求只查当前范围', async board => {
  const { paths, client } = mount(board)
  await waitFor(() => expect(document.querySelectorAll(board === 'sprints' ? '.sprint-board-card' : '.requirements-card').length).toBe(board === 'sprints' ? 3 : 8))
  await waitFor(() => expect(client.isFetching()).toBe(0))
  expect(paths.filter(path => new URL(path, 'http://localhost').pathname.endsWith('/requirements'))).toEqual(board === 'sprints' ? [] : ['/v1/projects/p1/requirements?page=1&pageSize=20&sprintId=s1'])
  expect(paths.filter(path => path.endsWith('/bindings'))).toEqual([])
  expect(screen.getAllByText('绑定对象')).toHaveLength(1)
})

it('全部迭代使用项目级分页，翻页后只展示服务器返回的本页', async () => {
  const { paths, client } = mount('requirements', null)
  await screen.findByText('需求1-0')
  await waitFor(() => expect(client.isFetching()).toBe(0))
  expect(paths).toContain('/v1/projects/p1/requirements?page=1&pageSize=20')
  fireEvent.click(document.querySelector('.ant-pagination-item-2')!)
  await screen.findByText('需求2-0')
  expect(screen.queryByText('需求1-0')).not.toBeInTheDocument()
  expect(paths).toContain('/v1/projects/p1/requirements?page=2&pageSize=20')
  expect(paths.filter(path => path.endsWith('/bindings'))).toEqual([])
  act(() => useWorkbenchStore.getState().setActiveSprintId('s2'))
  await waitFor(() => expect(paths).toContain('/v1/projects/p1/requirements?page=1&pageSize=20&sprintId=s2'))
  expect(paths).not.toContain('/v1/projects/p1/requirements?page=2&pageSize=20&sprintId=s2')
  await screen.findByText('需求1-0')
  act(() => useWorkbenchStore.getState().setActiveSprintId(null))
  await waitFor(() => expect(client.isFetching()).toBe(0))
  expect(screen.queryByText('需求2-0')).not.toBeInTheDocument()
  expect(paths.filter(path => path === '/v1/projects/p1/requirements?page=2&pageSize=20')).toHaveLength(1)
})


it('列表编辑缺失原文时允许切换 Word，旧下载结果不再阻塞保存', async () => {
  let reject!: (error: Error) => void
  vi.spyOn(api, 'downloadRequirementDocument').mockReturnValue(new Promise((_, no) => { reject = no }))
  const replace = vi.spyOn(api, 'replaceRequirementDocument').mockResolvedValue({ name: '更新需求', documentType: 'docx' })
  const update = vi.spyOn(api, 'updateRequirement')
  mount('requirements', 's1', 'text')
  const user = userEvent.setup()
  await screen.findByText('需求1-0')
  await user.click(screen.getAllByRole('button', { name: '编辑需求' })[0])
  await user.click(screen.getByRole('combobox', { name: '需求文档类型' }))
  await user.click(screen.getByText('Word', { selector: '.ant-select-item-option-content' }))
  await act(async () => reject(new Error('旧源文件缺失')))
  expect(screen.queryByText(/旧源文件缺失/)).not.toBeInTheDocument()
  const file = new File(['docx fixture'], 'replacement.docx')
  fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } })
  await user.clear(screen.getByLabelText('需求名称'))
  await user.type(screen.getByLabelText('需求名称'), '更新需求')
  await user.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(replace).toHaveBeenCalledWith('s1-r1-0', expect.objectContaining({ name: '更新需求', documentType: 'word', file })))
  expect(update).not.toHaveBeenCalled()
})

it('需求列表使用卡片和全局迭代范围，不重复显示局部迭代筛选', async () => {
  mount('requirements')
  await screen.findByText('需求1-0')
  expect(screen.getAllByRole('article')).toHaveLength(8)
  expect(screen.getByRole('link', { name: '需求1-0' })).toHaveAttribute('href', '/requirements/s1-r1-0')
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  expect(screen.queryByText('筛选迭代')).not.toBeInTheDocument()
  expect(screen.getByText('team/service · dev（共 2 项）')).toBeInTheDocument()
  expect(screen.getAllByText('2026/10/13 13:21')).toHaveLength(8)
  expect(screen.queryByText('迭代1 · 8 条需求')).not.toBeInTheDocument()
  expect(screen.getAllByText('未提供文档')).toHaveLength(7)
  expect(screen.queryByRole('button', { name: '查看文档' })).not.toBeInTheDocument()
  expect(screen.getByText('需求说明.docx')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '刷新' })).toBeInTheDocument()
})
