import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal } from 'antd'
import { useState, type Dispatch, type SetStateAction } from 'react'
import { message } from '@/shared/utils/feedback'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type {
  ApiInterface,
  ApiInterfaceListItem,
  InterfaceGroupTarget,
  InterfaceMoveTarget,
  SoftwareRepository,
} from '../types'
import { splitTags } from '../utils/interfaceForm'
import { firstTag, replaceFirstTag, type InterfaceGroup } from '../utils/interfaceGroups'
import { errorMessage } from '../utils/interfaceDetailForm'

export function useInterfaceGroupActions({
  draft,
  setDraft,
  setTagsText,
  projectId,
}: {
  draft: ApiInterface | null
  setDraft: Dispatch<SetStateAction<ApiInterface | null>>
  setTagsText: Dispatch<SetStateAction<string>>
  projectId: string
}) {
  const queryClient = useQueryClient()
  const [groupRenameTarget, setGroupRenameTarget] = useState<InterfaceGroupTarget | null>(null)
  const [groupRenameValue, setGroupRenameValue] = useState('')
  const [moveTarget, setMoveTarget] = useState<InterfaceMoveTarget | null>(null)
  const [moveMode, setMoveMode] = useState<'group' | 'clear'>('group')
  const [moveGroupName, setMoveGroupName] = useState('')
  const [createGroupRepository, setCreateGroupRepository] = useState<SoftwareRepository | null>(null)
  const [createGroupName, setCreateGroupName] = useState('')

  const renameGroupMutation = useMutation({
    mutationFn: ({
      target,
      newGroupName,
    }: {
      target: InterfaceGroupTarget
      newGroupName: string
    }) =>
      interfaceLibraryApi.renameApiInterfaceGroup(
        target.repository.softwareRepositoryId,
        {
          currentGroupName: target.group.tag,
          newGroupName,
        },
      ),
    onSuccess: (data, variables) => {
      syncDraftAfterGroupRename(
        variables.target.repository.softwareRepositoryId,
        variables.target.group.tag,
        data.newGroupName,
      )
      message.success(
        data.updatedCount
          ? `已将分组「${data.groupName}」重命名为「${data.newGroupName}」，更新 ${data.updatedCount} 个接口`
          : `已将分组「${data.groupName}」重命名为「${data.newGroupName}」`,
      )
      setGroupRenameTarget(null)
      void queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
      void queryClient.invalidateQueries({
        queryKey: ['softwareRepositories', projectId],
      })
    },
    onError: error => message.error(errorMessage(error)),
  })
  const deleteGroupMutation = useMutation({
    mutationFn: (target: InterfaceGroupTarget) =>
      interfaceLibraryApi.deleteApiInterfaceGroup(
        target.repository.softwareRepositoryId,
        { groupName: target.group.tag },
      ),
    onSuccess: (data, target) => {
      syncDraftAfterGroupRemoval(target.repository.softwareRepositoryId, target.group.tag)
      message.success(
        data.updatedCount
          ? `已移除分组「${data.groupName}」，${data.updatedCount} 个接口归入「未分类」`
          : `已移除分组「${data.groupName}」`,
      )
      void queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
      void queryClient.invalidateQueries({
        queryKey: ['softwareRepositories', projectId],
      })
    },
    onError: error => message.error(errorMessage(error)),
  })
  const moveMutation = useMutation({
    mutationFn: ({
      item,
      groupName,
    }: {
      item: ApiInterfaceListItem
      groupName: string
    }) => interfaceLibraryApi.moveApiInterfaceToGroup(item.interfaceId, { groupName }),
    onSuccess: (data, variables) => {
      if (draft?.interfaceId && draft.interfaceId === data.interfaceId) {
        setDraft(previous =>
          previous && previous.interfaceId === data.interfaceId
            ? {
                ...previous,
                tags: data.tags,
                version: data.version,
                updatedAt: data.updatedAt,
              }
            : previous,
        )
        setTagsText(data.tags.join(', '))
      }
      message.success(
        variables.groupName
          ? `已将「${data.name}」移动到分组「${variables.groupName}」`
          : `已清除「${data.name}」的标签并归入「未分类」`,
      )
      setMoveTarget(null)
      void queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
    },
    onError: error => message.error(errorMessage(error)),
  })
  const createGroupMutation = useMutation({
    mutationFn: ({
      repository,
      groupName,
    }: {
      repository: SoftwareRepository
      groupName: string
    }) =>
      interfaceLibraryApi.createApiInterfaceGroup(repository.softwareRepositoryId, {
        groupName,
      }),
    onSuccess: data => {
      message.success(`已创建分组「${data.newGroupName}」`)
      setCreateGroupRepository(null)
      void queryClient.invalidateQueries({
        queryKey: ['softwareRepositories', projectId],
      })
    },
    onError: error => message.error(errorMessage(error)),
  })

  function syncDraftAfterGroupRename(
    softwareRepositoryId: string,
    currentGroup: string,
    newGroup: string,
  ) {
    if (draft?.softwareRepositoryId !== softwareRepositoryId) return
    setDraft(previous => {
      if (
        !previous?.interfaceId ||
        previous.softwareRepositoryId !== softwareRepositoryId ||
        firstTag(previous.tags) !== currentGroup
      ) {
        return previous
      }
      return { ...previous, tags: replaceFirstTag(previous.tags, newGroup) }
    })
    setTagsText(previous => {
      const parsed = splitTags(previous)
      if (firstTag(parsed) !== currentGroup) return previous
      return replaceFirstTag(parsed, newGroup).join(', ')
    })
  }

  function syncDraftAfterGroupRemoval(
    softwareRepositoryId: string,
    groupName: string,
  ) {
    if (draft?.softwareRepositoryId !== softwareRepositoryId) return
    setDraft(previous => {
      if (
        !previous?.interfaceId ||
        previous.softwareRepositoryId !== softwareRepositoryId ||
        firstTag(previous.tags) !== groupName
      ) {
        return previous
      }
      return { ...previous, tags: [] }
    })
    setTagsText(previous =>
      firstTag(splitTags(previous)) === groupName ? '' : previous,
    )
  }

  function openCreateGroup(repository: SoftwareRepository) {
    setCreateGroupRepository(repository)
    setCreateGroupName('')
  }

  function submitCreateGroup() {
    if (!createGroupRepository) return
    const groupName = createGroupName.trim()
    if (!groupName) {
      message.warning('请输入分组名称')
      return
    }
    createGroupMutation.mutate({ repository: createGroupRepository, groupName })
  }

  function openRenameGroup(repository: SoftwareRepository, group: InterfaceGroup) {
    setGroupRenameTarget({ repository, group })
    setGroupRenameValue(group.tag)
  }

  function submitRenameGroup() {
    if (!groupRenameTarget) return
    const newGroupName = groupRenameValue.trim()
    if (!newGroupName) {
      message.warning('请输入分组名称')
      return
    }
    if (newGroupName === groupRenameTarget.group.tag) {
      setGroupRenameTarget(null)
      return
    }
    renameGroupMutation.mutate({ target: groupRenameTarget, newGroupName })
  }

  function openRemoveGroup(repository: SoftwareRepository, group: InterfaceGroup) {
    Modal.confirm({
      title: '移除分组',
      content: `该组 ${group.items.length} 个接口将清除全部标签并归入「未分类」，接口不会被删除，次要标签也会被清除。`,
      okText: '移除分组',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteGroupMutation.mutateAsync({ repository, group }),
    })
  }

  function openMoveInterface(
    repository: SoftwareRepository,
    item: ApiInterfaceListItem,
    groups: string[],
  ) {
    setMoveTarget({ repository, item, groups })
    setMoveMode('group')
    setMoveGroupName('')
  }

  function submitMoveInterface() {
    if (!moveTarget) return
    const groupName = moveMode === 'clear' ? '' : moveGroupName.trim()
    if (moveMode === 'group' && !groupName) {
      message.warning('请选择或输入目标分组')
      return
    }
    moveMutation.mutate({ item: moveTarget.item, groupName })
  }

  return {
    groupRenameTarget,
    setGroupRenameTarget,
    groupRenameValue,
    setGroupRenameValue,
    moveTarget,
    setMoveTarget,
    moveMode,
    setMoveMode,
    moveGroupName,
    setMoveGroupName,
    createGroupRepository,
    setCreateGroupRepository,
    createGroupName,
    setCreateGroupName,
    renameGroupMutation,
    deleteGroupMutation,
    moveMutation,
    createGroupMutation,
    openCreateGroup,
    submitCreateGroup,
    openRenameGroup,
    submitRenameGroup,
    openRemoveGroup,
    openMoveInterface,
    submitMoveInterface,
  } as const
}
