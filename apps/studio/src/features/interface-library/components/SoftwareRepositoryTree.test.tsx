import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiInterfaceListItem, SoftwareRepository } from '../types'
import type { InterfaceGroup } from '../utils/interfaceGroups'
import { SoftwareRepositoryTree } from './SoftwareRepositoryTree'

vi.mock('../api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: {
    getSoftwareRepositoryApiInterfaces: vi.fn(),
  },
}))

const repository: SoftwareRepository = {
  softwareRepositoryId: 'repository-1',
  projectId: 'project-1',
  name: '订单服务',
  description: '',
  basePath: '',
  repository: {
    projectId: '41',
    path: 'commerce/order-service',
    name: 'order-service',
    instanceUrl: 'https://gitlab.example.com',
  },
  interfaceGroups: [],
  interfaceCount: 4,
  version: 1,
}

function interfaceItem(
  overrides: Partial<ApiInterfaceListItem> & Pick<ApiInterfaceListItem, 'interfaceId' | 'name' | 'method' | 'path'>,
): ApiInterfaceListItem {
  return {
    softwareRepositoryId: repository.softwareRepositoryId,
    softwareRepositoryName: repository.name,
    description: '',
    tags: [],
    requirements: [],
    sourceType: 'openapi_file',
    updatedAt: '2026-11-15T10:00:00',
    ...overrides,
  }
}

const interfaces = [
  interfaceItem({ interfaceId: '1', name: '查询订单', method: 'GET', path: '/orders', tags: ['Orders'] }),
  interfaceItem({ interfaceId: '2', name: '登录', method: 'POST', path: '/auth/login', tags: ['Auth'] }),
  interfaceItem({ interfaceId: '3', name: '健康检查', method: 'GET', path: '/health', tags: [] }),
  interfaceItem({
    interfaceId: '4',
    name: '更新订单',
    method: 'PUT',
    path: '/orders/{id}',
    tags: ['Orders'],
  }),
]

function renderTree(
  overrides: {
    canManageInterfaces?: boolean
    interfaceGroups?: string[]
    onCreateGroup?: (repository: SoftwareRepository) => void
    onRenameGroup?: (repository: SoftwareRepository, group: InterfaceGroup) => void
    onRemoveGroup?: (repository: SoftwareRepository, group: InterfaceGroup) => void
    onMoveInterface?: (
      repository: SoftwareRepository,
      item: ApiInterfaceListItem,
      groups: string[],
    ) => void
  } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const treeRepository = overrides.interfaceGroups
    ? { ...repository, interfaceGroups: overrides.interfaceGroups }
    : repository
  return render(
    <QueryClientProvider client={client}>
      <SoftwareRepositoryTree
        repositories={[treeRepository]}
        selectedSoftwareRepositoryId={repository.softwareRepositoryId}
        mode="detail"
        canManageInterfaces={overrides.canManageInterfaces ?? true}
        onSelectRepository={() => {}}
        onShowAll={() => {}}
        onOpenInterface={() => {}}
        onCreateGroup={overrides.onCreateGroup ?? (() => {})}
        onRenameGroup={overrides.onRenameGroup ?? (() => {})}
        onRemoveGroup={overrides.onRemoveGroup ?? (() => {})}
        onMoveInterface={overrides.onMoveInterface ?? (() => {})}
      />
    </QueryClientProvider>,
  )
}

async function expandRepository(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: '展开订单服务' }))
}

describe('SoftwareRepositoryTree', () => {
  beforeEach(() => {
    vi.mocked(interfaceLibraryApi.getSoftwareRepositoryApiInterfaces).mockResolvedValue(
      Object.assign([...interfaces], { items: interfaces, total: interfaces.length }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('loads interfaces only after a repository is expanded', async () => {
    const user = userEvent.setup()
    renderTree()

    expect(
      await screen.findByRole('button', { name: '展开订单服务' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('Orders')).not.toBeInTheDocument()
    expect(interfaceLibraryApi.getSoftwareRepositoryApiInterfaces).not.toHaveBeenCalled()

    await expandRepository(user)
    expect(await screen.findByText('Orders')).toBeInTheDocument()
    expect(interfaceLibraryApi.getSoftwareRepositoryApiInterfaces).toHaveBeenCalled()
  })

  it('groups interfaces by their first OpenAPI tag and keeps untagged interfaces last', async () => {
    const user = userEvent.setup()
    const { container } = renderTree()
    await expandRepository(user)

    await screen.findByText('Auth')
    const headers = [...container.querySelectorAll('.if-app-tag-name')].map(node => node.textContent)
    expect(headers).toEqual(['Auth', 'Orders', '未分类'])
  })

  it('sorts interfaces inside a tag group by path and method', async () => {
    const user = userEvent.setup()
    renderTree()
    await expandRepository(user)

    const ordersGroup = (await screen.findByText('Orders')).closest('.if-app-tag-group')
    expect(ordersGroup).not.toBeNull()
    const titles = within(ordersGroup as HTMLElement)
      .getAllByRole('button')
      .map(button => button.getAttribute('title'))
      .filter((title): title is string => Boolean(title))
    expect(titles).toEqual(['查询订单 /orders', '更新订单 /orders/{id}'])
  })

  it('offers group rename and removal without touching the untagged group', async () => {
    const user = userEvent.setup()
    const onRenameGroup = vi.fn()
    const onRemoveGroup = vi.fn()
    renderTree({ onRenameGroup, onRemoveGroup })
    await expandRepository(user)

    await screen.findByText('Orders')
    expect(
      screen.queryByRole('button', { name: '分组「未分类」更多操作' }),
    ).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '分组「Orders」更多操作' }))
    await user.click(await screen.findByText('重命名分组'))
    expect(onRenameGroup).toHaveBeenCalledWith(
      repository,
      expect.objectContaining({ tag: 'Orders' }),
    )

    await user.click(screen.getByRole('button', { name: '分组「Orders」更多操作' }))
    await user.click(await screen.findByText('移除分组'))
    expect(onRemoveGroup).toHaveBeenCalledWith(
      repository,
      expect.objectContaining({ tag: 'Orders' }),
    )
  })

  it('passes the repository named groups when moving an interface', async () => {
    const user = userEvent.setup()
    const onMoveInterface = vi.fn()
    renderTree({ onMoveInterface })
    await expandRepository(user)

    await screen.findByText('Orders')
    await user.click(screen.getByRole('button', { name: '查询订单 更多操作' }))
    await user.click(await screen.findByText('移动到分组…'))

    expect(onMoveInterface).toHaveBeenCalledWith(
      repository,
      expect.objectContaining({ interfaceId: '1', name: '查询订单' }),
      ['Auth', 'Orders'],
    )
  })

  it('hides group management actions for read-only members', async () => {
    const user = userEvent.setup()
    renderTree({ canManageInterfaces: false })
    await expandRepository(user)

    await screen.findByText('Orders')
    expect(
      screen.queryByRole('button', { name: '分组「Orders」更多操作' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '查询订单 更多操作' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /新建分组/ })).not.toBeInTheDocument()
  })

  it('collapses and expands a tag group', async () => {
    const user = userEvent.setup()
    renderTree()
    await expandRepository(user)

    await screen.findByRole('button', { name: '收起分组「Orders」' })
    expect(screen.getByTitle('查询订单 /orders')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '收起分组「Orders」' }))
    expect(screen.queryByTitle('查询订单 /orders')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '展开分组「Orders」' }),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '展开分组「Orders」' }))
    expect(screen.getByTitle('查询订单 /orders')).toBeInTheDocument()
  })

  it('shows persisted empty groups and offers group creation', async () => {
    const user = userEvent.setup()
    const onCreateGroup = vi.fn()
    renderTree({ interfaceGroups: ['空分组'], onCreateGroup })
    await expandRepository(user)

    expect(await screen.findByText('空分组')).toBeInTheDocument()
    expect(
      screen.getByText('该分组还没有接口，可从接口的「更多操作」移动进来'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /新建分组/ }))
    expect(onCreateGroup).toHaveBeenCalledWith(
      expect.objectContaining({ softwareRepositoryId: repository.softwareRepositoryId }),
    )
  })

  it('uses software repositories only as groups without maintenance actions', async () => {
    renderTree()

    await screen.findByText('订单服务')
    expect(
      screen.queryByRole('button', { name: '新建软件仓库' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '编辑订单服务' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '删除订单服务' }),
    ).not.toBeInTheDocument()
    expect(screen.getByTitle('订单服务')).toBeInTheDocument()
  })
})
