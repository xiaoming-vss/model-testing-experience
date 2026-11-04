import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Drawer, Popconfirm, Space, Table, Tag } from 'antd'
import { useState } from 'react'
import { listItems, listTotal } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import { projectsApi } from '../api/projects.api'
import { useProjectAccess } from '../hooks/useProjectAccess'
import type { TestReportGenerateRun } from '../types'

const statusLabels: Record<string, string> = {
  pending: '待执行', queued: '排队中', claimed: '已领取', running: '生成中',
  success: '成功', failed: '失败', error: '异常', canceled: '已取消', waiting_review: '待审核',
}
const activeStatuses = new Set(['pending', 'queued', 'claimed', 'running', 'waiting_review', 'stopping'])
const idOf = (run: TestReportGenerateRun) => run.runId ?? run.run_id ?? ''

export function TestReportHistoryDrawer({ open, projectId, sprintId, onClose, onView }: {
  open: boolean; projectId: string; sprintId: string; onClose: () => void
  onView: (run: TestReportGenerateRun) => void
}) {
  const [page, setPage] = useState(1)
  const client = useQueryClient()
  const { can } = useProjectAccess(projectId)
  const query = useQuery({
    queryKey: ['testReportGenerateRuns', projectId, sprintId, 'history', page],
    queryFn: () => projectsApi.getTestReportGenerateRuns(projectId, { sprintId, page, pageSize: 20 }),
    enabled: open && Boolean(projectId && sprintId),
  })
  const remove = useMutation({
    mutationFn: projectsApi.deleteTestReportGenerateRun,
    onSuccess: () => {
      message.success('报告记录已删除')
      void client.invalidateQueries({ queryKey: ['testReportGenerateRuns', projectId, sprintId] })
      if (page > 1 && listItems(query.data).length === 1) setPage(page - 1)
    },
    onError: error => message.error(getErrorMessage(error)),
  })
  return <Drawer title="测试报告历史" open={open} onClose={onClose} size="min(760px, 100vw)" destroyOnHidden>
    {query.error ? <Alert type="error" showIcon title={getErrorMessage(query.error)} action={<Button onClick={() => void query.refetch()}>重试</Button>} /> : null}
    <Table<TestReportGenerateRun> rowKey={run => idOf(run) || `${run.createdAt ?? run.created_at ?? ''}-${run.status ?? ''}`} size="small" loading={query.isFetching} dataSource={listItems(query.data)}
      locale={{ emptyText: '暂无报告记录' }} pagination={{ current: page, pageSize: 20, total: listTotal(query.data), onChange: setPage, showSizeChanger: false }}
      columns={[
        { title: '生成时间', key: 'created', render: (_, run) => formatTime(run.createdAt ?? run.created_at) },
        { title: '状态', key: 'status', render: (_, run) => <div><Tag>{statusLabels[run.status ?? ''] ?? run.status ?? '未知'}</Tag>{run.errorMessage || run.error_message ? <div role="note">{run.errorMessage ?? run.error_message}</div> : null}</div> },
        { title: '操作', key: 'actions', render: (_, run) => <Space>
          <Button type="link" size="small" disabled={run.status !== 'success' || !idOf(run)} onClick={() => onView(run)}>查看</Button>
          {can('write') ? <Popconfirm title="删除这条报告记录？" description="删除后无法恢复。" onConfirm={() => remove.mutate(idOf(run))} okText="删除" cancelText="取消" disabled={!idOf(run) || activeStatuses.has(run.status ?? '') || remove.isPending}>
            <Button type="link" size="small" danger disabled={!idOf(run) || activeStatuses.has(run.status ?? '') || remove.isPending}>删除</Button>
          </Popconfirm> : null}
        </Space> },
      ]} />
  </Drawer>
}
