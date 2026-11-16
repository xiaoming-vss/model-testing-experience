import {
  AppstoreOutlined,
  DownOutlined,
  MoreOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useQueries } from '@tanstack/react-query'
import { Button, Dropdown, Empty, Input, Spin, Tag } from 'antd'
import { useMemo, useState } from 'react'
import { listItems, listTotal } from '@/services/api'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiInterfaceListItem, SoftwareRepository } from '../types'
import {
  UNTAGGED_GROUP,
  groupItemsByTag,
  withEmptyGroups,
  type InterfaceGroup,
} from '../utils/interfaceGroups'
import { methodTone } from '../utils/interfaceForm'

type Props = {
  repositories: SoftwareRepository[]
  loading?: boolean
  selectedSoftwareRepositoryId: string
  selectedInterfaceId?: string
  mode: 'list' | 'detail'
  canManageInterfaces: boolean
  onSelectRepository: (softwareRepositoryId: string) => void
  onShowAll: () => void
  onOpenInterface: (interfaceId: string) => void
  onCreateGroup: (repository: SoftwareRepository) => void
  onRenameGroup: (repository: SoftwareRepository, group: InterfaceGroup) => void
  onRemoveGroup: (repository: SoftwareRepository, group: InterfaceGroup) => void
  onMoveInterface: (
    repository: SoftwareRepository,
    item: ApiInterfaceListItem,
    groups: string[],
  ) => void
}

const ALL_PAGE_SIZE = 200
const ALL_MAX_PAGES = 50

async function loadAllRepositoryInterfaces(softwareRepositoryId: string) {
  const all: ApiInterfaceListItem[] = []
  let total: number
  let page = 1
  do {
    const response = await interfaceLibraryApi.getSoftwareRepositoryApiInterfaces(
      softwareRepositoryId,
      {
        page,
        pageSize: ALL_PAGE_SIZE,
      },
    )
    const items = listItems(response) as ApiInterfaceListItem[]
    all.push(...items)
    total = listTotal(response) || all.length
    if (!items.length) break
    page += 1
  } while (all.length < total && page <= ALL_MAX_PAGES)
  return Object.assign(all, { items: all, total })
}

/** 接口库左侧软件仓库树：仓库即一级分组，仓库内按 OpenAPI 标签分组。 */
export function SoftwareRepositoryTree({
  repositories,
  loading = false,
  selectedSoftwareRepositoryId,
  selectedInterfaceId,
  mode,
  canManageInterfaces,
  onSelectRepository,
  onShowAll,
  onOpenInterface,
  onCreateGroup,
  onRenameGroup,
  onRemoveGroup,
  onMoveInterface,
}: Props) {
  const [repositorySearch, setRepositorySearch] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    () => new Set(),
  )
  // Every repository starts collapsed; interfaces are fetched only after an explicit expand.
  const [expandedRepositories, setExpandedRepositories] = useState<Set<string>>(
    () => new Set(),
  )

  const visibleRepositories = useMemo(() => {
    const keyword = repositorySearch.trim().toLowerCase()
    return repositories.filter(repository => {
      if (!keyword) return true
      return (
        repository.name.toLowerCase().includes(keyword) ||
        (repository.repository?.path ?? '').toLowerCase().includes(keyword)
      )
    })
  }, [repositories, repositorySearch])

  const expandedVisibleRepositories = useMemo(
    () =>
      visibleRepositories.filter(repository =>
        expandedRepositories.has(repository.softwareRepositoryId),
      ),
    [expandedRepositories, visibleRepositories],
  )
  const childQueries = useQueries({
    queries: expandedVisibleRepositories.map(repository => ({
      queryKey: ['apiInterfaces', 'tree', repository.softwareRepositoryId, 'all'],
      queryFn: () => loadAllRepositoryInterfaces(repository.softwareRepositoryId),
      staleTime: 30_000,
    })),
  })
  const childrenByRepository = useMemo(() => {
    const result = new Map<
      string,
      {
        items: ApiInterfaceListItem[]
        loading: boolean
        failed: boolean
      }
    >()
    expandedVisibleRepositories.forEach((repository, index) => {
      const query = childQueries[index]
      result.set(repository.softwareRepositoryId, {
        items: listItems(query?.data) as ApiInterfaceListItem[],
        loading: Boolean(query?.isLoading),
        failed: Boolean(query?.isError),
      })
    })
    return result
  }, [childQueries, expandedVisibleRepositories])

  const totalInterfaces = repositories.reduce(
    (sum, repository) => sum + repository.interfaceCount,
    0,
  )

  function toggleExpanded(softwareRepositoryId: string) {
    setExpandedRepositories(previous => {
      const next = new Set(previous)
      if (next.has(softwareRepositoryId)) next.delete(softwareRepositoryId)
      else next.add(softwareRepositoryId)
      return next
    })
  }

  function handleRepositoryMain(repository: SoftwareRepository) {
    if (mode === 'detail') {
      toggleExpanded(repository.softwareRepositoryId)
      return
    }
    onSelectRepository(repository.softwareRepositoryId)
  }

  function groupKey(softwareRepositoryId: string, tag: string) {
    return `${softwareRepositoryId}\u0000${tag}`
  }

  function toggleGroup(softwareRepositoryId: string, tag: string) {
    const key = groupKey(softwareRepositoryId, tag)
    setCollapsedGroups(previous => {
      const next = new Set(previous)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <aside className={`if-app-tree${mode === 'detail' ? ' if-detail-app-tree' : ''}`}>
      <div className="if-app-tree-head">
        <div className="if-app-tree-title">
          <span>软件仓库</span>
          <span className="if-app-tree-total">{repositories.length}</span>
        </div>
      </div>
      <Input
        className="if-app-search"
        allowClear
        prefix={<SearchOutlined />}
        placeholder="搜索软件仓库"
        aria-label="搜索软件仓库"
        value={repositorySearch}
        onChange={event => setRepositorySearch(event.target.value)}
      />
      <div className="if-app-tree-scroll">
        <button
          type="button"
          className={`if-app-all${selectedSoftwareRepositoryId === 'all' && mode === 'list' ? ' is-active' : ''}`}
          onClick={onShowAll}
        >
          <span className="if-app-all-main">
            <AppstoreOutlined />
            <span>全部接口</span>
          </span>
          <span className="if-app-count">{totalInterfaces}</span>
        </button>

        {loading ? (
          <div className="if-app-tree-loading"><Spin size="small" /></div>
        ) : null}

        {!loading && !visibleRepositories.length ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={repositorySearch ? '没有匹配的软件仓库' : '还没有软件仓库'}
            className="if-app-tree-empty"
          />
        ) : null}

        {visibleRepositories.map(repository => {
          const expanded = expandedRepositories.has(repository.softwareRepositoryId)
          const selected =
            selectedSoftwareRepositoryId === repository.softwareRepositoryId
          const childState = childrenByRepository.get(repository.softwareRepositoryId)
          const groups = withEmptyGroups(
            groupItemsByTag(childState?.items ?? []),
            repository.interfaceGroups,
          )
          const groupNames = groups
            .map(group => group.tag)
            .filter(tag => tag !== UNTAGGED_GROUP)
          return (
            <div
              key={repository.softwareRepositoryId}
              className={`if-app-group${expanded ? ' is-expanded' : ''}${selected ? ' is-selected' : ''}`}
            >
              <div className="if-app-row">
                <button
                  type="button"
                  className="if-app-chevron"
                  aria-label={`${expanded ? '收起' : '展开'}${repository.name}`}
                  onClick={() => toggleExpanded(repository.softwareRepositoryId)}
                >
                  <DownOutlined />
                </button>
                <button
                  type="button"
                  className="if-app-main"
                  title={repository.name}
                  onClick={() => handleRepositoryMain(repository)}
                >
                  <span className="if-app-name">{repository.name}</span>
                  <span className="if-app-count">{repository.interfaceCount}</span>
                </button>
              </div>

              {expanded ? (
                <div className="if-app-children">
                  {childState?.loading ? (
                    <div className="if-app-tree-loading"><Spin size="small" /></div>
                  ) : null}
                  {childState?.failed ? (
                    <div className="if-app-children-note">接口加载失败</div>
                  ) : null}
                  {canManageInterfaces ? (
                    <button
                      type="button"
                      className="if-app-add-group"
                      onClick={() => onCreateGroup(repository)}
                    >
                      <PlusOutlined />
                      <span>新建分组</span>
                    </button>
                  ) : null}
                  {!childState?.loading && !childState?.failed && !groups.length ? (
                    <div className="if-app-children-note">还没有接口</div>
                  ) : null}
                  {groups.map(group => {
                    const collapsed = collapsedGroups.has(
                      groupKey(repository.softwareRepositoryId, group.tag),
                    )
                    return (
                      <div
                        className={`if-app-tag-group${collapsed ? ' is-collapsed' : ''}`}
                        key={group.tag}
                      >
                        <div className="if-app-tag-head" title={group.tag}>
                          <button
                            type="button"
                            className={`if-app-chevron if-app-tag-chevron${collapsed ? '' : ' is-expanded'}`}
                            aria-label={`${collapsed ? '展开' : '收起'}分组「${group.tag}」`}
                            onClick={() =>
                              toggleGroup(repository.softwareRepositoryId, group.tag)
                            }
                          >
                            <DownOutlined />
                          </button>
                          <span className="if-app-tag-name">{group.tag}</span>
                          <span className="if-app-tag-meta">
                            <span className="if-app-tag-count">{group.items.length}</span>
                            {canManageInterfaces && group.tag !== UNTAGGED_GROUP ? (
                              <Dropdown
                                trigger={['click']}
                                menu={{
                                  items: [
                                    { key: 'rename', label: '重命名分组' },
                                    { key: 'remove', label: '移除分组', danger: true },
                                  ],
                                  onClick: ({ key }) => {
                                    if (key === 'rename') onRenameGroup(repository, group)
                                    else onRemoveGroup(repository, group)
                                  },
                                }}
                              >
                                <Button
                                  type="text"
                                  size="small"
                                  className="if-app-tag-action"
                                  aria-label={`分组「${group.tag}」更多操作`}
                                  icon={<MoreOutlined />}
                                  onClick={event => event.stopPropagation()}
                                />
                              </Dropdown>
                            ) : null}
                          </span>
                        </div>
                        {collapsed ? null : group.items.length ? (
                          group.items.map(item => (
                            <div className="if-app-child-row" key={item.interfaceId}>
                              <button
                                type="button"
                                className={`if-app-child${item.interfaceId === selectedInterfaceId ? ' is-active' : ''}`}
                                title={`${item.name} ${item.path}`}
                                onClick={() => onOpenInterface(item.interfaceId)}
                              >
                                <Tag className={`if-method if-method-${methodTone(item.method)}`}>
                                  {item.method}
                                </Tag>
                                <span className="if-app-child-name">{item.name}</span>
                              </button>
                              {canManageInterfaces ? (
                                <Dropdown
                                  trigger={['click']}
                                  menu={{
                                    items: [{ key: 'move', label: '移动到分组…' }],
                                    onClick: () =>
                                      onMoveInterface(repository, item, groupNames),
                                  }}
                                >
                                  <Button
                                    type="text"
                                    size="small"
                                    className="if-app-child-action"
                                    aria-label={`${item.name} 更多操作`}
                                    icon={<MoreOutlined />}
                                    onClick={event => event.stopPropagation()}
                                  />
                                </Dropdown>
                              ) : null}
                            </div>
                          ))
                        ) : (
                          <div className="if-app-children-note">
                            该分组还没有接口，可从接口的「更多操作」移动进来
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
