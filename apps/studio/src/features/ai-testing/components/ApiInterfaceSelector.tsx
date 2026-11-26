import { Alert, Button, Select, Tag } from 'antd'
import { useQueries, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import type {
  ApiInterfaceListItem,
  RequirementSoftwareRepository,
} from '@/features/interface-library/types'
import type { ListResponse } from '@/shared/api/request'
import { listItems, listTotal } from '@/services/api'
import { getErrorMessage } from '@/utils/format'

type Props = {
  projectId: string
  requirementId?: string
  value?: string[]
  onChange?: (interfaceIds: string[]) => void
  disabled?: boolean
  /** 仓库画像建议的后端仓库；只作为默认筛选范围，不限制其他软件仓库。 */
  suggestedRepositories?: ApiSuggestedRepository[]
}

/** 仓库画像给出的接口范围建议，只携带选择器需要的公开标识。 */
export type ApiSuggestedRepository = {
  /** 仓库画像中的 GitLab 仓库项目 ID；不是平台软件仓库 UUID。 */
  gitRepositoryId: string
  pathWithNamespace?: string
}

type SelectorScope = 'suggested' | 'requirement' | 'project'

const PAGE_SIZE = 100

/** 接口可能超过单页上限：读完第 1 页的 total 再取剩余页，「全选」才覆盖全部结果。 */
async function fetchAllInterfaces(
  fetchPage: (page: number) => Promise<ListResponse<ApiInterfaceListItem>>,
): Promise<ApiInterfaceListItem[]> {
  const first = await fetchPage(1)
  const remaining = Math.ceil(listTotal(first) / PAGE_SIZE) - 1
  const rest = await Promise.all(
    Array.from({ length: remaining }, (_, index) => fetchPage(index + 2)),
  )
  return [first, ...rest].flatMap(page => listItems(page))
}

/** API 用例生成的接口选择器：默认使用画像建议或需求关联的软件仓库，可切换到项目全部接口。 */
export function ApiInterfaceSelector({
  projectId,
  requirementId,
  value = [],
  onChange = () => {},
  disabled = false,
  suggestedRepositories = [],
}: Props) {
  const [keyword, setKeyword] = useState('')
  const [scope, setScope] = useState<SelectorScope>()
  const [repositoryFilter, setRepositoryFilter] = useState<string>()
  const [tagFilter, setTagFilter] = useState<string>()

  const bindingsQuery = useQuery({
    queryKey: ['requirementSoftwareRepositories', requirementId],
    queryFn: () =>
      interfaceLibraryApi.getRequirementSoftwareRepositories(requirementId!),
    enabled: Boolean(requirementId),
  })
  const bindings = useMemo(
    () => listItems(bindingsQuery.data) as RequirementSoftwareRepository[],
    [bindingsQuery.data],
  )
  // 画像产物中的 repositoryId 是 GitLab 项目 ID；接口查询需要需求关联上的软件仓库 UUID。
  const suggestedRepositoryIds = useMemo(() => {
    if (!suggestedRepositories.length) return []
    const softwareRepositoryByGitlabId = new Map(
      bindings
        .filter(binding => binding.repository?.projectId)
        .map(binding => [binding.repository!.projectId, binding.softwareRepositoryId]),
    )
    return [
      ...new Set(
        suggestedRepositories
          .map(item => softwareRepositoryByGitlabId.get(item.gitRepositoryId) ?? '')
          .filter(Boolean),
      ),
    ]
  }, [bindings, suggestedRepositories])
  const scopedRepositoryIds = useMemo(
    () => bindings.map(binding => binding.softwareRepositoryId),
    [bindings],
  )
  const requirementScopeReady = bindingsQuery.isSuccess || bindingsQuery.isError
  const effectiveScope: SelectorScope =
    scope && (scope !== 'suggested' || suggestedRepositoryIds.length)
      ? scope
      : suggestedRepositoryIds.length
        ? 'suggested'
        : 'requirement'
  const activeRepositoryIds = useMemo(() => {
    if (effectiveScope === 'suggested') return suggestedRepositoryIds
    if (effectiveScope === 'requirement' && requirementScopeReady)
      return scopedRepositoryIds
    return []
  }, [
    effectiveScope,
    requirementScopeReady,
    scopedRepositoryIds,
    suggestedRepositoryIds,
  ])
  const useAllRepositories =
    effectiveScope === 'project' ||
    (effectiveScope === 'requirement' &&
      (requirementId
        ? requirementScopeReady && scopedRepositoryIds.length === 0
        : true))

  const repositoryQueries = useQueries({
    queries: useAllRepositories
      ? []
      : activeRepositoryIds.map(softwareRepositoryId => ({
          queryKey: [
            'apiInterfaces',
            'selector',
            softwareRepositoryId,
            keyword,
          ],
          queryFn: () => fetchAllInterfaces(page => interfaceLibraryApi.getSoftwareRepositoryApiInterfaces(softwareRepositoryId, { keyword, page, pageSize: PAGE_SIZE })),
          enabled: !disabled,
        })),
  })
  const projectQuery = useQuery({
    queryKey: ['apiInterfaces', 'selector', 'project', projectId, keyword],
    queryFn: () => fetchAllInterfaces(page => interfaceLibraryApi.getProjectApiInterfaces(projectId, { keyword, page, pageSize: PAGE_SIZE })),
    enabled: !disabled && useAllRepositories && Boolean(projectId),
  })

  const interfaces = useMemo(() => {
    const rows = useAllRepositories
      ? listItems(projectQuery.data)
      : repositoryQueries.flatMap(query => listItems(query.data))
    return rows as ApiInterfaceListItem[]
  }, [projectQuery.data, repositoryQueries, useAllRepositories])

  const repositoryOptions = useMemo(() => {
    const repositories = new Map<string, string>()
    for (const item of interfaces) {
      repositories.set(item.softwareRepositoryId, item.softwareRepositoryName)
    }
    return [...repositories].map(([value, label]) => ({ value, label }))
  }, [interfaces])

  const tagOptions = useMemo(() => {
    const tags = new Set<string>()
    for (const item of interfaces) {
      for (const raw of item.tags ?? []) {
        const tag = raw.trim()
        if (tag) tags.add(tag)
      }
    }
    return [...tags]
      .sort((left, right) => left.localeCompare(right, 'zh-CN'))
      .map(tag => ({ value: tag, label: tag }))
  }, [interfaces])

  const visibleInterfaces = useMemo(
    () =>
      interfaces.filter(item => {
        if (repositoryFilter && item.softwareRepositoryId !== repositoryFilter) return false
        if (tagFilter && !(item.tags ?? []).some(tag => tag.trim() === tagFilter)) return false
        return true
      }),
    [interfaces, repositoryFilter, tagFilter],
  )

  const options = useMemo(() => {
    const byId = new Map(interfaces.map(item => [item.interfaceId, item]))
    const visibleIds = new Set<string>()
    const groups = new Map<
      string,
      { label: string; options: { value: string; label: string }[] }
    >()
    for (const item of visibleInterfaces) {
      if (visibleIds.has(item.interfaceId)) continue
      visibleIds.add(item.interfaceId)
      const key = item.softwareRepositoryId || item.softwareRepositoryName
      const group = groups.get(key) ?? {
        label: item.softwareRepositoryName,
        options: [],
      }
      group.options.push({
        value: item.interfaceId,
        label: `${item.method} ${item.path} · ${item.softwareRepositoryName}`,
      })
      groups.set(key, group)
    }
    const selectedOutsideFilter = value
      .filter(interfaceId => !visibleIds.has(interfaceId))
      .map(interfaceId => {
        const item = byId.get(interfaceId)
        return {
          value: interfaceId,
          label: item
            ? `${item.method} ${item.path} · ${item.softwareRepositoryName}`
            : `已选接口 ${interfaceId.slice(0, 8)}`,
        }
      })
    if (selectedOutsideFilter.length) {
      groups.set('__selected__', { label: '已选接口', options: selectedOutsideFilter })
    }
    return [...groups.values()]
  }, [interfaces, value, visibleInterfaces])

  const selectVisibleInterfaces = () => {
    const visibleInterfaceIds = visibleInterfaces.map(item => item.interfaceId)
    onChange([...new Set([...value, ...visibleInterfaceIds])])
  }

  const loading = useAllRepositories
    ? projectQuery.isLoading
    : repositoryQueries.some(query => query.isLoading)
  const error =
    projectQuery.error ?? repositoryQueries.find(query => query.error)?.error
  const suggestionScope = effectiveScope === 'suggested' && suggestedRepositoryIds.length > 0
  const requirementScope = effectiveScope === 'requirement' && !useAllRepositories
  const bindingsLoading = effectiveScope === 'requirement' && bindingsQuery.isLoading
  const switchScope = (next: SelectorScope) => {
    setRepositoryFilter(undefined)
    setTagFilter(undefined)
    setScope(next)
  }

  return (
    <div className="api-interface-selector grid min-w-0 gap-2">
      <div className="api-interface-selector-scope flex flex-wrap items-center gap-2">
        <Tag color={suggestionScope ? 'purple' : useAllRepositories ? 'default' : 'blue'}>
          {suggestionScope
            ? `画像建议仓库（${suggestedRepositoryIds.length}）`
            : useAllRepositories
              ? '项目全部软件仓库'
              : `需求关联软件仓库（${scopedRepositoryIds.length}）`}
        </Tag>
        {suggestedRepositoryIds.length && !suggestionScope ? (
          <button
            type="button"
            className="api-interface-selector-scope-toggle cursor-pointer border-0 bg-transparent p-0 font-[inherit] text-xs text-[var(--app-accent)] disabled:cursor-not-allowed disabled:text-[var(--app-surface-text-muted)]"
            disabled={disabled}
            onClick={() => switchScope('suggested')}
          >
            按画像建议
          </button>
        ) : null}
        {scopedRepositoryIds.length && !requirementScope ? (
          <button
            type="button"
            className="api-interface-selector-scope-toggle cursor-pointer border-0 bg-transparent p-0 font-[inherit] text-xs text-[var(--app-accent)] disabled:cursor-not-allowed disabled:text-[var(--app-surface-text-muted)]"
            disabled={disabled}
            onClick={() => switchScope('requirement')}
          >
            仅看需求关联仓库
          </button>
        ) : null}
        {!useAllRepositories ? (
          <button
            type="button"
            className="api-interface-selector-scope-toggle cursor-pointer border-0 bg-transparent p-0 font-[inherit] text-xs text-[var(--app-accent)] disabled:cursor-not-allowed disabled:text-[var(--app-surface-text-muted)]"
            disabled={disabled}
            onClick={() => switchScope('project')}
          >
            显示项目全部接口
          </button>
        ) : null}
      </div>
      {suggestionScope ? (
        <span className="api-interface-selector-hint text-xs leading-normal text-[var(--app-surface-text-muted)]">
          建议来自仓库画像，仅用于缩小接口范围；可切换范围选择其他软件仓库的接口。
        </span>
      ) : null}
      {requirementId && effectiveScope === 'requirement' && requirementScopeReady && !scopedRepositoryIds.length ? (
        <span className="api-interface-selector-empty text-xs text-[var(--app-surface-text-muted)]">
          该需求尚未关联软件仓库，已展示项目全部接口。
        </span>
      ) : null}
      {repositoryOptions.length ? (
        <div className="api-interface-selector-toolbar flex flex-wrap items-center gap-2">
          <Select
            allowClear
            aria-label="按软件仓库筛选"
            placeholder="全部软件仓库"
            disabled={disabled}
            value={repositoryFilter}
            options={repositoryOptions}
            className="flex-[1_1_220px] min-w-[180px]"
            onChange={value => setRepositoryFilter(value || undefined)}
          />
          {tagOptions.length ? (
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              aria-label="按标签筛选"
              placeholder="全部标签"
              disabled={disabled}
              value={tagFilter}
              options={tagOptions}
              className="flex-[1_1_220px] min-w-[180px]"
              onChange={value => setTagFilter(value || undefined)}
            />
          ) : null}
          <Button
            size="small"
            disabled={
              disabled ||
              (!repositoryFilter && !tagFilter) ||
              !visibleInterfaces.length
            }
            onClick={selectVisibleInterfaces}
          >
            全选筛选结果
          </Button>
        </div>
      ) : null}
      {bindingsQuery.isError ? (
        <Alert
          showIcon
          type="warning"
          title={`读取需求关联软件仓库失败：${getErrorMessage(bindingsQuery.error)}`}
        />
      ) : null}
      {error ? (
        <Alert showIcon type="error" title={getErrorMessage(error)} />
      ) : null}
      <Select
        mode="multiple"
        allowClear
        showSearch
        filterOption={false}
        aria-label="选择接口"
        placeholder="搜索并选择接口，可多选"
        disabled={disabled}
        loading={loading || bindingsLoading}
        value={value}
        options={options}
        onSearch={setKeyword}
        onChange={nextValue => onChange(nextValue)}
        optionFilterProp="label"
      />
      {!loading && !bindingsLoading && !visibleInterfaces.length ? (
        <span className="api-interface-selector-empty text-xs text-[var(--app-surface-text-muted)]">
          {keyword || repositoryFilter || tagFilter
            ? '没有匹配的接口'
            : suggestionScope
              ? '仓库画像建议的后端仓库下还没有接口，可切换到需求关联仓库或项目全部接口'
              : requirementScope
                ? '关联软件仓库下还没有接口，请先在接口库导入'
                : '当前项目还没有接口，请先在接口库创建'}
        </span>
      ) : null}
    </div>
  )
}
