import type { Ref } from 'react'
import { Button, Tag, Tooltip } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { requirementsApi } from '../api/requirements.api'
import { saveBlob } from '@/shared/utils/download'
import { message } from '@/shared/utils/feedback'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { ActionButton } from '@/shared/components/ActionButton'
import { getErrorMessage } from '@/utils/format'
import type { Requirement } from '../types'
import '../styles/detail.css'

export function RequirementDetailHeader({ requirement, requirementId, canWrite, onBack, onEdit, workspaceActionsRef, showDownload, showEdit = true }: {
  requirement: Requirement; requirementId: string; canWrite: boolean; showDownload: boolean; showEdit?: boolean;
  onBack: () => void; onEdit: () => void; workspaceActionsRef?: Ref<HTMLDivElement>
}) {
  const download = useMutation({
    mutationFn: () => requirementsApi.downloadRequirementDocument(requirementId),
    onSuccess: response => saveBlob(response.blob, response.filename || requirement.documentFilename || requirement.name || 'requirement-document'),
    onError: error => message.error(getErrorMessage(error)),
  })
  return <header className="requirement-detail-header tp-list-toolbar">
    <div className="requirement-detail-summary">
      <Tooltip title="返回需求列表"><Button type="text" shape="circle" icon={<ArrowLeftOutlined />} aria-label="返回需求列表" onClick={onBack} /></Tooltip>
      <div className="requirement-detail-heading">
        <div className="requirement-detail-title-row"><h1 className="tp-list-title" title={requirement.name}>{requirement.name}</h1><Tag>需求</Tag></div>
      </div>
    </div>
    <div className="requirement-detail-actions">
      {showDownload ? <ActionButton operation="download" loading={download.isPending} onClick={() => download.mutate()}>下载原文件</ActionButton> : null}
      {canWrite && showEdit ? <ActionButton operation="edit" onClick={onEdit}>编辑需求</ActionButton> : null}
      <div className="requirement-detail-workspace-actions" ref={workspaceActionsRef} />
    </div>
  </header>
}
