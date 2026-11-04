import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Drawer, Popconfirm, Space, Table, Tag } from 'antd'
import { useState } from 'react'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { listItems, listTotal } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import { testOrdersApi } from '../api/testOrders.api'
import type { TestOrderGraphRun } from '../types'

const labels: Record<string, string> = { pending: '待执行', queued: '排队中', claimed: '已领取', running: '生成中', success: '成功', failed: '失败', error: '异常', canceled: '已取消' }
const active = new Set(['pending', 'queued', 'claimed', 'running', 'stopping'])

export function TestOrderGraphHistoryDrawer({ open, orderId, projectId, onClose, onSelect, onDeleted }: {
  open: boolean; orderId: string; projectId?: string; onClose: () => void
  onSelect: (runId: string) => void; onDeleted: (runId: string) => void
}) {
  const [page, setPage] = useState(1)
  const client = useQueryClient()
  const { can } = useProjectAccess(projectId)
  const query = useQuery({
    queryKey: ['testOrderGraphRuns', orderId, page],
    queryFn: () => testOrdersApi.getTestOrderGraphRuns(orderId, { page, pageSize: 20 }),
    enabled: open && Boolean(orderId),
  })
  const remove = useMutation({
    mutationFn: testOrdersApi.deleteTestOrderGraphRun,
    onSuccess: (_, runId) => {
      message.success('图谱记录已删除')
      onDeleted(runId)
      void client.invalidateQueries({ queryKey: ['testOrderGraphRuns', orderId] })
      void client.invalidateQueries({ queryKey: ['testOrderGraph', orderId] })
      if (page > 1 && listItems(query.data).length === 1) setPage(page - 1)
    },
    onError: error => message.error(getErrorMessage(error)),
  })
  return <Drawer title="图谱生成历史" open={open} onClose={onClose} size="min(760px, 100vw)" destroyOnHidden>
    {query.error ? <Alert type="error" showIcon title={getErrorMessage(query.error)} action={<Button onClick={() => void query.refetch()}>重试</Button>} /> : null}
    <Table<TestOrderGraphRun> rowKey={run => run.runId ?? ''} size="small" loading={query.isFetching} dataSource={listItems(query.data)}
      locale={{ emptyText: '暂无图谱记录' }} pagination={{ current: page, pageSize: 20, total: listTotal(query.data), onChange: setPage, showSizeChanger: false }}
      columns={[
        { title: '生成时间', key: 'created', render: (_, run) => formatTime(run.createdAt ?? run.created_at) },
        { title: '状态', key: 'status', render: (_, run) => <Tag>{labels[run.status ?? ''] ?? run.status ?? '未知'}</Tag> },
        { title: '操作', key: 'actions', render: (_, run) => <Space>
          <Button type="link" size="small" disabled={!run.runId} onClick={() => onSelect(run.runId!)}>查看</Button>
          {can('write') ? <Popconfirm title="删除这条图谱记录？" description="删除后无法恢复。" onConfirm={() => remove.mutate(run.runId!)} okText="删除" cancelText="取消" disabled={!run.runId || active.has(run.status ?? '') || remove.isPending}>
            <Button type="link" size="small" danger disabled={!run.runId || active.has(run.status ?? '') || remove.isPending}>删除</Button>
          </Popconfirm> : null}
        </Space> },
      ]} />
  </Drawer>
}
