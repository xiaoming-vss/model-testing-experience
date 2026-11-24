import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal } from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import { useProjectRequirementOptions } from '@/domain/projects/hooks/useProjectRequirementOptions'
import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { message } from '@/shared/utils/feedback'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import { useSoftwareRepositoryList } from './useSoftwareRepositoryManager'
import type { ApiInterface } from '../types'
import { blankInterface, syncPathParams } from '../utils/interfaceForm'
import {
  EMPTY_JSON_TEXTS,
  buildPayload,
  enabledCount,
  errorMessage,
  jsonTextsOf,
  type JsonTexts,
} from '../utils/interfaceDetailForm'
import { useInterfaceGroupActions } from './useInterfaceGroupActions'
import { useSoftwareRepositoryTreeView } from './useSoftwareRepositoryTreeView'

export type InterfaceDetailTab = 'params' | 'headers' | 'body' | 'response' | 'settings'

export function useInterfaceDetailPage() {
  const { interfaceId } = useParams<{ interfaceId: string }>()
  const isCreate = !interfaceId
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const projectId = useWorkbenchStore(state => state.activeProjectId) ?? ''
  const { can } = useProjectAccess(projectId)
  const canWrite = can('write')
  const { allRequirements } = useProjectRequirementOptions({ activeProjectId: projectId })
  const { repositories, repositoriesQuery } = useSoftwareRepositoryList(projectId)

  const [draft, setDraft] = useState<ApiInterface | null>(null)
  const [tagsText, setTagsText] = useState('')
  const [jsonTexts, setJsonTexts] = useState<JsonTexts>(EMPTY_JSON_TEXTS)
  const [activeTab, setActiveTab] = useState<InterfaceDetailTab>('params')
  const [importOpen, setImportOpen] = useState(false)
  const [dirty, setDirty] = useState(false)

  const groupActions = useInterfaceGroupActions({
    draft,
    setDraft,
    setTagsText,
    projectId,
  })
  const treeView = useSoftwareRepositoryTreeView()

  const interfaceQuery = useQuery({
    queryKey: ['apiInterface', projectId, interfaceId],
    queryFn: () => interfaceLibraryApi.getApiInterface(interfaceId!),
    enabled: Boolean(interfaceId),
  })
  // Reset all editable state when the route changes so a stale draft can never be saved to
  // the interface or project now shown in the URL.
  const routeKey = `${projectId}:${interfaceId ?? 'new'}`
  useEffect(() => {
    setDraft(null)
    setTagsText('')
    setJsonTexts(EMPTY_JSON_TEXTS)
    setActiveTab('params')
    setDirty(false)
  }, [routeKey])
  useEffect(() => {
    if (!interfaceQuery.data) return
    const data = interfaceQuery.data
    setDraft(data)
    setTagsText(data.tags.join(', '))
    setJsonTexts(jsonTextsOf(data))
    setDirty(false)
  }, [interfaceQuery.data])

  useEffect(() => {
    if (!isCreate || draft || repositoriesQuery.isLoading) return
    const requestedRepositoryId = searchParams.get('softwareRepositoryId') ?? ''
    const repository =
      repositories.find(
        item => item.softwareRepositoryId === requestedRepositoryId,
      ) ?? repositories[0]
    if (!repository) return
    const next = blankInterface(repository.softwareRepositoryId)
    next.softwareRepositoryName = repository.name
    setDraft(next)
    setDirty(false)
  }, [repositories, repositoriesQuery.isLoading, draft, isCreate, searchParams])

  const selectedRepository = repositories.find(
    repository => repository.softwareRepositoryId === draft?.softwareRepositoryId,
  )
  const interfaceInActiveProject =
    isCreate ||
    repositories.some(
      repository => repository.softwareRepositoryId === draft?.softwareRepositoryId,
    )

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error('接口尚未加载')
      if (!isCreate && draft.interfaceId !== interfaceId) {
        throw new Error('接口正在切换，请稍候再保存')
      }
      if (!interfaceInActiveProject) throw new Error('接口不属于当前项目')
      const payload = buildPayload(draft, tagsText, jsonTexts)
      if (isCreate) {
        if (!draft.softwareRepositoryId) throw new Error('请选择所属软件仓库')
        return interfaceLibraryApi.createApiInterface(draft.softwareRepositoryId, payload)
      }
      return interfaceLibraryApi.updateApiInterface(draft.interfaceId, payload)
    },
    onSuccess: data => {
      setDraft(data)
      setTagsText(data.tags.join(', '))
      setJsonTexts(jsonTextsOf(data))
      setDirty(false)
      message.success(isCreate ? '接口已创建' : '接口已保存')
      queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
      queryClient.invalidateQueries({ queryKey: ['apiInterface', projectId, data.interfaceId] })
      queryClient.invalidateQueries({ queryKey: ['softwareRepositories', projectId] })
      if (isCreate) {
        navigate(`/asset-library/interfaces/${data.interfaceId}`, { replace: true })
      }
    },
    onError: error => message.error(errorMessage(error)),
  })
  const deleteMutation = useMutation({
    mutationFn: () => interfaceLibraryApi.deleteApiInterface(draft!.interfaceId),
    onSuccess: () => {
      message.success('接口已删除')
      queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
      queryClient.invalidateQueries({ queryKey: ['softwareRepositories', projectId] })
      navigate('/asset-library?tab=interfaces')
    },
    onError: error => message.error(errorMessage(error)),
  })

  function patch(patchValue: Partial<ApiInterface>) {
    setDraft(previous => (previous ? { ...previous, ...patchValue } : previous))
    setDirty(true)
  }

  function changePath(path: string) {
    if (draft?.path === path) return
    setDraft(previous =>
      previous
        ? { ...previous, path, pathParams: syncPathParams(path, previous.pathParams) }
        : previous,
    )
    setDirty(true)
  }

  function changeRepository(softwareRepositoryId: string) {
    const repository = repositories.find(
      item => item.softwareRepositoryId === softwareRepositoryId,
    )
    setDraft(previous =>
      previous
        ? {
            ...previous,
            softwareRepositoryId,
            softwareRepositoryName: repository?.name ?? '',
          }
        : previous,
    )
    setDirty(true)
  }

  const updateTagsText: typeof setTagsText = value => {
    setTagsText(value)
    setDirty(true)
  }

  const updateJsonTexts: typeof setJsonTexts = value => {
    setJsonTexts(value)
    setDirty(true)
  }

  function confirmDelete() {
    if (!draft || isCreate) return
    if (draft.interfaceId !== interfaceId) {
      message.info('接口正在切换，请稍候再操作')
      return
    }
    Modal.confirm({
      title: '删除接口',
      content: `确定删除「${draft.name || draft.path}」吗？删除后不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteMutation.mutateAsync(),
    })
  }

  const tabs: { key: InterfaceDetailTab; label: string; count?: number }[] = draft
    ? [
        { key: 'params', label: '参数', count: enabledCount(draft.pathParams) + enabledCount(draft.queryParams) },
        { key: 'headers', label: '请求头', count: enabledCount(draft.headers) },
        { key: 'body', label: '请求体', count: draft.bodyType === 'none' ? 0 : 1 },
        { key: 'response', label: '响应', count: 1 },
        { key: 'settings', label: '设置' },
      ]
    : []

  return {
    interfaceId,
    isCreate,
    navigate,
    projectId,
    canWrite,
    allRequirements,
    repositories,
    repositoriesQuery,
    draft,
    dirty,
    tagsText,
    setTagsText: updateTagsText,
    jsonTexts,
    setJsonTexts: updateJsonTexts,
    activeTab,
    setActiveTab,
    importOpen,
    setImportOpen,
    interfaceQuery,
    selectedRepository,
    interfaceInActiveProject,
    saveMutation,
    deleteMutation,
    patch,
    changePath,
    changeRepository,
    confirmDelete,
    tabs,
    treeView,
    ...groupActions,
  } as const
}

export type InterfaceDetailPageModel = ReturnType<typeof useInterfaceDetailPage>
