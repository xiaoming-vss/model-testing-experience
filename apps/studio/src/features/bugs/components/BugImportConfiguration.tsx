import { useState } from 'react'
import { Alert, Button, Select, Space, Table, Tag, Tooltip } from 'antd'
import type { ZentaoBugImportPreview } from '../types'
import { BUG_PRIORITY_LABELS, BUG_SEVERITY_LABELS } from '../utils/bugMeta'

export type ImportChoice = { assigneeUserId: string; foundSprintId: string; severity?: string; priority?: string }
type Option = { value: string; label: string }
type Props = {
  selected: number[]
  choices: Record<number, ImportChoice>
  previews: Map<number, ZentaoBugImportPreview>
  members: Option[]
  sprints: Option[]
  sprintFor: (id: number) => string
  ready: number[]
  busy: boolean
  loading: boolean
  error?: string
  onRetry: () => void
  onChange: (ids: number[], patch: Partial<ImportChoice>) => void
}

export function BugImportConfiguration({ selected, choices, previews, members, sprints, sprintFor,
  ready, busy, loading, error, onRetry, onChange }: Props) {
  const [bulkAssignee, setBulkAssignee] = useState<string>()
  const [bulkSprint, setBulkSprint] = useState<string>()
  const apply = () => onChange(selected, {
    ...(bulkAssignee ? { assigneeUserId: bulkAssignee } : {}),
    ...(bulkSprint ? { foundSprintId: bulkSprint } : {}),
  })
  return <div className="bug-import-step">
    <Space wrap className="bug-import-bulk">
      <span>批量设置</span>
      <Select aria-label="批量责任人" placeholder="平台责任人" options={members} showSearch
        optionFilterProp="label" allowClear value={bulkAssignee} onChange={setBulkAssignee} disabled={busy} />
      <Select aria-label="批量发现迭代" placeholder="发现迭代" options={sprints} allowClear
        value={bulkSprint} onChange={setBulkSprint} disabled={busy} />
      <Button disabled={busy || (!bulkAssignee && !bulkSprint)} onClick={apply}>应用到全部 {selected.length} 条</Button>
    </Space>
    {error && <Alert type="error" showIcon title={error} action={<Button onClick={onRetry} disabled={busy}>重试预览</Button>} />}
    <div className="bug-import-scroll">
      <Table<number> size="small" rowKey={id => id} dataSource={selected} pagination={false}
        loading={loading} scroll={{ x: 860 }} columns={[
          { title: 'Bug', key: 'bug', width: 320, render: (_, id) => {
            const title = `#${id} ${previews.get(id)?.title || ''}`
            return <Tooltip title={title}><span className="bug-import-title">{title}</span></Tooltip>
          } },
          { title: '平台责任人', key: 'assignee', width: 170, render: (_, id) => <Select
            aria-label={`责任人-${id}`} placeholder="选择平台责任人" options={members} showSearch optionFilterProp="label"
            value={choices[id]?.assigneeUserId || undefined} disabled={busy}
            onChange={value => onChange([id], { assigneeUserId: value })} /> },
          { title: '发现迭代', key: 'sprint', width: 170, render: (_, id) => <Select
            aria-label={`发现迭代-${id}`} placeholder="选择发现迭代" options={sprints}
            value={sprintFor(id) || undefined} disabled={busy}
            onChange={value => onChange([id], { foundSprintId: value })} /> },
          { title: '检查结果', key: 'check', width: 200, render: (_, id) => {
            const item = previews.get(id)
            const choice = choices[id]
            if (!item) return <span>{error ? '预览失败' : '等待预览'}</span>
            const missing = [!choice?.assigneeUserId && '未分配责任人', !sprintFor(id) && '未选择发现迭代',
              !item.converted.severity && !choice?.severity && '待补严重程度',
              !item.converted.priority && !choice?.priority && '待补优先级'].filter(Boolean)
            return <Space orientation="vertical" size={4} className="bug-import-check">
              {ready.includes(id) ? <Tag color="success">可导入</Tag>
                : <span>{item.state !== 'ready' ? item.errorMessage || item.pending.map(p => p.reason).join('；') : missing.join('；')}</span>}
              {item.converted.severity == null && <Select aria-label={`严重程度-${id}`} placeholder="补充严重程度"
                options={Object.entries(BUG_SEVERITY_LABELS).map(([value, label]) => ({ value, label }))}
                value={choice?.severity} disabled={busy} onChange={value => onChange([id], { severity: value })} />}
              {item.converted.priority == null && <Select aria-label={`优先级-${id}`} placeholder="补充优先级"
                options={Object.entries(BUG_PRIORITY_LABELS).map(([value, label]) => ({ value, label }))}
                value={choice?.priority} disabled={busy} onChange={value => onChange([id], { priority: value })} />}
            </Space>
          } },
        ]} />
    </div>
  </div>
}
