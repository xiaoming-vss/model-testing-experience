import {
  AppstoreOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useQueries } from '@tanstack/react-query'
import { Button, Empty, Input, Spin, Switch, Tag, Tooltip } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { listItems, listTotal } from '@/services/api'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiApp, ApiInterfaceListItem } from '../types'
import { methodTone } from '../utils/interfaceForm'

type Props = {
  apps: ApiApp[]
  loading?: boolean
  selectedAppId: string
  selectedInterfaceId?: string
  mode: 'list' | 'detail'
  canManageApps: boolean
  onSelectApp: (appId: string) => void
  onShowAll: () => void
  onOpenInterface: (interfaceId: string) => void
  onCreateApp: () => void
  onEditApp: (app: ApiApp) => void
  onToggleApp: (app: ApiApp) => void
  onDeleteApp: (app: ApiApp) => void
}

const CHILD_PREVIEW_LIMIT = 10
const ALL_PAGE_SIZE = 200
const ALL_MAX_PAGES = 50

async function loadAllAppInterfaces(appId: string) {
  const all: ApiInterfaceListItem[] = []
  let total: number
  let page = 1
  do {
    const response = await interfaceLibraryApi.getAppApiInterfaces(appId, {
      page,
      pageSize: ALL_PAGE_SIZE,
    })
    const items = listItems(response) as ApiInterfaceListItem[]
    all.push(...items)
    total = listTotal(response) || all.length
    if (!items.length) break
    page += 1
  } while (all.length < total && page <= ALL_MAX_PAGES)
  return Object.assign(all, { items: all, total })
}

/** 接口库左侧应用树：应用即分组，展开后直接进入应用内接口。 */
export function InterfaceAppTree({
  apps,
  loading = false,
  selectedAppId,
  selectedInterfaceId,
  mode,
  canManageApps,
  onSelectApp,
  onShowAll,
  onOpenInterface,
  onCreateApp,
  onEditApp,
  onToggleApp,
  onDeleteApp,
}: Props) {
  const [appSearch, setAppSearch] = useState('')
  const [showDisabledApps, setShowDisabledApps] = useState(true)
  const [expandedApps, setExpandedApps] = useState<Set<string>>(
    () => new Set(selectedAppId !== 'all' ? [selectedAppId] : []),
  )
  const [showAllApps, setShowAllApps] = useState<Set<string>>(() => new Set())

  useEffect(() => {
    if (selectedAppId === 'all') return
    setExpandedApps(previous => {
      if (previous.has(selectedAppId)) return previous
      const next = new Set(previous)
      next.add(selectedAppId)
      return next
    })
  }, [selectedAppId])

  const visibleApps = useMemo(() => {
    const keyword = appSearch.trim().toLowerCase()
    return apps.filter(app => {
      if (!showDisabledApps && !app.enabled && app.appId !== selectedAppId) return false
      if (!keyword) return true
      return app.name.toLowerCase().includes(keyword) ||
        app.repository?.path.toLowerCase().includes(keyword)
    })
  }, [appSearch, apps, selectedAppId, showDisabledApps])

  const expandedVisibleApps = useMemo(
    () => visibleApps.filter(app => expandedApps.has(app.appId)),
    [expandedApps, visibleApps],
  )
  const childQueries = useQueries({
    queries: expandedVisibleApps.map(app => {
      const showAll = showAllApps.has(app.appId)
      return {
        queryKey: ['apiInterfaces', 'tree', app.appId, showAll ? 'all' : 'preview'],
        queryFn: () =>
          showAll
            ? loadAllAppInterfaces(app.appId)
            : interfaceLibraryApi.getAppApiInterfaces(app.appId, { page: 1, pageSize: 100 }),
        staleTime: 30_000,
      }
    }),
  })
  const childrenByApp = useMemo(() => {
    const result = new Map<string, {
      items: ApiInterfaceListItem[]
      total: number
      loading: boolean
      failed: boolean
    }>()
    expandedVisibleApps.forEach((app, index) => {
      const query = childQueries[index]
      result.set(app.appId, {
        items: listItems(query?.data) as ApiInterfaceListItem[],
        total: listTotal(query?.data) || app.interfaceCount,
        loading: Boolean(query?.isLoading),
        failed: Boolean(query?.isError),
      })
    })
    return result
  }, [childQueries, expandedVisibleApps])

  const totalInterfaces = apps.reduce((sum, app) => sum + app.interfaceCount, 0)

  function toggleExpanded(appId: string) {
    setExpandedApps(previous => {
      const next = new Set(previous)
      if (next.has(appId)) next.delete(appId)
      else next.add(appId)
      return next
    })
  }

  function handleAppMain(app: ApiApp) {
    if (mode === 'detail') {
      toggleExpanded(app.appId)
      return
    }
    onSelectApp(app.appId)
  }

  return (
    <aside className={`if-app-tree${mode === 'detail' ? ' if-detail-app-tree' : ''}`}>
      <div className="if-app-tree-head">
        <div className="if-app-tree-title">
          <span>应用</span>
          <span className="if-app-tree-total">{apps.length}</span>
        </div>
        {canManageApps ? (
          <Tooltip title="新建应用">
            <Button
              type="text"
              size="small"
              aria-label="新建应用"
              icon={<PlusOutlined />}
              onClick={onCreateApp}
            />
          </Tooltip>
        ) : null}
      </div>
      <Input
        className="if-app-search"
        allowClear
        prefix={<SearchOutlined />}
        placeholder="搜索应用"
        aria-label="搜索应用"
        value={appSearch}
        onChange={event => setAppSearch(event.target.value)}
      />
      <div className="if-app-tree-scroll">
        <button
          type="button"
          className={`if-app-all${selectedAppId === 'all' && mode === 'list' ? ' is-active' : ''}`}
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

        {!loading && !visibleApps.length ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={appSearch ? '没有匹配的应用' : '还没有接口应用'}
            className="if-app-tree-empty"
          />
        ) : null}

        {visibleApps.map(app => {
          const expanded = expandedApps.has(app.appId)
          const selected = selectedAppId === app.appId
          const childState = childrenByApp.get(app.appId)
          const showAll = showAllApps.has(app.appId)
          const children = childState?.items.slice(
            0,
            showAll ? Number.POSITIVE_INFINITY : CHILD_PREVIEW_LIMIT,
          ) ?? []
          const rest = Math.max((childState?.total ?? app.interfaceCount) - children.length, 0)
          return (
            <div
              key={app.appId}
              className={`if-app-group${expanded ? ' is-expanded' : ''}${selected ? ' is-selected' : ''}${app.enabled ? '' : ' is-off'}`}
            >
              <div className="if-app-row">
                <button
                  type="button"
                  className="if-app-chevron"
                  aria-label={`${expanded ? '收起' : '展开'}${app.name}`}
                  onClick={() => toggleExpanded(app.appId)}
                >
                  <DownOutlined />
                </button>
                <button
                  type="button"
                  className="if-app-main"
                  title={`${app.name}${app.enabled ? '' : '（已停用）'}`}
                  onClick={() => handleAppMain(app)}
                >
                  <span className="if-app-name">
                    {app.name}
                    {app.enabled ? null : <em>停用</em>}
                  </span>
                  <span className="if-app-count">{app.interfaceCount}</span>
                </button>
                {canManageApps ? (
                  <div className="if-app-actions">
                    <Tooltip title="编辑应用">
                      <Button
                        type="text"
                        size="small"
                        aria-label={`编辑${app.name}`}
                        icon={<EditOutlined />}
                        onClick={() => onEditApp(app)}
                      />
                    </Tooltip>
                    <Tooltip title={app.enabled ? '停用应用' : '启用应用'}>
                      <Button
                        type="text"
                        size="small"
                        aria-label={`${app.enabled ? '停用' : '启用'}${app.name}`}
                        icon={<ReloadOutlined />}
                        onClick={() => onToggleApp(app)}
                      />
                    </Tooltip>
                    <Tooltip title={app.interfaceCount > 0 ? '先删除该应用下的接口' : '删除应用'}>
                      <Button
                        type="text"
                        size="small"
                        danger
                        disabled={app.interfaceCount > 0}
                        aria-label={`删除${app.name}`}
                        icon={<DeleteOutlined />}
                        onClick={() => onDeleteApp(app)}
                      />
                    </Tooltip>
                  </div>
                ) : null}
              </div>

              {expanded ? (
                <div className="if-app-children">
                  {childState?.loading ? (
                    <div className="if-app-tree-loading"><Spin size="small" /></div>
                  ) : null}
                  {childState?.failed ? (
                    <div className="if-app-children-note">接口加载失败</div>
                  ) : null}
                  {!childState?.loading && !childState?.failed && children.length === 0 ? (
                    <div className="if-app-children-note">还没有接口</div>
                  ) : null}
                  {children.map(item => (
                    <button
                      key={item.interfaceId}
                      type="button"
                      className={`if-app-child${item.interfaceId === selectedInterfaceId ? ' is-active' : ''}${item.enabled ? '' : ' is-off'}`}
                      title={`${item.name} ${item.path}`}
                      onClick={() => onOpenInterface(item.interfaceId)}
                    >
                      <Tag className={`if-method if-method-${methodTone(item.method)}`}>
                        {item.method}
                      </Tag>
                      <span className="if-app-child-name">{item.name}</span>
                      {item.enabled ? null : <em>停用</em>}
                    </button>
                  ))}
                  {rest > 0 && !childState?.loading ? (
                    <button
                      type="button"
                      className="if-app-tree-more"
                      onClick={() =>
                        setShowAllApps(previous => {
                          const next = new Set(previous)
                          next.add(app.appId)
                          return next
                        })
                      }
                    >
                      查看其余 {rest} 个接口
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
      <label className="if-app-disabled-toggle">
        <Switch size="small" checked={showDisabledApps} onChange={setShowDisabledApps} />
        显示停用应用
      </label>
    </aside>
  )
}
