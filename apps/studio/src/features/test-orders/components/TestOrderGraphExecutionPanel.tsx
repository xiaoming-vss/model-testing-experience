import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { Alert, Button, Input, Spin, Tag, Typography } from 'antd'
import { useState } from 'react'
import { formatTime } from '@/utils/format'
import { useTestOrderEntrySave } from '../hooks/useTestOrderEntrySave'
import type { TestOrderEntry, UpdateTestOrderEntryPayload } from '../types'
import { isTestOrderEntryLocked } from '../utils/testOrderExecution'
import { getTestOrderEntryStatusMeta } from '../utils/testOrderStatus'
import { TestOrderVerdictButtons } from './TestOrderVerdictButtons'
import '@/shared/styles/surface-tokens.css'
import workspaceStyles from '../styles/test-order-workspace.module.css'

type Props = {
  orderId: string
  entry: TestOrderEntry
  canExecute: boolean
  currentUserId?: string
  isProjectOwner: boolean
}

/** Mount per entry so drafts and save feedback never leak into another card. */
export function TestOrderGraphExecutionPanel(props: Props) {
  const detail = useQuery({
    queryKey: ['testOrderEntry', props.orderId, props.entry.entryId],
    queryFn: () => api.getTestOrderEntry(props.orderId, props.entry.entryId!),
    enabled: Boolean(props.entry.entryId),
  })
  if (detail.isPending) return <Spin description="加载执行详情…" />
  if (detail.isError) return <Alert type="error" title="执行详情加载失败" action={<Button onClick={() => void detail.refetch()}>重试</Button>} />
  return <TestOrderGraphExecutionContent {...props} entry={detail.data} />
}

function TestOrderGraphExecutionContent({ orderId, entry, canExecute, currentUserId, isProjectOwner }: Props) {
  const mutation = useTestOrderEntrySave(orderId)
  const [draft, setDraft] = useState<UpdateTestOrderEntryPayload>({})
  const locked = isTestOrderEntryLocked(entry.assigneeUserId, currentUserId, isProjectOwner)
  const canJudge = canExecute && !locked && Boolean(entry.entryId)
  const status = getTestOrderEntryStatusMeta(entry.status)
  const reasonField = entry.status === 'blocked' ? 'blockReason' : 'failureReason'
  const hasReason = entry.status === 'failed' || entry.status === 'blocked'
  const dirty = Object.keys(draft).length > 0

  function save(payload: UpdateTestOrderEntryPayload) {
    if (!canJudge || !entry.entryId || mutation.isPending) return
    mutation.mutate({ entryId: entry.entryId, payload: { ...draft, ...payload } }, {
      onSuccess: () => setDraft({}),
    })
  }

  return <section className={`test-order-graph-execution tp-surface flex min-w-0 flex-col gap-3 text-[13px] text-[var(--ant-color-text)] [&_ol]:mt-2 [&_ol]:pl-[22px] [&_ol>li]:mb-2.5 [&_ol>li]:leading-[1.6] [&_ol>li]:[overflow-wrap:anywhere] [&_p]:m-0 [&_h3]:m-0 ${workspaceStyles.root}`} aria-label="图谱用例执行">
    <div className="test-order-graph-execution-meta flex flex-wrap items-center gap-1.5">
      <Tag color={status.color}>{status.label}</Tag>
      {entry.casePriority ? <Tag>{entry.casePriority}</Tag> : null}
      {entry.caseModule ? <Typography.Text type="secondary">{entry.caseModule}</Typography.Text> : null}
    </div>
    <h3 className="text-[14px] leading-[1.6]">{entry.caseTitle || entry.caseId}</h3>
    <section>
      <strong>前置条件</strong>
      {entry.snapshot?.preconditions?.length ? <ol>{entry.snapshot.preconditions.map((item, i) => <li key={i}>{item}</li>)}</ol> : <p>暂无前置条件</p>}
    </section>
    <section>
      <strong>测试步骤与预期结果</strong>
      {entry.snapshot?.steps?.length ? <ol className="test-order-graph-steps">
        {entry.snapshot.steps.map((step, i) => <li key={i}>
          <div>{step.action || '—'}</div>
          <div className="test-order-graph-expected text-[var(--ant-color-text-secondary)]">预期：{step.expected || '—'}</div>
        </li>)}
      </ol> : <p>暂无测试步骤</p>}
    </section>
    <hr className="test-order-graph-execution-divider m-0 w-full border-0 border-t border-t-[var(--ant-color-border-secondary)]" />
    <Typography.Text type="secondary">执行时间：{formatTime(entry.executedAt) || '—'}</Typography.Text>
    {!canJudge ? <Alert type="info" showIcon title={locked ? '该用例已分配给其他执行人，仅执行人或项目所有者可修改' : '当前仅可查看，没有执行权限'} /> : null}
    <strong>执行判定结果</strong>
    <TestOrderVerdictButtons status={entry.status} disabled={!canJudge || mutation.isPending} onJudge={(value) => save({ status: value })} />
    <div className="test-order-defect-section flex flex-col gap-2">
      {hasReason ? <label className="flex flex-col gap-1.5">
        {entry.status === 'blocked' ? '阻塞原因' : '失败原因'}
        <Input.TextArea
          aria-label={entry.status === 'blocked' ? '阻塞原因' : '失败原因'}
          rows={3}
          value={draft[reasonField] ?? entry[reasonField] ?? ''}
          disabled={!canJudge || mutation.isPending}
          onChange={(event) => setDraft((value) => ({ ...value, [reasonField]: event.target.value }))}
        />
      </label> : null}
      <label className="flex flex-col gap-1.5">禅道缺陷号
        <Input
          aria-label="禅道缺陷号"
          placeholder="禅道缺陷号（可选）"
          value={draft.zentaoBugId ?? entry.zentaoBugId ?? ''}
          disabled={!canJudge || mutation.isPending}
          onChange={(event) => setDraft((value) => ({ ...value, zentaoBugId: event.target.value }))}
        />
      </label>
      <div className="test-order-graph-save-actions flex flex-wrap items-center gap-1.5">
        <Button size="small" disabled={!canJudge || !dirty} loading={mutation.isPending} onClick={() => save({})}>保存补充信息</Button>
        {entry.zentaoBugId ? <Button size="small" disabled={!canJudge || mutation.isPending} onClick={() => save({ zentaoBugId: '' })}>解绑缺陷</Button> : null}
        <span role="status" className="text-[var(--ant-color-text-secondary)]">{mutation.isPending ? '保存中…' : mutation.isError ? '保存失败，请重试' : dirty ? '补充信息待保存' : mutation.isSuccess ? '已保存' : ''}</span>
      </div>
    </div>
  </section>
}
