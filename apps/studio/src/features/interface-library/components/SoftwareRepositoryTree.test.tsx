import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import { useSoftwareRepositoryTreeView } from '../hooks/useSoftwareRepositoryTreeView'
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

/** Renders the tree the way the page does, with its view state owned one level above the tree. */
function MountedTree(props: Omit<ComponentProps<typeof SoftwareRepositoryTree>, 'view'>) {
  const view = useSoftwareRepositoryTreeView()
  return <SoftwareRepositoryTree view={view} {...props} />
}

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
      <MountedTree
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

/** Repositories render expanded with their tag groups collapsed. */
async function expandGroup(
  user: ReturnType<typeof userEvent.setup>,
  tag: string,
) {
  await user.click(
    await screen.findByRole('button', { name: `展开分组「${tag}」` }),
  )
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

  it('expands repositories by default and loads their interfaces', async () => {
    renderTree()

    expect(await screen.findByText('Orders')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '收起订单服务' }),
    ).toBeInTheDocument()
    expect(interfaceLibraryApi.getSoftwareRepositoryApiInterfaces).toHaveBeenCalled()
  })

  it('collapses and expands a repository', async () => {
    const user = userEvent.setup()
    renderTree()

    await screen.findByText('Orders')
    await user.click(screen.getByRole('button', { name: '收起订单服务' }))
    expect(screen.queryByText('Orders')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '展开订单服务' }),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '展开订单服务' }))
    expect(await screen.findByText('Orders')).toBeInTheDocument()
  })

  it('groups interfaces by their first OpenAPI tag and keeps untagged interfaces last', async () => {
    const { container } = renderTree()

    await screen.findByText('Auth')
    const headers = [...container.querySelectorAll('.if-app-tag-name')].map(node => node.textContent)
    expect(headers).toEqual(['Auth', 'Orders', '未分类'])
  })

  it('sorts interfaces inside a tag group by path and method', async () => {
    const user = userEvent.setup()
    renderTree()
    await expandGroup(user, 'Orders')

    const ordersGroup = screen.getByText('Orders').closest('.if-app-tag-group')
    expect(ordersGroup).not.toBeNull()
    const titles = within(ordersGroup as HTMLElement)
      .getAllByRole('button')
      .map(button => button.getAttribute('title'))
      .filter((title): title is string => Boolean(title))
    expect(titles).toEqual(['查询订单 /orders', '更新订单 /orders/{id}'])
  })

  it('renders interface methods as compact text labels instead of tags', async () => {
    const user = userEvent.setup()
    const { container } = renderTree()
    await expandGroup(user, 'Orders')

    const ordersGroup = screen.getByText('Orders').closest('.if-app-tag-group') as HTMLElement
    expect(within(ordersGroup).getByText('GET')).toHaveClass('if-app-method')
    expect(container.querySelector('.if-app-child .ant-tag')).toBeNull()
  })

  it('offers group rename and removal without touching the untagged group', async () => {
    const user = userEvent.setup()
    const onRenameGroup = vi.fn()
    const onRemoveGroup = vi.fn()
    renderTree({ onRenameGroup, onRemoveGroup })

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
    await expandGroup(user, 'Orders')

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
    await expandGroup(user, 'Orders')

    expect(screen.getByTitle('查询订单 /orders')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '分组「Orders」更多操作' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '查询订单 更多操作' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /新建分组/ })).not.toBeInTheDocument()
  })

  it('keeps tag groups collapsed until they are expanded', async () => {
    const user = userEvent.setup()
    renderTree()

    await screen.findByRole('button', { name: '展开分组「Orders」' })
    expect(screen.queryByTitle('查询订单 /orders')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '展开分组「Orders」' }))
    expect(screen.getByTitle('查询订单 /orders')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '收起分组「Orders」' }))
    expect(screen.queryByTitle('查询订单 /orders')).not.toBeInTheDocument()
  })

  it('shows persisted empty groups and offers group creation', async () => {
    const user = userEvent.setup()
    const onCreateGroup = vi.fn()
    renderTree({ interfaceGroups: ['空分组'], onCreateGroup })
    await expandGroup(user, '空分组')

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
