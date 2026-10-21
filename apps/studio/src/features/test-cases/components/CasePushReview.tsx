import { Alert, Button, Checkbox, Form, Input, InputNumber, Space, Typography } from 'antd'
import { useState } from 'react'
import type { CasePushPreviewItem, CasePushReconcilePayload } from '../types'

export function CasePushReview({ item, owner, busy, onConfirm, onClose }: {
  item: CasePushPreviewItem
  owner: boolean
  busy: boolean
  onConfirm: (body: CasePushReconcilePayload) => void
  onClose: () => void
}) {
  const [remoteId, setRemoteId] = useState<number | null>(item.operation?.remoteCaseId || null)
  const [reason, setReason] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  return <section className="case-push-review" aria-label="核对未决推送">
    <Typography.Title level={5}>核对：{item.title}</Typography.Title>
    <Alert showIcon type="warning" title="请先在禅道核对原操作" description="系统会检查远端归属和完整内容。在途写入需等待核对窗口，核对不会重新发送用例。" />
    <Form layout="vertical">
      <Form.Item label="已找到的禅道用例 ID" htmlFor="case-push-remote-id">
        <InputNumber autoFocus id="case-push-remote-id" min={1} precision={0} value={remoteId} onChange={setRemoteId} disabled={busy} />
      </Form.Item>
      <Space wrap>
        <Button disabled={!remoteId || busy} onClick={() => onConfirm({ resolution: 'confirm', remoteCaseId: remoteId! })}>确认已有结果</Button>
        <Button disabled={busy} onClick={onClose}>收起核对</Button>
      </Space>
      {owner && <>
        <Form.Item label="未找到远端结果时的人工核对理由" htmlFor="case-push-review-reason">
          <Input.TextArea id="case-push-review-reason" value={reason} onChange={event => setReason(event.target.value)} maxLength={1000} showCount autoSize={{ minRows: 2, maxRows: 4 }} disabled={busy} placeholder="说明核对范围和未写入的依据，至少 8 字。请勿填写 Token 等凭据。" />
        </Form.Item>
        <Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)}>我已人工核对，确认原操作未写入；理解解除后可发起新的推送。</Checkbox>
        <Button danger disabled={busy || !confirmed || reason.trim().length < 8} onClick={() => onConfirm({ resolution: 'not_applied', reason, confirmedNotApplied: true })}>确认未写入并解除锁定</Button>
      </>}
    </Form>
  </section>
}
