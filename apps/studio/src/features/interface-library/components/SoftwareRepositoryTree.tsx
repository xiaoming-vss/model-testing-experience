import {
  AppstoreOutlined,
  DownOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  MoreOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import { useQueries } from '@tanstack/react-query'
import { Dropdown, Empty, Spin } from 'antd'
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { listItems, listTotal } from '@/services/api'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { SoftwareRepositoryTreeView } from '../hooks/useSoftwareRepositoryTreeView'
import type { ApiInterfaceListItem, SoftwareRepository } from '../types'
import {
  UNTAGGED_GROUP,
  groupItemsByTag,
  interfaceGroupKey,
  withEmptyGroups,
  type InterfaceGroup,
} from '../utils/interfaceGroups'

type Props = {
  /** Owned by the page: the tree unmounts while another interface loads and must come back as it was left. */
  view: SoftwareRepositoryTreeView
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

const METHOD_TEXT_TONE: Record<string, string> = {
  get: 'text-[var(--app-http-method-get)]',
  post: 'text-[var(--app-http-method-post)]',
  put: 'text-[var(--app-http-method-put)]',
  patch: 'text-[var(--app-http-method-patch)]',
  delete: 'text-[var(--app-http-method-delete)]',
}

function methodTextTone(method: string) {
  return METHOD_TEXT_TONE[method.toLowerCase()] ?? 'text-[var(--srf-text-secondary)]'
}

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
  view,
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
  const {
    collapsedRepositories,
    expandedGroups,
    scrollTopRef,
    toggleRepository,
    toggleGroup,
  } = view
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const scrollIdleTimerRef = useRef<number | null>(null)
  // The tree is rebuilt whenever another interface loads; put the list back where the user left it.
  useLayoutEffect(() => {
    if (scrollAreaRef.current) scrollAreaRef.current.scrollTop = scrollTopRef.current
  }, [scrollTopRef])
  useEffect(() => () => {
    if (scrollIdleTimerRef.current !== null) {
      window.clearTimeout(scrollIdleTimerRef.current)
    }
  }, [])

  function handleTreeScroll(event: React.UIEvent<HTMLDivElement>) {
    scrollTopRef.current = event.currentTarget.scrollTop
    const node = event.currentTarget
    node.dataset.scrolling = 'true'
    if (scrollIdleTimerRef.current !== null) {
      window.clearTimeout(scrollIdleTimerRef.current)
    }
    scrollIdleTimerRef.current = window.setTimeout(() => {
      delete node.dataset.scrolling
      scrollIdleTimerRef.current = null
    }, 900)
  }

  const expandedRepositories = useMemo(
    () =>
      repositories.filter(
        repository =>
          !collapsedRepositories.has(repository.softwareRepositoryId),
      ),
    [collapsedRepositories, repositories],
  )
  const childQueries = useQueries({
    queries: expandedRepositories.map(repository => ({
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
    expandedRepositories.forEach((repository, index) => {
      const query = childQueries[index]
      result.set(repository.softwareRepositoryId, {
        items: listItems(query?.data) as ApiInterfaceListItem[],
        loading: Boolean(query?.isLoading),
        failed: Boolean(query?.isError),
      })
    })
    return result
  }, [childQueries, expandedRepositories])

  const totalInterfaces = repositories.reduce(
    (sum, repository) => sum + repository.interfaceCount,
    0,
  )

  function handleRepositoryMain(repository: SoftwareRepository) {
    if (mode === 'detail') {
      toggleRepository(repository.softwareRepositoryId)
      return
    }
    onSelectRepository(repository.softwareRepositoryId)
  }

  const treeClassName = mode === 'detail'
    ? 'if-app-tree if-detail-app-tree flex flex-[0_0_var(--app-sidebar-width)] flex-col min-h-0 max-w-[var(--app-sidebar-width)] rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-3 max-[960.01px]:hidden'
    : 'if-app-tree flex flex-[0_0_var(--app-sidebar-width)] flex-col min-h-0 border-r border-[var(--srf-card-border)] bg-[color-mix(in_srgb,var(--srf-card)_94%,var(--srf-hover))] p-[14px_12px] max-[760.01px]:flex-none max-[760.01px]:max-h-[220px] max-[760.01px]:border-r-0 max-[760.01px]:border-b max-[760.01px]:border-b-[var(--srf-card-border)]'
  // A sticky group header must paint the same surface as the rail behind it.
  const treeSurfaceClass = mode === 'detail'
    ? 'bg-[var(--srf-card)]'
    : 'bg-[color-mix(in_srgb,var(--srf-card)_94%,var(--srf-hover))]'

  return (
    <aside className={treeClassName}>
      <div className="if-app-tree-head flex min-h-6 items-center justify-between gap-2 text-[12px] font-semibold text-[var(--srf-text-secondary)]">
        <div className="if-app-tree-title inline-flex min-w-0 items-center gap-1.5">
          <FolderOpenOutlined className="text-[var(--srf-accent)]" aria-hidden />
          <span>接口导航</span>
        </div>
        <span className="if-app-tree-total flex-none text-[10px] font-normal tabular-nums text-[var(--srf-text-muted)]">{repositories.length} 个仓库</span>
      </div>
      <div
        ref={scrollAreaRef}
        className={`if-app-tree-scroll app-scrollbar-overlay -mr-3 mt-1.5 flex min-h-0 flex-auto flex-col overflow-auto pr-[14px] max-[760.01px]:max-h-[150px]`}
        onScroll={handleTreeScroll}
      >
        <button
          type="button"
          className={`if-app-all mb-0.5 flex h-8 w-full cursor-pointer items-center justify-between rounded-[6px] border-0 px-2 py-0 text-left font-[inherit] text-[12.5px] ${selectedSoftwareRepositoryId === 'all' && mode === 'list' ? ' is-active bg-[var(--srf-accent-soft)] font-semibold text-[var(--srf-accent-strong)]' : ' bg-transparent text-[var(--srf-text-secondary)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)]'}`}
          onClick={onShowAll}
        >
          <span className="if-app-all-main inline-flex min-w-0 items-center gap-2">
            <AppstoreOutlined />
            <span>全部接口</span>
          </span>
          <span className={`if-app-count flex-none text-[10.5px] font-normal tabular-nums ${selectedSoftwareRepositoryId === 'all' && mode === 'list' ? ' text-[var(--srf-accent-strong)]' : ' text-[var(--srf-text-muted)]'}`}>{totalInterfaces}</span>
        </button>

        {loading ? (
          <div className="if-app-tree-loading grid place-items-center py-2.5"><Spin size="small" /></div>
        ) : null}

        {!loading && !repositories.length ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="还没有软件仓库"
            className="if-app-tree-empty my-3"
          />
        ) : null}

        {repositories.map(repository => {
          const expanded = !collapsedRepositories.has(
            repository.softwareRepositoryId,
          )
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
          const selectedRow = selected && mode === 'list'
          return (
            <div
              key={repository.softwareRepositoryId}
              className={`if-app-group flex min-w-0 flex-col ${expanded ? ' is-expanded' : ''} ${selected ? ' is-selected' : ''}`}
            >
              <div className={`if-app-row mb-[3px] flex min-w-0 items-center gap-0.5 rounded-[var(--srf-radius-control)] border-b border-[color-mix(in_srgb,var(--srf-card-border)_72%,transparent)] py-0.5 pl-[7px] pr-0.5 ${selectedRow ? ' bg-[var(--srf-accent-soft)]' : ' hover:bg-[var(--srf-hover)] focus-within:bg-[var(--srf-hover)]'}`}>
                <button
                  type="button"
                  className={`if-app-main flex h-7 min-w-0 flex-auto cursor-pointer items-center gap-1.5 border-0 bg-transparent text-left font-[inherit] text-[13px] font-semibold ${selected ? ' text-[var(--srf-accent-strong)]' : ' text-[var(--srf-text)]'}`}
                  title={repository.name}
                  aria-expanded={mode === 'detail' ? expanded : undefined}
                  onClick={() => handleRepositoryMain(repository)}
                >
                  {expanded
                    ? <FolderOpenOutlined className="flex-none text-[14px] text-[var(--srf-text-muted)]" aria-hidden />
                    : <FolderOutlined className="flex-none text-[14px] text-[var(--srf-text-muted)]" aria-hidden />}
                  <span className="if-app-name min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">{repository.name}</span>
                  <span className="if-app-count flex-none text-[10.5px] font-normal tabular-nums text-[var(--srf-text-muted)]">{repository.interfaceCount}</span>
                </button>
                {canManageInterfaces ? (
                  <button
                    type="button"
                    className="if-app-add-group inline-grid h-[22px] w-[22px] flex-none cursor-pointer place-items-center rounded-[5px] border-0 bg-transparent p-0 text-[var(--srf-text-muted)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)] focus-visible:bg-[var(--srf-hover)] focus-visible:text-[var(--srf-text)]"
                    aria-label="新建分组"
                    title="新建分组"
                    onClick={() => onCreateGroup(repository)}
                  >
                    <PlusOutlined />
                  </button>
                ) : null}
                <button
                  type="button"
                  className="if-app-chevron inline-grid h-[22px] w-[22px] flex-none cursor-pointer place-items-center rounded-[5px] border-0 bg-transparent p-0 text-[10px] text-[var(--srf-text-muted)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)]"
                  aria-label={`${expanded ? '收起' : '展开'}${repository.name}`}
                  aria-expanded={expanded}
                  onClick={() => toggleRepository(repository.softwareRepositoryId)}
                >
                  <DownOutlined className={`transition-transform duration-[120ms] ${expanded ? 'rotate-0' : '-rotate-90'}`} />
                </button>
              </div>

              {expanded ? (
                <div className="if-app-children flex min-w-0 flex-col pb-[5px]">
                  {childState?.loading ? (
                    <div className="if-app-tree-loading grid place-items-center py-2.5"><Spin size="small" /></div>
                  ) : null}
                  {childState?.failed ? (
                    <div className="if-app-children-note px-1.5 py-[3px] text-[11px] leading-[18px] text-[var(--srf-text-muted)]">接口加载失败</div>
                  ) : null}
                  {!childState?.loading && !childState?.failed && !groups.length ? (
                    <div className="if-app-children-note px-1.5 py-[3px] text-[11px] leading-[18px] text-[var(--srf-text-muted)]">还没有接口</div>
                  ) : null}
                  {groups.map(group => {
                    const collapsed = !expandedGroups.has(
                      interfaceGroupKey(repository.softwareRepositoryId, group.tag),
                    )
                    const canManageGroup =
                      canManageInterfaces && group.tag !== UNTAGGED_GROUP
                    return (
                      <div
                        className={`if-app-tag-group flex min-w-0 flex-col [&+&]:mt-[3px] ${collapsed ? ' is-collapsed' : ''}`}
                        key={group.tag}
                      >
                        <div className={`if-app-tag-head group sticky top-0 z-[2] flex h-[27px] min-w-0 items-center gap-0.5 rounded-[5px] ${treeSurfaceClass} px-1 text-[var(--srf-text-secondary)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)]`} title={group.tag}>
                          <button
                            type="button"
                            className="if-app-tag-chevron flex h-full min-w-0 flex-auto cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-left font-[inherit] text-[11.5px] font-semibold tracking-[0.01em]"
                            aria-label={`${collapsed ? '展开' : '收起'}分组「${group.tag}」`}
                            aria-expanded={!collapsed}
                            onClick={() =>
                              toggleGroup(repository.softwareRepositoryId, group.tag)
                            }
                          >
                            <DownOutlined className={`flex-[0_0_12px] text-[10px] text-[var(--srf-text-muted)] transition-transform duration-[120ms] ${collapsed ? '-rotate-90' : 'rotate-0'}`} />
                            <span className="if-app-tag-name min-w-0 flex-auto overflow-hidden text-ellipsis whitespace-nowrap">{group.tag}</span>
                          </button>
                          <span className={`if-app-tag-count flex-none text-[10.5px] font-normal tabular-nums text-[var(--srf-text-muted)] ${canManageGroup ? ' transition-opacity duration-[100ms] group-hover:opacity-0 group-focus-within:opacity-0' : ''}`}>{group.items.length}</span>
                          {canManageGroup ? (
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
                              <button
                                type="button"
                                className="if-app-tag-action absolute right-1 top-1/2 inline-grid h-5 w-5 -translate-y-1/2 cursor-pointer place-items-center rounded-[4px] border-0 bg-transparent p-0 text-[var(--srf-text-muted)] opacity-0 hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)] group-hover:opacity-100 group-focus-within:opacity-100"
                                aria-label={`分组「${group.tag}」更多操作`}
                                onClick={event => event.stopPropagation()}
                              >
                                <MoreOutlined />
                              </button>
                            </Dropdown>
                          ) : null}
                        </div>
                        {collapsed ? null : group.items.length ? (
                          <div className="flex min-w-0 flex-col gap-px pb-[5px] pt-px">
                            {group.items.map(item => {
                              const methodTone = methodTextTone(item.method)
                              return (
                                <div className="if-app-child-row group relative flex min-w-0 items-center" key={item.interfaceId}>
                                  <button
                                    type="button"
                                    className={`if-app-child flex h-[30px] min-w-0 flex-auto cursor-pointer items-center gap-2 rounded-[6px] border-0 py-0 pl-2 pr-1.5 text-left font-[inherit] text-[13px] ${item.interfaceId === selectedInterfaceId ? ' is-active bg-[var(--srf-accent-soft)] font-semibold text-[var(--srf-accent-strong)] shadow-[inset_2px_0_0_var(--srf-accent)]' : ' bg-transparent text-[var(--srf-text-secondary)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)]'}`}
                                    title={`${item.name} ${item.path}`}
                                    onClick={() => onOpenInterface(item.interfaceId)}
                                  >
                                    <span className={`if-app-method w-[42px] flex-[0_0_42px] shrink-0 font-[ui-monospace,SFMono-Regular,Menlo,Consolas,monospace] text-[10px] font-bold tracking-[0.02em] ${methodTone}`}>{item.method}</span>
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
                                      <button
                                        type="button"
                                        className="if-app-child-action absolute right-0.5 top-1/2 inline-grid h-5 w-5 -translate-y-1/2 cursor-pointer place-items-center rounded-[4px] border-0 bg-transparent p-0 text-[var(--srf-text-muted)] opacity-0 hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)] group-hover:opacity-100 group-focus-within:opacity-100"
                                        aria-label={`${item.name} 更多操作`}
                                        onClick={event => event.stopPropagation()}
                                      >
                                        <MoreOutlined />
                                      </button>
                                    </Dropdown>
                                  ) : null}
                                </div>
                              )
                            })}
                          </div>
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
