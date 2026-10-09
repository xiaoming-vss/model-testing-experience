import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import { getErrorMessage } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { bugsApi } from '../api/bugs.api'
import type {
  ZentaoBugCandidate,
  ZentaoBugImportPreview,
  ZentaoBugImportResult,
  ZentaoBugPendingItem,
} from '../types'
import {
  BUG_PRIORITY_LABELS,
  BUG_SEVERITY_LABELS,
  BUG_STATUS_LABELS,
  ZENTAO_PRIORITY_LABELS,
  ZENTAO_SEVERITY_LABELS,
} from '../utils/bugMeta'

type Props = {
  open: boolean
  projectId: string
  onClose: () => void
}

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

export function BugZentaoImportModal({ open, projectId, onClose }: Props) {
  const client = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [status, setStatus] = useState('')
  const [keyword, setKeyword] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const [choices, setChoices] = useState<Record<number, { assigneeUserId: string; foundSprintId: string; severity?: string; priority?: string }>>({})
  const [results, setResults] = useState<ZentaoBugImportResult[] | null>(null)
  const [importing, setImporting] = useState(false)

  const candidates = useQuery({
    queryKey: ['zentaoBugCandidates', projectId, page, pageSize, status, keyword, open],
    queryFn: () => bugsApi.listZentaoBugCandidates(projectId, { page, pageSize, status, keyword }),
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
  const pick = (remoteBugId: number, patch: Partial<{ assigneeUserId: string; foundSprintId: string; severity: string; priority: string }>) => {
    setChoices((current) => ({
      ...current,
      [remoteBugId]: {
        ...{ assigneeUserId: '', foundSprintId: '' },
        ...current[remoteBugId],
        ...patch,
      },
    }))
  }
  // 发现迭代允许使用预览解析出的绑定预填；责任人必须人工选择（Q05/Q06）。
  const sprintFor = (remoteBugId: number) =>
    choices[remoteBugId]?.foundSprintId || previewById.get(remoteBugId)?.converted.foundSprintId || ''
  const readyToImport = selected.filter((id) => {
    const item = previewById.get(id)
    if (!item || !['ready'].includes(item.state)) return false
    return !!choices[id]?.assigneeUserId && !!sprintFor(id)
  })
  const blocked = selected.filter((id) => !readyToImport.includes(id))

  const confirmImport = async () => {
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
      title="从禅道导入 Bug"
      open={open}
      width={920}
      onCancel={close}
      footer={results ? (
        <Button type="primary" onClick={close}>完成</Button>
      ) : (
        <Space>
          <Button onClick={close}>取消</Button>
          <Button type="primary" disabled={readyToImport.length === 0} loading={importing}
            onClick={() => void confirmImport()}>
            导入 {readyToImport.length > 0 ? `（${readyToImport.length}）` : ''}
          </Button>
        </Space>
      )}
    >
      {results ? (
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
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
      ) : (
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
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
          {candidates.error && (
            <Alert showIcon type="error" title={getErrorMessage(candidates.error)}
              action={<Button onClick={() => candidates.refetch()}>重试</Button>} />
          )}
          <Table<ZentaoBugCandidate>
            size="small"
            rowKey="remoteBugId"
            loading={candidates.isFetching}
            columns={columns}
            dataSource={candidates.data?.items ?? []}
            pagination={{
              current: page, pageSize, total: candidates.data?.total ?? 0,
              onChange: (nextPage, nextSize) => { setPage(nextPage); setPageSize(nextSize) },
              showSizeChanger: false,
            }}
            rowSelection={{
              selectedRowKeys: selected,
              onChange: (keys) => setSelected(keys.map(Number)),
              getCheckboxProps: (row) => ({ disabled: row.linked }),
            }}
          />
          {selected.length > 0 && (
            <div>
              <Typography.Title level={5} style={{ marginTop: 0 }}>导入确认</Typography.Title>
              <Space orientation="vertical" size="small" style={{ width: '100%' }}>
                {selected.map((remoteBugId) => {
                  const item = previewById.get(remoteBugId)
                  const choice = choices[remoteBugId] ?? {}
                  return (
                    <div key={remoteBugId}>
                      <Typography.Text strong>#{remoteBugId} {item?.title || ''}</Typography.Text>
                      <Space wrap style={{ marginLeft: 12 }}>
                        <Select
                          aria-label={`责任人-${remoteBugId}`}
                          placeholder="选择平台责任人"
                          style={{ width: 180 }}
                          showSearch
                          optionFilterProp="label"
                          value={choice.assigneeUserId || undefined}
                          options={(options.data?.members ?? []).map((member) => ({
                            value: member.userId, label: member.name || member.userId,
                          }))}
                          onChange={(value) => pick(remoteBugId, { assigneeUserId: value ?? '' })}
                        />
                        <Select
                          aria-label={`发现迭代-${remoteBugId}`}
                          placeholder="选择发现迭代"
                          style={{ width: 180 }}
                          value={choice.foundSprintId || item?.converted.foundSprintId || undefined}
                          options={(options.data?.sprints ?? []).map((sprint) => ({
                            value: sprint.sprintId, label: sprint.name,
                          }))}
                          onChange={(value) => pick(remoteBugId, { foundSprintId: value ?? '' })}
                        />
                        {item && item.converted.severity == null && (
                          <Select
                            aria-label={`严重程度-${remoteBugId}`}
                            placeholder="严重程度（禅道值待映射）"
                            style={{ width: 160 }}
                            value={choice.severity || undefined}
                            options={Object.entries(BUG_SEVERITY_LABELS).map(([value, label]) => ({ value, label }))}
                            onChange={(value) => pick(remoteBugId, { severity: value ?? '' })}
                          />
                        )}
                        {item && item.converted.priority == null && (
                          <Select
                            aria-label={`优先级-${remoteBugId}`}
                            placeholder="优先级（禅道值待映射）"
                            style={{ width: 160 }}
                            value={choice.priority || undefined}
                            options={Object.entries(BUG_PRIORITY_LABELS).map(([value, label]) => ({ value, label }))}
                            onChange={(value) => pick(remoteBugId, { priority: value ?? '' })}
                          />
                        )}
                      </Space>
                      {item && item.state !== 'ready' && (
                        <Alert
                          style={{ marginTop: 4 }}
                          type={item.state === 'pending_files' ? 'warning' : 'error'}
                          showIcon
                          title={item.errorMessage || pendingText(item.pending)}
                        />
                      )}
                      {item && item.state === 'ready' && item.pending.length > 0 && (
                        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                          {pendingText(item.pending)}
                        </Typography.Paragraph>
                      )}
                      {previews.error && (
                        <Alert type="error" showIcon title={getErrorMessage(previews.error)} />
                      )}
                    </div>
                  )
                })}
                {blocked.length > 0 && (
                  <Alert type="info" showIcon
                    title={`${blocked.length} 条候选尚未满足导入条件（待映射、待选择或含待同步图片），本次不会导入。`} />
                )}
              </Space>
            </div>
          )}
        </Space>
      )}
    </Modal>
  )
}
