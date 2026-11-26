import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Drawer, Popconfirm, Space, Table, Tag } from 'antd'
import { useState } from 'react'
import { listItems, listTotal } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import { isRunInProgress, runStatusMeta } from '@/domain/runs/status'
import { projectsApi } from '@/domain/projects/api/projects.api'
import { useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import type { TestReportGenerateRun } from '@/domain/projects/types'
import { getRunId } from '../utils/sprintReport'

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
    <Table<TestReportGenerateRun> rowKey={run => getRunId(run) || `${run.createdAt ?? ''}-${run.status ?? ''}`} size="small" loading={query.isFetching} dataSource={listItems(query.data)}
      locale={{ emptyText: '暂无报告记录' }} pagination={{ current: page, pageSize: 20, total: listTotal(query.data), onChange: setPage, showSizeChanger: false }}
      columns={[
        { title: '生成时间', key: 'created', render: (_, run) => formatTime(run.createdAt) },
        { title: '状态', key: 'status', render: (_, run) => <div><Tag color={runStatusMeta(run.status).color}>{runStatusMeta(run.status).label}</Tag>{run.errorMessage ? <div role="note">{run.errorMessage}</div> : null}</div> },
        { title: '操作', key: 'actions', render: (_, run) => <Space>
          <Button type="link" size="small" disabled={run.status !== 'success' || !getRunId(run)} onClick={() => onView(run)}>查看</Button>
          {can('write') ? <Popconfirm title="删除这条报告记录？" description="删除后无法恢复。" onConfirm={() => remove.mutate(getRunId(run))} okText="删除" cancelText="取消" disabled={!getRunId(run) || isRunInProgress(run.status) || remove.isPending}>
            <Button type="link" size="small" danger disabled={!getRunId(run) || isRunInProgress(run.status) || remove.isPending}>删除</Button>
          </Popconfirm> : null}
        </Space> },
      ]} />
  </Drawer>
}
