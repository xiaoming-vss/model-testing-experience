import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Input, Modal, Select, Space, Steps, Table, Tag, Typography } from 'antd'
import { getErrorMessage } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { ListPagination } from '@/shared/components/ListPagination'
import { BugImportConfiguration, type ImportChoice } from './BugImportConfiguration'
import '../styles/bug-import.css'
import { bugsApi } from '../api/bugs.api'
import type {
  ZentaoBugCandidate,
  ZentaoBugImportPreview,
  ZentaoBugImportResult,
  ZentaoBugPendingItem,
} from '../types'
import {
  BUG_STATUS_LABELS,
  ZENTAO_PRIORITY_LABELS,
  ZENTAO_SEVERITY_LABELS,
} from '../utils/bugMeta'

type Props = {
  open: boolean
  projectId: string
  /** 当前迭代：候选按其绑定的执行整套查询，发现迭代默认预填。 */
  defaultSprintId?: string | null
  onClose: () => void
}

const MAX_IMPORT_SELECTION = 20

const RESULT_LABELS: Record<string, string> = {
  success: '导入成功',
  already_linked: '已存在关联',
  conflict: '已被其他项目关联',
  pending: '待文件管线',
  failed: '导入失败',
}

// 候选列表展示禅道原始值：可映射时给出平台标签并保留编号便于核对（R23）。
const severityText = (value: string) => {
  if (!value) return '—'
  const label = ZENTAO_SEVERITY_LABELS[value] ?? ''
  return label ? `${label} (${value})` : value
}
const priorityText = (value: string) => {
  if (!value) return '—'
  const label = ZENTAO_PRIORITY_LABELS[value] ?? ''
  return label ? `${label} (${value})` : value
}

function pendingText(items: ZentaoBugPendingItem[]) {
  return items.map((item) => item.reason).join('；')
}

export function BugZentaoImportModal({ open, projectId, defaultSprintId, onClose }: Props) {
  const client = useQueryClient()
  const [step, setStep] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [status, setStatus] = useState('')
  const [keyword, setKeyword] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const [choices, setChoices] = useState<Record<number, ImportChoice>>({})
  const [results, setResults] = useState<ZentaoBugImportResult[] | null>(null)
  const [importing, setImporting] = useState(false)

  const candidates = useQuery({
    queryKey: ['zentaoBugCandidates', projectId, defaultSprintId, page, pageSize, status, keyword, open],
    queryFn: () =>
      bugsApi.listZentaoBugCandidates(projectId, {
        sprintId: defaultSprintId || undefined,
        page,
        pageSize,
        status,
        keyword,
      }),
    enabled: open && !!projectId,
    staleTime: 0,
    refetchOnWindowFocus: false,
  })
  const options = useQuery({
    queryKey: ['bugOptions', projectId],
    queryFn: () => bugsApi.getBugOptions(projectId),
    enabled: open && !!projectId,
    staleTime: 0,
    refetchOnWindowFocus: false,
  })
  const previews = useQuery({
    queryKey: ['zentaoBugImportPreview', projectId, selected],
    queryFn: () => bugsApi.previewZentaoBugImport(projectId, selected),
    enabled: open && selected.length > 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
  })
  const previewById = useMemo(() => {
    const map = new Map<number, ZentaoBugImportPreview>()
    for (const item of previews.data?.items ?? []) map.set(item.remoteBugId, item)
    return map
  }, [previews.data])

  const reset = () => {
    setStep(0)
    setSelected([])
    setResults(null)
    setChoices({})
    setPage(1)
    setStatus('')
    setKeyword('')
  }
  const close = () => {
    if (importing) return
    reset()
    onClose()
  }
  const pick = (ids: number[], patch: Partial<ImportChoice>) => {
    setChoices(current => {
      const next = { ...current }
      for (const id of ids) next[id] = { ...(next[id] ?? { assigneeUserId: '', foundSprintId: '' }), ...patch }
      return next
    })
  }
  // 发现迭代优先用绑定解析值，其次当前迭代；责任人必须人工选择（Q05/Q06）。
  const sprintFor = (remoteBugId: number) =>
    choices[remoteBugId]?.foundSprintId ||
    previewById.get(remoteBugId)?.converted.foundSprintId ||
    defaultSprintId ||
    ''
  const readyToImport = selected.filter((id) => {
    const item = previewById.get(id)
    if (!item || !['ready'].includes(item.state)) return false
    return !!choices[id]?.assigneeUserId && !!sprintFor(id)
      && !!(choices[id]?.severity || item.converted.severity)
      && !!(choices[id]?.priority || item.converted.priority)
  })
  const blocked = selected.filter((id) => !readyToImport.includes(id))
  const confirmImport = async () => {
    if (importing || previews.isFetching || previews.isError || options.isError || readyToImport.length === 0) return
    setImporting(true)
    try {
      const response = await bugsApi.importZentaoBugs(projectId, {
        requestId: crypto.randomUUID(),
        items: readyToImport.map((remoteBugId) => ({
          remoteBugId,
          assigneeUserId: choices[remoteBugId].assigneeUserId,
          foundSprintId: sprintFor(remoteBugId),
          ...(choices[remoteBugId].severity ? { severity: choices[remoteBugId].severity } : {}),
          ...(choices[remoteBugId].priority ? { priority: choices[remoteBugId].priority } : {}),
        })),
      })
      setResults(response.items)
      const okCount = response.items.filter((item) => item.status === 'success').length
      if (okCount > 0) {
        message.success(`已导入 ${okCount} 条 Bug`)
        void client.invalidateQueries({ queryKey: ['bugs'] })
        void client.invalidateQueries({ queryKey: ['zentaoBugCandidates'] })
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setImporting(false)
    }
  }

  const columns = [
    {
      title: '禅道编号',
      dataIndex: 'remoteBugId',
      width: 90,
      render: (value: number) => `#${value}`,
    },
    { title: '标题', dataIndex: 'title', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: string) => BUG_STATUS_LABELS[value] || value || '—',
    },
    { title: '严重程度', dataIndex: 'severity', width: 90, render: severityText },
    { title: '优先级', dataIndex: 'priority', width: 80, render: priorityText },
    {
      title: '责任人（禅道）',
      dataIndex: 'assignedTo',
      width: 110,
      render: (value: string) => value || '—',
    },
    {
      title: '平台关联',
      dataIndex: 'linked',
      width: 90,
      render: (linked: boolean) => (linked ? <Tag color="default">已关联</Tag> : <Tag color="blue">可导入</Tag>),
    },
  ]

  return (
    <Modal
      mask={{ closable: false }}
      centered
      title="从禅道导入 Bug"
      open={open}
      width={1040}
      className="bug-import-modal"
      onCancel={close}
      footer={results ? <Button type="primary" onClick={close}>完成</Button> : (
        <div className="bug-import-footer">
          <Typography.Text type="secondary">
            {step === 0 ? `已选 ${selected.length}／${MAX_IMPORT_SELECTION} 条` : `可导入 ${readyToImport.length} 条，待完善 ${blocked.length} 条`}
          </Typography.Text>
          <Space>
            <Button disabled={importing} onClick={step === 0 ? close : () => setStep(0)}>{step === 0 ? '取消' : '上一步'}</Button>
            {step === 0 ? <Button type="primary" disabled={!selected.length} onClick={() => setStep(1)}>下一步</Button>
              : <Button type="primary" disabled={!readyToImport.length || previews.isFetching || previews.isError || options.isError}
                  loading={importing} onClick={() => void confirmImport()}>导入 {readyToImport.length} 条</Button>}
          </Space>
        </div>
      )}
    >
      {!results && <Steps size="small" current={step} items={[{ title: '选择 Bug' }, { title: '确认导入' }]} />}
      {results ? (
        <Space className="bug-import-scroll" orientation="vertical" size="middle" style={{ width: '100%' }}>
          {results.map((item) => (
            <Alert
              key={item.remoteBugId}
              showIcon
              type={item.status === 'success' ? 'success' : item.status === 'failed' || item.status === 'conflict' ? 'error' : 'warning'}

              title={`#${item.remoteBugId} ${item.title || ''}：${RESULT_LABELS[item.status] || item.status}`}
              description={
                <>
                  {item.status === 'success' && <div>平台 Bug：BUG-{item.bugNo}</div>}
                  {item.errorMessage && <div>{item.errorMessage}</div>}
                  {item.pending.length > 0 && <div>{pendingText(item.pending)}</div>}
                </>
              }
            />
          ))}
        </Space>
      ) : step === 0 ? (
        <div className="bug-import-step">
          <Space wrap>
            <Select
              aria-label="候选状态筛选"
              style={{ width: 140 }}
              allowClear
              placeholder="全部状态"
              value={status || undefined}
              options={Object.entries(BUG_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
              onChange={(value) => { setStatus(value ?? ''); setPage(1) }}
            />
            <Input
              aria-label="候选标题搜索"
              style={{ width: 220 }}
              allowClear
              placeholder="搜索禅道标题"
              value={keyword}
              onChange={(event) => { setKeyword(event.target.value); setPage(1) }}
            />
          </Space>
          {candidates.data && (
            <Alert
              type="info"
              showIcon
              title={
                candidates.data.scope === 'execution'
                  ? `候选范围：当前迭代绑定的禅道执行 #${candidates.data.executionId}`
                  : '候选范围：整个禅道项目（未按迭代过滤）'
              }
            />
          )}
          {candidates.error && (
            <Alert showIcon type="error" title={getErrorMessage(candidates.error)}
              action={<Button onClick={() => candidates.refetch()}>重试</Button>} />
          )}
          <Typography.Text type="secondary">
            已选 {selected.length} 条，每批最多导入 {MAX_IMPORT_SELECTION} 条；每页条数仅控制候选展示。
          </Typography.Text>
          <div className="bug-import-scroll">
          <Table<ZentaoBugCandidate>
            size="small"
            rowKey="remoteBugId"
            loading={candidates.isFetching}
            columns={columns}
            dataSource={candidates.data?.items ?? []}
            pagination={false}
            scroll={{ x: 820 }}
            rowSelection={{
              selectedRowKeys: selected,
              preserveSelectedRowKeys: true,
              onChange: (keys) => {
                const ids = keys.map(Number)
                if (ids.length > MAX_IMPORT_SELECTION) {
                  message.warning(`每批最多导入 ${MAX_IMPORT_SELECTION} 条，已保留前 ${MAX_IMPORT_SELECTION} 条候选`)
                }
                setSelected(ids.slice(0, MAX_IMPORT_SELECTION))
              },
              getCheckboxProps: (row) => ({
                disabled: row.linked || (selected.length >= MAX_IMPORT_SELECTION && !selected.includes(row.remoteBugId)),
              }),
            }}
          />
          </div>
          <div className="table-footer">
            <ListPagination current={page} pageSize={pageSize} total={candidates.data?.total ?? 0}
              loading={candidates.isFetching || candidates.isError}
              onChange={(nextPage, nextSize) => { setPage(nextSize === pageSize ? nextPage : 1); setPageSize(nextSize) }} />
          </div>
        </div>
      ) : (
        <BugImportConfiguration selected={selected} choices={choices} previews={previewById}
          members={(options.data?.members ?? []).map(member => ({ value: member.userId, label: member.name || member.userId }))}
          sprints={(options.data?.sprints ?? []).map(sprint => ({ value: sprint.sprintId, label: sprint.name }))}
          sprintFor={sprintFor} ready={readyToImport} busy={importing} loading={previews.isFetching}
          error={previews.error ? getErrorMessage(previews.error) : options.error ? getErrorMessage(options.error) : undefined}
          onRetry={() => { void previews.refetch(); void options.refetch() }} onChange={pick} />
      )}
    </Modal>
  )
}
