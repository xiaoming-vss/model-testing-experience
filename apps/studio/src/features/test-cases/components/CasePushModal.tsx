import { Alert, Button, Checkbox, Form, InputNumber, Select, Space, Table, Typography } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ListPagination } from '@/shared/components/ListPagination'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { getErrorMessage } from '@/utils/format'
import { functionTestingApi } from '../api/functionTesting.api'
import type { CasePushPreviewItem, CasePushReconcilePayload, FunctionTestCaseZentaoImportItem, ImportFunctionTestCasesToZentaoPayload } from '../types'
import { CasePushReview } from './CasePushReview'
import '../styles/case-push.css'

type TargetValues = { productId: number; moduleId: number }
const unresolved = (operation?: FunctionTestCaseZentaoImportItem | null) => operation?.status === 'uncertain' || operation?.status === 'pending'

export function CasePushModal({ suiteId, caseIds, count, projectId, onClose }: {
  suiteId: string; caseIds: string[]; count: number; projectId: string; onClose: () => void
}) {
  const [form] = Form.useForm<TargetValues>()
  const { project } = useProjectAccess(projectId)
  const [values, setValues] = useState<TargetValues | null>(null)
  const [items, setItems] = useState<CasePushPreviewItem[] | null>(null)
  const [choices, setChoices] = useState<Record<string, number>>({})
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')
  const [review, setReview] = useState<CasePushPreviewItem | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [attempted, setAttempted] = useState(false)
  const [restoreRequired, setRestoreRequired] = useState(false)
  const [mayConfirm, setMayConfirm] = useState(false)
  const owner = mayConfirm && project?.role === 'owner'
  const [restoreConfirmed, setRestoreConfirmed] = useState(false)
  const [requestId, setRequestId] = useState(() => crypto.randomUUID())
  const submitted = useRef<ImportFunctionTestCasesToZentaoPayload | null>(null)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const preview = useMutation({
    mutationFn: (target: TargetValues) => functionTestingApi.previewFunctionCasePush(suiteId, { ...target, caseIds: caseIds.length ? caseIds : undefined }),
    onSuccess: data => {
      if (!alive.current) return
      setItems(data.items)
      setRestoreRequired(Boolean(data.restoreRequired))
      setMayConfirm(Boolean(data.canConfirmNotApplied))
      setChoices(Object.fromEntries(data.items.flatMap(item => item.mappedRemoteCaseId ? [[item.caseId, item.mappedRemoteCaseId]] : item.candidates.length ? [] : [[item.caseId, 0]])))
      setPage(1)
      setError('')
    },
    onError: failure => { if (alive.current) setError(getErrorMessage(failure)) },
  })
  const push = useMutation({
    mutationFn: (body: ImportFunctionTestCasesToZentaoPayload) => functionTestingApi.importFunctionTestCasesToZentao(suiteId, body),
    onSuccess: result => {
      if (!alive.current) return
      const succeeded = result.importedCaseCount ?? 0
      setFeedback(result.status === 'success' ? `已推送 ${succeeded} 条用例` : `已推送 ${succeeded} 条，部分用例未完成。请查看下方结果。`)
      const results = new Map(result.items?.map(item => [item.caseId, item]))
      setItems(current => current?.map(item => ({ ...item, operation: results.get(item.caseId) ?? item.operation })) ?? null)
      setError('')
    },
    onError: failure => {
      if (alive.current) setError(`${getErrorMessage(failure)}。可用原请求重试查询结果，系统不会重复发放写许可。`)
    },
  })
  const reconcile = useMutation({
    mutationFn: ({ operationId, body }: { operationId: string; body: CasePushReconcilePayload }) => functionTestingApi.reconcileFunctionCasePush(suiteId, operationId, body),
    onSuccess: () => {
      if (!alive.current) return
      setReview(null)
      setFeedback('核对已保存。重新预览后可发起新的推送。')
      if (values) preview.mutate(values)
    },
    onError: failure => { if (alive.current) setError(getErrorMessage(failure)) },
  })
  const busy = preview.isPending || push.isPending || reconcile.isPending
  const blocked = items?.some(item => unresolved(item.operation)) ?? false
  const missing = items?.some(item => choices[item.caseId] === undefined && !item.mappedRemoteCaseId) ?? true
  const canPush = Boolean(items?.length) && !blocked && !missing && !busy && (!restoreRequired || (restoreConfirmed && owner))
  const actionLabel = !items ? '预览并核对' : attempted ? '用原请求查询／重试' : '确认推送'

  function loadPreview(target: TargetValues) {
    setValues(target)
    setItems(null)
    setReview(null)
    setFeedback('')
    setAttempted(false)
    setRestoreConfirmed(false)
    setRequestId(crypto.randomUUID())
    submitted.current = null
    preview.mutate(target)
  }
  function submit() {
    if (!values || !canPush) return
    const body = submitted.current ?? { ...values, choices, requestId, ...(restoreRequired ? { restoreConfirmed } : {}), caseIds: caseIds.length ? caseIds : undefined }
    submitted.current = body
    setAttempted(true)
    push.mutate(body)
  }
  return <ProjectActionModal
    open action="execute" projectId={projectId} title="导入到禅道" width={960}
    cancelText="关闭" onCancel={() => { if (!busy) onClose() }}
    okText={actionLabel}
    confirmLoading={busy} okButtonProps={{ 'aria-label': actionLabel, disabled: items ? !canPush || Boolean(feedback) : busy }}
    onOk={() => { if (!items) form.submit(); else submit() }}
    mask={{ closable: false }} destroyOnHidden
  >
    <div className="case-push-body">
      {error && <Alert showIcon type="error" title="操作未完成" description={error} />}
      {feedback && <Alert showIcon type={blocked ? 'warning' : 'info'} title={blocked ? '推送未全部完成' : '推送结果'} description={feedback} />}
      {!items ? <>
        <Typography.Paragraph>本次选择 {count} 条用例。先预览远端候选，再确认推送。同名用例不会自动覆盖。</Typography.Paragraph>
        <Form form={form} layout="vertical" initialValues={values ?? { productId: 1, moduleId: 0 }} onFinish={loadPreview}>
          <Form.Item name="productId" label="禅道产品 ID" rules={[{ required: true, type: 'number', min: 1, message: '请输入大于 0 的产品 ID' }]}>
            <InputNumber min={1} precision={0} disabled={busy} />
          </Form.Item>
          <Form.Item name="moduleId" label="禅道模块 ID"><InputNumber min={0} precision={0} disabled={busy} /></Form.Item>
        </Form>
      </> : <>
        <div className="case-push-toolbar">
          <Typography.Text>产品 {values?.productId} · 模块 {values?.moduleId} · {items.length} 条用例</Typography.Text>
          <Space wrap>
            <Button disabled={busy} onClick={() => { setItems(null); setFeedback(''); setError('') }}>修改目标</Button>
            <Button disabled={busy} onClick={() => { if (values) loadPreview(values) }}>重新预览</Button>
          </Space>
        </div>
        {restoreRequired && <Alert showIcon type="warning" title="数据库恢复后的远端核对" description={<Checkbox checked={restoreConfirmed} disabled={busy || attempted || !owner} onChange={event => setRestoreConfirmed(event.target.checked)}>项目所有者确认：已核对这些用例在恢复前的远端写入及当前选择。</Checkbox>} />}
        {blocked && <Alert showIcon type="warning" title="存在未决写入，暂不能推送" description="关闭或刷新页面不会解除锁定。请在对应行核对原操作结果。" />}
        <Table<CasePushPreviewItem> tableLayout="fixed" rowKey="caseId" pagination={false} dataSource={items.slice((page - 1) * pageSize, page * pageSize)} scroll={{ x: 720 }} columns={[
          { title: '平台用例', key: 'title', width: 260, ellipsis: true, render: (_, item) => <Typography.Text className="case-push-title" ellipsis={{ tooltip: item.title }}>{item.title}</Typography.Text> },
          { title: '推送方式', key: 'choice', width: 260, render: (_, item) => item.mappedRemoteCaseId
            ? <Typography.Text>更新已绑定用例 #{item.mappedRemoteCaseId}</Typography.Text>
            : <Select aria-label={`推送方式：${item.title}`} className="case-push-choice" placeholder="请选择绑定已有用例或新建" value={choices[item.caseId]} disabled={busy || attempted || unresolved(item.operation)} onChange={value => setChoices(current => ({ ...current, [item.caseId]: value }))} options={[
              { value: 0, label: '新建独立用例' }, ...item.candidates.map(candidate => ({ value: candidate.id, label: `绑定 #${candidate.id} · ${candidate.title}` })),
            ]} /> },
          { title: '结果', key: 'result', render: (_, item) => <Space orientation="vertical" size={4}>
            <Typography.Text>{item.operation?.status === 'success' ? '已完成' : unresolved(item.operation) ? '待核对' : item.operation?.status === 'failed' ? '未完成' : item.operation?.status === 'skipped' ? '未推送' : '待确认'}</Typography.Text>
            {item.operation?.errorMessage && <Typography.Text type="secondary">{item.operation.errorMessage}</Typography.Text>}
            {unresolved(item.operation) && item.operation?.operationId && <Button disabled={busy} onClick={() => { setReview(item); setError('') }}>核对结果</Button>}
          </Space> },
        ]} />
        {review && <CasePushReview key={review.caseId} item={review} owner={owner} busy={busy} onClose={() => setReview(null)} onConfirm={body => {
          if (review.operation?.operationId) reconcile.mutate({ operationId: review.operation.operationId, body })
        }} />}
      </>}
    </div>
    {items && <div className="table-footer"><ListPagination current={page} pageSize={pageSize} total={items.length} loading={busy} onChange={(next, size) => { setPage(next); setPageSize(size) }} /></div>}
  </ProjectActionModal>
}
