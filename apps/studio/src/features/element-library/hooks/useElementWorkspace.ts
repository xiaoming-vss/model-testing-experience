import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { useState } from 'react'
import { listItems } from '@/shared/api/request'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { getErrorMessage } from '@/utils/format'
import { elementLibraryApi } from '../api/elementLibrary.api'
import type { ElementDetail, ElementDraft, VerificationStatus } from '../types'

export const all = { key: 'all', name: '全部元素', route: '' }
export const common = { key: 'common', name: '公共元素', route: '' }

export type ElementWorkspaceModel = ReturnType<typeof useElementWorkspace>

export function useElementWorkspace(repositoryId: string) {
  const [group, setGroup] = useState(all.key)
  const [keyword, setKeyword] = useState('')
  const [searchReset, setSearchReset] = useState(0)
  const [status, setStatus] = useState<VerificationStatus | 'all'>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [selected, setSelected] = useState('')
  const [editor, setEditor] = useState<ElementDetail | 'new' | null>(null)
  const [groupModal, setGroupModal] = useState(false)
  const { message } = App.useApp()
  const cache = useQueryClient()
  const root = ['uiElementLibrary', repositoryId]
  const groupsQuery = useQuery({ queryKey: [...root, 'groups'], queryFn: () => elementLibraryApi.getGroups(repositoryId) })
  const groups = listItems(groupsQuery.data)
  const commonGroup = groups.find(item => item.kind === 'common')
  const pageGroups = groups.filter(item => item.kind === 'page')
  const activeGroup = group === common.key ? commonGroup : pageGroups.find(item => item.groupId === group)
  const entries = [
    { ...all, count: groups.reduce((total, item) => total + item.elementCount, 0) },
    { ...common, count: commonGroup?.elementCount ?? 0 },
    ...pageGroups.map(item => ({ key: item.groupId, name: item.name, route: item.routeTemplate, count: item.elementCount })),
  ]
  const current = entries.find(item => item.key === group) ?? all
  const filters = { groupId: activeGroup?.groupId, keyword, verificationStatus: status === 'all' ? undefined : status, page, pageSize }
  const listEnabled = Boolean(group === all.key || activeGroup)
  const list = useQuery({
    queryKey: [...root, 'elements', filters],
    queryFn: () => elementLibraryApi.getElements(repositoryId, filters),
    enabled: listEnabled,
  })
  const detail = useQuery({
    queryKey: [...root, 'detail', selected],
    queryFn: () => elementLibraryApi.getElement(selected),
    enabled: Boolean(selected),
  })
  const refresh = () => cache.invalidateQueries({ queryKey: root })

  function selectGroup(next: string) {
    setGroup(next)
    setSelected('')
    setPage(1)
  }

  function clearFilters() {
    setKeyword('')
    setSearchReset(value => value + 1)
    setStatus('all')
    setPage(1)
  }

  const saveElement = useMutation({
    mutationFn: (draft: ElementDraft) => editor && editor !== 'new'
      ? elementLibraryApi.updateElement(editor.elementId, { ...draft, version: editor.version })
      : elementLibraryApi.createElement(repositoryId, draft),
    onSuccess: (result, draft) => {
      cache.setQueryData([...root, 'detail', result.elementId], result)
      setEditor(null)
      setGroup(draft.groupId ?? common.key)
      clearFilters()
      setSelected(result.elementId)
      void refresh()
      void message.success('元素已保存')
    },
  })
  const deleteElement = useMutation({
    mutationFn: (item: Pick<ElementDetail, 'elementId' | 'version'>) => elementLibraryApi.deleteElement(item.elementId, item.version),
    onSuccess: () => {
      setSelected('')
      void refresh()
      void message.success('元素已删除')
    },
    onError: error => void message.error(getErrorMessage(error)),
  })
  const createGroup = useMutation({
    mutationFn: (fields: { name: string; routeTemplate: string }) => elementLibraryApi.createGroup(repositoryId, fields),
    onSuccess: item => {
      setGroupModal(false)
      selectGroup(item.groupId)
      clearFilters()
      void refresh()
      void message.success('页面分组已创建')
    },
  })
  const deleteGroup = useMutation({
    mutationFn: elementLibraryApi.deleteGroup,
    onSuccess: () => {
      selectGroup(all.key)
      void refresh()
      void message.success('分组已删除')
    },
    onError: error => void message.error(getErrorMessage(error)),
  })

  function openEditor(item?: ElementDetail) {
    saveElement.reset()
    setEditor(item ?? 'new')
  }

  /** 列表行只有摘要，编辑前先取详情（定位值和参数不在列表契约里）。 */
  async function openEditorById(elementId: string) {
    try {
      const detail = await elementLibraryApi.getElement(elementId)
      cache.setQueryData([...root, 'detail', elementId], detail)
      openEditor(detail)
    } catch (error) {
      void message.error(getErrorMessage(error))
    }
  }

  return {
    activeGroup, clearFilters, createGroup, current, deleteElement, deleteGroup,
    detail, editor, entries, group, groupModal, groups, groupsQuery, keyword, list, listEnabled,
    openEditor, openEditorById, page, pageGroups, pageSize, refresh, saveElement, searchReset, selectGroup,
    selected, setEditor, setGroupModal, setKeyword, setPage, setPageSize, setSelected, setStatus, status,
  }
}
