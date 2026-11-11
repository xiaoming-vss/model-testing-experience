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
import '../styles/detail.css'

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
  return <header className="requirement-detail-header tp-list-toolbar">
    <nav className="requirement-detail-crumbs" aria-label="面包屑">
      <Tooltip title="返回需求列表"><button type="button" className="requirement-crumb-link" aria-label="返回需求列表" onClick={onBack}>需求列表</button></Tooltip>
      <RightOutlined className="requirement-crumb-sep" aria-hidden />
      {readingNode ? <>
        <Tooltip title="返回生成流程"><button type="button" className="requirement-crumb-parent-link" onClick={onLeaveReading}>{requirement.name}</button></Tooltip>
        <RightOutlined className="requirement-crumb-sep" aria-hidden />
        <h1 className="requirement-detail-title requirement-detail-title--current" aria-current="page" title={readingNode.label}>{readingNode.label}</h1>
      </> : <>
        <h1 className="tp-list-title requirement-detail-title" title={requirement.name}>{requirement.name}</h1>
        <Tag>需求</Tag>
      </>}
    </nav>
    <div className="requirement-detail-actions">
      {showDownload ? <ActionButton operation="download" loading={download.isPending} onClick={() => download.mutate()}>下载原文件</ActionButton> : null}
      {canWrite && showEdit ? <ActionButton operation="edit" onClick={onEdit}>编辑需求</ActionButton> : null}
      <div className="requirement-detail-workspace-actions" ref={readingActionsRef} />
      {onRefresh ? <ActionButton operation="refresh" loading={refreshing} onClick={onRefresh}>刷新</ActionButton> : null}
    </div>
  </header>
}
