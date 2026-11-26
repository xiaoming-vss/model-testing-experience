import { useState } from 'react'
import { Alert, Button, InputNumber, Space, Typography } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { bugsApi } from '../api/bugs.api'
import type { BugAttachment, BugZentaoPush } from '../types'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

/** Recover attachments whose remote write result is unknown, keyed by file id. */
export function BugZentaoAttachmentRecovery({ bugId, attachments, busy, canWrite, onSaved }: {
  bugId: string
  attachments: BugAttachment[]
  busy: boolean
  canWrite: boolean
  onSaved: (result: BugZentaoPush) => void
}) {
  const [remoteFileIds, setRemoteFileIds] = useState<Record<string, number | null>>({})
  const reconcile = useMutation({
    mutationFn: ({ fileId, remoteFileId }: { fileId: string; remoteFileId: number }) =>
      bugsApi.reconcileBugZentaoAttachment(bugId, fileId, remoteFileId),
    onSuccess: onSaved,
    onError: (error) => message.error(getErrorMessage(error)),
  })
  return <>
    <Alert type="warning" showIcon title="附件同步结果待核对：在禅道确认远端文件后，按文件填写编号恢复关联，勿重复上传。" />
    {canWrite && attachments.map((attachment) => {
      const remoteFileId = remoteFileIds[attachment.fileId] ?? null
      return <Space key={attachment.fileId} wrap>
        <Typography.Text>{attachment.filename}</Typography.Text>
        <InputNumber min={1} precision={0} placeholder="禅道文件编号"
          aria-label={`${attachment.filename} 的禅道文件编号`} value={remoteFileId}
          onChange={(value) => setRemoteFileIds((ids) => ({ ...ids, [attachment.fileId]: value }))} />
        <Button disabled={!remoteFileId || busy || reconcile.isPending}
          onClick={() => reconcile.mutate({ fileId: attachment.fileId, remoteFileId: remoteFileId! })}>
          按远端文件编号恢复关联
        </Button>
      </Space>
    })}
  </>
}
