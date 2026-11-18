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

  const treeClassName = mode === 'detail'
    ? 'if-app-tree if-detail-app-tree flex flex-[0_0_var(--app-sidebar-width)] flex-col min-h-0 max-w-[var(--app-sidebar-width)] rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-3 max-[960.01px]:hidden'
    : 'if-app-tree flex flex-[0_0_var(--app-sidebar-width)] flex-col min-h-0 border-r border-[var(--srf-card-border)] bg-[color-mix(in_srgb,var(--srf-card)_94%,var(--srf-hover))] p-[14px_12px] max-[760.01px]:flex-none max-[760.01px]:max-h-[220px] max-[760.01px]:border-r-0 max-[760.01px]:border-b max-[760.01px]:border-b-[var(--srf-card-border)]'

  return (
    <aside className={treeClassName}>
      <div className="if-app-tree-head flex min-h-6 items-center justify-between gap-2 text-[12px] font-semibold text-[var(--srf-text-secondary)]">
        <div className="if-app-tree-title inline-flex min-w-0 items-center gap-1.5">
          <span>软件仓库</span>
          <span className="if-app-tree-total min-w-5 rounded-full bg-[var(--srf-chip)] px-1.5 text-center text-[10px] leading-[18px] text-[var(--srf-text-secondary)]">{repositories.length}</span>
        </div>
      </div>
      <Input
        className="if-app-search mt-2.5 mb-2"
        allowClear
        prefix={<SearchOutlined />}
        placeholder="搜索软件仓库"
        aria-label="搜索软件仓库"
        value={repositorySearch}
        onChange={event => setRepositorySearch(event.target.value)}
      />
      <div className="if-app-tree-scroll mt-0.5 flex min-h-0 flex-auto flex-col gap-0.5 overflow-auto max-[760.01px]:max-h-[150px]">
        <button
          type="button"
          className={`if-app-all flex min-h-[34px] w-full cursor-pointer items-center justify-between rounded-[var(--srf-radius-control)] border-0 px-[9px] py-1.5 text-left font-[inherit] text-[13px] ${selectedSoftwareRepositoryId === 'all' && mode === 'list' ? ' is-active bg-[var(--srf-accent-soft)] font-semibold text-[var(--srf-accent-strong)]' : ' bg-transparent text-[var(--srf-text-secondary)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)]'}`}
          onClick={onShowAll}
        >
          <span className="if-app-all-main inline-flex min-w-0 items-center gap-2">
            <AppstoreOutlined />
            <span>全部接口</span>
          </span>
          <span className={`if-app-count min-w-[22px] flex-none rounded-full px-1.5 text-center text-[11px] leading-[18px] ${selectedSoftwareRepositoryId === 'all' && mode === 'list' ? ' bg-[var(--srf-count-badge)] text-[var(--srf-accent-strong)]' : ' bg-[var(--srf-chip)] text-[var(--srf-text-secondary)]'}`}>{totalInterfaces}</span>
        </button>

        {loading ? (
          <div className="if-app-tree-loading grid place-items-center py-2.5"><Spin size="small" /></div>
        ) : null}

        {!loading && !visibleRepositories.length ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={repositorySearch ? '没有匹配的软件仓库' : '还没有软件仓库'}
            className="if-app-tree-empty my-3"
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
              className={`if-app-group flex min-w-0 flex-col rounded-[var(--srf-radius-control)] ${expanded ? ' is-expanded' : ''} ${selected ? ' is-selected' : ''}`}
            >
              <div className={`if-app-row flex min-w-0 items-center gap-px rounded-[var(--srf-radius-control)] px-0.5 ${selected ? ' bg-[var(--srf-accent-soft)]' : ' hover:bg-[var(--srf-hover)] focus-within:bg-[var(--srf-hover)]'}`}>
                <button
                  type="button"
                  className={`if-app-chevron inline-grid h-7 w-5 flex-[0_0_20px] cursor-pointer place-items-center border-0 bg-transparent p-0 text-[10px] text-[var(--srf-text-muted)] transition-transform duration-[120ms] ${expanded ? ' rotate-0' : ' -rotate-90'}`}
                  aria-label={` ${expanded ? '收起' : '展开'}${repository.name}`}
                  onClick={() => toggleExpanded(repository.softwareRepositoryId)}
                >
                  <DownOutlined />
                </button>
                <button
                  type="button"
                  className={`if-app-main flex min-h-8 min-w-0 flex-auto cursor-pointer items-center justify-between gap-2 border-0 bg-transparent px-[3px] py-1 text-left font-[inherit] text-[13px] ${selected ? ' font-semibold text-[var(--srf-accent-strong)]' : ' text-[var(--srf-text-secondary)]'}`}
                  title={repository.name}
                  onClick={() => handleRepositoryMain(repository)}
                >
                  <span className="if-app-name inline-flex min-w-0 items-center gap-1.5 overflow-hidden text-ellipsis whitespace-nowrap">{repository.name}</span>
                  <span className={`if-app-count min-w-[22px] flex-none rounded-full px-1.5 text-center text-[11px] leading-[18px] ${selected ? ' bg-[var(--srf-count-badge)] text-[var(--srf-accent-strong)]' : ' bg-[var(--srf-chip)] text-[var(--srf-text-secondary)]'}`}>{repository.interfaceCount}</span>
                </button>
              </div>

              {expanded ? (
                <div className="if-app-children mb-[5px] ml-5 mt-px flex min-w-0 flex-col gap-px border-l border-[var(--srf-divider)] pl-[7px]">
                  {childState?.loading ? (
                    <div className="if-app-tree-loading grid place-items-center py-2.5"><Spin size="small" /></div>
                  ) : null}
                  {childState?.failed ? (
                    <div className="if-app-children-note px-1.5 py-[3px] text-[11px] leading-[18px] text-[var(--srf-text-muted)]">接口加载失败</div>
                  ) : null}
                  {canManageInterfaces ? (
                    <button
                      type="button"
                      className="if-app-add-group flex min-h-[26px] cursor-pointer items-center gap-1.5 self-start rounded-[var(--srf-radius-control)] border-0 bg-transparent px-1.5 py-[3px] font-[inherit] text-[11px] text-[var(--srf-text-muted)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-accent-strong)] focus-visible:bg-[var(--srf-hover)] focus-visible:text-[var(--srf-accent-strong)]"
                      onClick={() => onCreateGroup(repository)}
                    >
                      <PlusOutlined />
                      <span>新建分组</span>
                    </button>
                  ) : null}
                  {!childState?.loading && !childState?.failed && !groups.length ? (
                    <div className="if-app-children-note px-1.5 py-[3px] text-[11px] leading-[18px] text-[var(--srf-text-muted)]">还没有接口</div>
                  ) : null}
                  {groups.map(group => {
                    const collapsed = collapsedGroups.has(
                      groupKey(repository.softwareRepositoryId, group.tag),
                    )
                    return (
                      <div
                        className={`if-app-tag-group flex min-w-0 flex-col gap-px [&+&]:mt-[5px] ${collapsed ? ' is-collapsed' : ''}`}
                        key={group.tag}
                      >
                        <div className="if-app-tag-head group flex items-center justify-between gap-1.5 px-1.5 pb-0.5 pt-1 text-[10px] font-semibold tracking-[0.02em] text-[var(--srf-text-muted)]" title={group.tag}>
                          <button
                            type="button"
                            className={`if-app-chevron if-app-tag-chevron inline-grid h-[18px] w-4 flex-[0_0_16px] cursor-pointer place-items-center border-0 bg-transparent p-0 text-[8px] text-[var(--srf-text-muted)] transition-transform duration-[120ms] ${collapsed ? ' -rotate-90' : ' is-expanded rotate-0'}`}
                            aria-label={` ${collapsed ? '展开' : '收起'}分组「${group.tag}」`}
                            onClick={() =>
                              toggleGroup(repository.softwareRepositoryId, group.tag)
                            }
                          >
                            <DownOutlined />
                          </button>
                          <span className="if-app-tag-name min-w-0 flex-auto overflow-hidden text-ellipsis whitespace-nowrap">{group.tag}</span>
                          <span className="if-app-tag-meta flex items-center gap-0.5">
                            <span className="if-app-tag-count flex-none font-normal">{group.items.length}</span>
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
                                  className="if-app-tag-action opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
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
                            <div className="if-app-child-row group flex min-w-0 items-center gap-0.5" key={item.interfaceId}>
                              <button
                                type="button"
                                className={`if-app-child flex min-h-[26px] min-w-0 flex-auto cursor-pointer items-center gap-1.5 rounded-[var(--srf-radius-control)] border-0 px-1.5 py-[3px] text-left font-[inherit] text-[12px] ${item.interfaceId === selectedInterfaceId ? ' is-active bg-[var(--srf-accent-soft)] text-[var(--srf-accent-strong)]' : ' bg-transparent text-[var(--srf-text-secondary)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)]'}`}
                                title={`${item.name} ${item.path}`}
                                onClick={() => onOpenInterface(item.interfaceId)}
                              >
                                <Tag className={`if-method if-method-${methodTone(item.method)}`}>
                                  {item.method}
                                </Tag>
                                <span className="if-app-child-name min-w-0 flex-auto overflow-hidden text-ellipsis whitespace-nowrap">{item.name}</span>
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
                                    className="if-app-child-action flex-none opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
                                    aria-label={`${item.name} 更多操作`}
                                    icon={<MoreOutlined />}
                                    onClick={event => event.stopPropagation()}
                                  />
                                </Dropdown>
                              ) : null}
                            </div>
                          ))
                        ) : (
                          <div className="if-app-children-note px-1.5 py-[3px] text-[11px] leading-[18px] text-[var(--srf-text-muted)]">
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
