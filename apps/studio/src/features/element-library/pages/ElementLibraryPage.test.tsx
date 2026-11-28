import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { seedOwnerProject } from '@/test/projectAccess'
import { ProjectAccessContext } from '@/domain/projects/hooks/projectAccessContext'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { elementLibraryApi } from '../api/elementLibrary.api'
import { ElementLibraryPage } from './ElementLibraryPage'
import type { SoftwareRepository } from '@/features/interface-library/types'
import type { ElementDetail, ElementGroup, ElementSummary } from '../types'

vi.mock('../api/elementLibrary.api', () => ({
  elementLibraryApi: {
    getGroups: vi.fn(),
    getElements: vi.fn(),
    getElement: vi.fn(),
    createGroup: vi.fn(),
    deleteGroup: vi.fn(),
    createElement: vi.fn(),
    updateElement: vi.fn(),
    deleteElement: vi.fn(),
  },
}))
vi.mock('@/features/interface-library/api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: { getSoftwareRepositories: vi.fn() },
}))

const repositories: SoftwareRepository[] = [{
  softwareRepositoryId: 'repo-1',
  projectId: 'project-1',
  name: 'demo',
  description: '',
  basePath: '/api',
  repository: null,
  interfaceGroups: [],
  interfaceCount: 0,
  version: 1,
}]
const groups: ElementGroup[] = [
  { groupId: 'group-common', kind: 'common', name: '公共元素', routeTemplate: '', elementCount: 2 },
  { groupId: 'group-orders', kind: 'page', name: '订单列表', routeTemplate: '/orders', elementCount: 0 },
]
const selector: ElementSummary = {
  elementId: 'el-1', groupId: 'group-common', name: '顶部项目选择器', scope: '全局',
  locatorType: 'test_id', parameterized: false, verificationStatus: 'verified', version: 3,
}
const orderRow: ElementSummary = {
  elementId: 'el-2', groupId: 'group-common', name: '订单行-{{orderId}}', scope: '订单表格',
  locatorType: 'xpath', parameterized: true, verificationStatus: 'pending', version: 8,
}
const orderRowDetail: ElementDetail = {
  ...orderRow,
  locatorValue: '//tr[@data-order-id="{{orderId}}"]',
  parameters: [{ name: 'orderId', description: '订单号' }],
  updatedAt: '2026-11-24T13:37:00Z',
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function buildClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  return client
}

/** 页面按上下文判断写权限；测试显式提供可写上下文，才能渲染底部新建 / 删除分组。 */
function renderPage(canWrite = true) {
  return render(
    <QueryClientProvider client={buildClient()}>
      <ProjectAccessContext.Provider value={{ projectId: 'project-1', can: () => canWrite, loading: false, error: null }}>
        <MemoryRouter>
          <ElementLibraryPage />
        </MemoryRouter>
      </ProjectAccessContext.Provider>
    </QueryClientProvider>,
  )
}

function statusChip(label: string) {
  const chips = [...document.querySelectorAll<HTMLButtonElement>('[aria-label="按验证状态筛选"] .tp-chip')]
  const node = chips.find(chip => chip.textContent?.trim() === label)
  if (!node) throw new Error(`找不到状态胶囊：${label}`)
  return node
}

beforeEach(() => {
  vi.mocked(interfaceLibraryApi.getSoftwareRepositories).mockResolvedValue(listResponse(repositories))
  vi.mocked(elementLibraryApi.getGroups).mockResolvedValue(listResponse(groups))
  vi.mocked(elementLibraryApi.getElements).mockResolvedValue(listResponse([selector, orderRow]))
  vi.mocked(elementLibraryApi.getElement).mockResolvedValue(orderRowDetail)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('元素库列表', () => {
  it('左栏列出分组和计数，右栏列出元素与筛选总数', async () => {
    renderPage()

    const nav = await screen.findByLabelText('分组列表')
    expect(await within(nav).findByText('全部元素')).toBeTruthy()
    expect(await within(nav).findByText('公共元素')).toBeTruthy()
    expect(await within(nav).findByText('订单列表')).toBeTruthy()

    await waitFor(() => expect(screen.getByText('顶部项目选择器')).toBeTruthy())
    expect(screen.getByText('订单行-{{orderId}}')).toBeTruthy()
    expect(screen.getByText('参数')).toBeTruthy()
    expect(elementLibraryApi.getElements).toHaveBeenLastCalledWith('repo-1', expect.objectContaining({
      groupId: undefined, verificationStatus: undefined, page: 1,
    }))
  })

  it('未选中的分组行显式透明，不露出浏览器默认按钮底色', async () => {
    // 未引入 preflight，裸 button 会带 Chrome 的 ButtonFace 灰底，只能靠 bg-transparent 压掉。
    renderPage()
    const nav = await screen.findByLabelText('分组列表')
    await within(nav).findByText('全部元素')

    const rows = [...nav.querySelectorAll('button')]
    expect(rows.length).toBeGreaterThan(1)
    for (const row of rows.filter(item => item.getAttribute('aria-current') !== 'true')) {
      expect(row.className).toContain('bg-transparent')
    }
  })

  it('状态胶囊按验证状态筛选并回到第一页', async () => {
    renderPage()
    await screen.findByText('顶部项目选择器')

    await userEvent.setup().click(statusChip('已验证'))
    await waitFor(() => expect(elementLibraryApi.getElements).toHaveBeenLastCalledWith('repo-1', expect.objectContaining({
      verificationStatus: 'verified', page: 1,
    })))
    expect(statusChip('已验证').getAttribute('aria-pressed')).toBe('true')

    await userEvent.setup().click(statusChip('全部'))
    await waitFor(() => expect(elementLibraryApi.getElements).toHaveBeenLastCalledWith('repo-1', expect.objectContaining({
      verificationStatus: undefined, page: 1,
    })))
  })

  it('选中页面分组只请求该分组，并显示分组路由', async () => {
    renderPage()
    const nav = await screen.findByLabelText('分组列表')

    await userEvent.setup().click(await within(nav).findByText('订单列表'))
    await waitFor(() => expect(elementLibraryApi.getElements).toHaveBeenLastCalledWith('repo-1', expect.objectContaining({
      groupId: 'group-orders', page: 1,
    })))
    expect(within(nav).getByText('订单列表').closest('button')?.getAttribute('aria-current')).toBe('true')
    expect(screen.getByText('/orders')).toBeTruthy()
  })

  it('点行打开详情抽屉并取回定位值和参数', async () => {
    renderPage()
    await userEvent.setup().click(await screen.findByText('订单行-{{orderId}}'))

    await waitFor(() => expect(elementLibraryApi.getElement).toHaveBeenCalledWith('el-2'))
    const drawer = await waitFor(() => {
      const node = document.querySelector('.ant-drawer')
      if (!node) throw new Error('抽屉没有打开')
      return node as HTMLElement
    })
    await waitFor(() => expect(within(drawer).getByText('定位模板')).toBeTruthy())
    // 定位模板里的 {{…}} 会被拆成 <mark>，按片段和整体文本分别断言。
    expect(within(drawer).getByText('{{orderId}}')).toBeTruthy()
    expect(drawer.textContent).toContain('//tr[@data-order-id="')
    expect(within(drawer).getByLabelText('orderId 样例值')).toBeTruthy()
  })

  it('只有空的页面分组可以删除，公共元素分组禁用删除', async () => {
    renderPage()
    const nav = await screen.findByLabelText('分组列表')
    const removeGroup = () => document.querySelector('[aria-label="删除分组"]') as HTMLButtonElement | null

    await userEvent.setup().click(await within(nav).findByText('公共元素'))
    await waitFor(() => expect(removeGroup()?.disabled).toBe(true))

    await userEvent.setup().click(await within(nav).findByText('订单列表'))
    await waitFor(() => expect(removeGroup()?.disabled).toBe(false))
  })

  it('空分组显示首次空态，筛选无结果显示清除筛选', async () => {
    vi.mocked(elementLibraryApi.getElements).mockResolvedValue(listResponse<ElementSummary>([]))
    renderPage()
    const nav = await screen.findByLabelText('分组列表')

    await userEvent.setup().click(await within(nav).findByText('订单列表'))
    await waitFor(() => expect(screen.getByText('这个分组还没有元素')).toBeTruthy())

    await userEvent.setup().click(statusChip('待验证'))
    await waitFor(() => expect(screen.getByText('没有匹配的元素')).toBeTruthy())
    expect(screen.getByText('清除筛选')).toBeTruthy()
  })
})
