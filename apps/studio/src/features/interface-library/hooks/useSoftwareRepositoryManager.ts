import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal } from 'antd'
import { useMemo, useState } from 'react'
import { ApiError, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { SoftwareRepository } from '../types'

/** Read-only software repository list; the interface library only uses repositories as groups. */
export function useSoftwareRepositoryList(projectId: string) {
  const repositoriesQuery = useQuery({
    queryKey: ['softwareRepositories', projectId],
    queryFn: () => interfaceLibraryApi.getSoftwareRepositories(projectId),
    enabled: Boolean(projectId),
  })
  const repositories = useMemo(
    () => listItems(repositoriesQuery.data) as SoftwareRepository[],
    [repositoriesQuery.data],
  )
  return { repositories, repositoriesQuery }
}

/** Software repository maintenance lives on the Software Repositories page, not in the interface library. */
export function useSoftwareRepositoryManager(projectId: string) {
  const queryClient = useQueryClient()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingRepository, setEditingRepository] =
    useState<SoftwareRepository | null>(null)
  const { repositories, repositoriesQuery } = useSoftwareRepositoryList(projectId)

  const deleteMutation = useMutation({
    mutationFn: (repository: SoftwareRepository) =>
      interfaceLibraryApi.deleteSoftwareRepository(repository.softwareRepositoryId),
    onSuccess: () => {
      message.success('软件仓库已删除')
      queryClient.invalidateQueries({ queryKey: ['softwareRepositories', projectId] })
    },
    onError: error => message.error(errorMessage(error)),
  })

  function openCreate() {
    setEditingRepository(null)
    setEditorOpen(true)
  }

  function openEdit(repository: SoftwareRepository) {
    setEditingRepository(repository)
    setEditorOpen(true)
  }

  function closeEditor() {
    setEditorOpen(false)
  }

  function deleteRepository(repository: SoftwareRepository) {
    if (repository.interfaceCount > 0) {
      message.info('请先删除该软件仓库下的接口')
      return
    }
    Modal.confirm({
      title: '删除软件仓库',
      content: `确定删除「${repository.name}」吗？仍被需求关联时无法删除。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteMutation.mutateAsync(repository),
    })
  }

  return {
    repositories,
    repositoriesQuery,
    editorOpen,
    editingRepository,
    openCreate,
    openEdit,
    closeEditor,
    deleteRepository,
  }
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  return getErrorMessage(error)
}
