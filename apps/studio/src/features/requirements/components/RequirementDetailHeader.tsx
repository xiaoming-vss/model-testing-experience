import type { Ref } from 'react'
import { Tag, Tooltip } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { requirementsApi } from '../api/requirements.api'
import { saveBlob } from '@/shared/utils/download'
import { message } from '@/shared/utils/feedback'
import { RightOutlined } from '@ant-design/icons'
import { ActionButton } from '@/shared/components/ActionButton'
import { getErrorMessage } from '@/utils/format'
import type { Requirement } from '../types'

export function RequirementDetailHeader({ requirement, requirementId, canWrite, onBack, onEdit, onRefresh, refreshing, readingActionsRef, showDownload, showEdit = true, readingNode, onLeaveReading }: {
  requirement: Requirement; requirementId: string; canWrite: boolean; showDownload: boolean; showEdit?: boolean;
  onBack: () => void; onEdit: () => void; onRefresh?: () => void; refreshing?: boolean; readingActionsRef?: Ref<HTMLDivElement>
  /** 画布内正在阅读的产物；有值时面包屑追加一级「需求 / 当前产物」。状态由阶段侧栏展示。 */
  readingNode?: { label: string } | null
  /** 阅读态点「需求名」一级退回生成流程。 */
  onLeaveReading?: () => void
}) {
  const download = useMutation({
    mutationFn: () => requirementsApi.downloadRequirementDocument(requirementId),
    onSuccess: response => saveBlob(response.blob, response.filename || requirement.documentFilename || requirement.name || 'requirement-document'),
    onError: error => message.error(getErrorMessage(error)),
  })
  return <header className="requirement-detail-header tp-list-toolbar flex-none flex-wrap gap-x-4 gap-y-3 rounded-none border-0 border-b border-[var(--app-surface-border)] bg-[var(--app-list-toolbar-bg,var(--srf-card))]">
    <nav className="requirement-detail-crumbs flex min-w-0 flex-[1_1_360px] items-center gap-[7px] max-[840.01px]:flex-[1_1_100%]" aria-label="面包屑">
      <Tooltip title="返回需求列表"><button type="button" className="requirement-crumb-link -ml-[5px] inline-flex h-6 cursor-pointer items-center rounded-[5px] border-0 bg-transparent px-[5px] font-[inherit] text-[13px] leading-none text-[var(--app-accent)] hover:bg-[var(--app-accent-surface)] hover:text-[var(--app-accent-hover)] hover:underline" aria-label="返回需求列表" onClick={onBack}>需求列表</button></Tooltip>
      <RightOutlined className="requirement-crumb-sep flex-none text-[10px] text-[var(--app-surface-text-muted)]" aria-hidden />
      {readingNode ? <>
        <Tooltip title="返回生成流程"><button type="button" className="requirement-crumb-parent-link inline-flex h-6 max-w-[300px] cursor-pointer items-center truncate rounded-[5px] border-0 bg-transparent px-[5px] font-[inherit] text-[13px] leading-none text-[var(--app-accent)] hover:bg-[var(--app-accent-surface)] hover:text-[var(--app-accent-hover)] hover:underline" onClick={onLeaveReading}>{requirement.name}</button></Tooltip>
        <RightOutlined className="requirement-crumb-sep flex-none text-[10px] text-[var(--app-surface-text-muted)]" aria-hidden />
        <h1 className="requirement-detail-title requirement-detail-title--current m-0 max-w-[240px] overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-medium leading-[20px] text-[var(--app-surface-text)]" aria-current="page" title={readingNode.label}>{readingNode.label}</h1>
      </> : <>
        <h1 className="tp-list-title requirement-detail-title min-w-0 flex-[0_1_auto] overflow-hidden text-ellipsis whitespace-nowrap" title={requirement.name}>{requirement.name}</h1>
        <Tag className="m-0 shrink-0">需求</Tag>
      </>}
    </nav>
    <div className="requirement-detail-actions flex min-w-0 flex-wrap items-center gap-2 max-[840.01px]:ml-auto">
      {onRefresh ? <ActionButton operation="refresh" loading={refreshing} onClick={onRefresh}>刷新</ActionButton> : null}
      {showDownload ? <ActionButton operation="download" loading={download.isPending} onClick={() => download.mutate()}>下载原文件</ActionButton> : null}
      {canWrite && showEdit ? <ActionButton operation="edit" onClick={onEdit}>编辑需求</ActionButton> : null}
      <div className="requirement-detail-workspace-actions" ref={readingActionsRef} />
    </div>
  </header>
}
