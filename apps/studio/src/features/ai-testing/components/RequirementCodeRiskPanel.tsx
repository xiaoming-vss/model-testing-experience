import { ActionButton } from '@/shared/components/ActionButton'
import { ListPagination } from '@/shared/components/ListPagination'
import { Alert, Button, Empty, Modal, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { CodeRiskReportView } from './CodeRiskReportView'
import { RunArtifacts } from './RunPipelineStatus'
import { RunHistoryTable, RunRowActions } from './RunHistoryTable'
import { RunListStatus } from './RunListStatus'
import type { RequirementCodeRiskWorkspace } from '../hooks/useRequirementCodeRiskWorkspace'
import { confirmDeleteRun, isRunDeletable } from '../utils/runDeletion'
import { aiTestingApi } from '../api/aiTesting.api'
import type { RunPipelineStageKey } from '../utils/runPipeline'
import { getErrorMessage } from '@/utils/format'

const STAGES: RunPipelineStageKey[] = ['generate']

/** 需求详情「代码风险」页签的运行历史，与设计类页签共用列表外观与分页。 */
export function RequirementCodeRiskPanel({ workspace, canWrite }: {
  workspace: RequirementCodeRiskWorkspace
  canWrite: boolean
}) {
  const [reportRunId, setReportRunId] = useState<string>()
  const [errorContent, setErrorContent] = useState<string>()
  const reportQuery = useQuery({
    queryKey: ['codeRiskRun', reportRunId],
    queryFn: () => aiTestingApi.getCodeRiskRun(reportRunId!),
    enabled: Boolean(reportRunId),
  })
  const report = reportQuery.data
  const pagination = {
    current: workspace.page, pageSize: workspace.pageSize, total: workspace.total,
    loading: workspace.runsFetching,
    onChange: (next: number, size: number) => { workspace.setPage(size === workspace.pageSize ? next : 1); workspace.setPageSize(size) },
  }
  return <>
    {workspace.personalLlm.dialog}
    {workspace.personalGitlab.dialog}
    {workspace.runsError ? <Alert showIcon type="error" title={getErrorMessage(workspace.runsError)} action={<Button onClick={workspace.refresh}>重试读取</Button>} /> : null}
    <section className="ai-requirement-design-history">
      {workspace.runsLoading ? <Spin /> : workspace.pagedRows.length ? <RunHistoryTable appearance="list" className="tp-list-table" rows={workspace.pagedRows} getRunId={row => row.runId} selectedRunId={workspace.selectedRunId}
        resolveRow={row => row} onSelect={workspace.setSelectedRunId} pagination={pagination}
        getCreatedAt={row => row.createdAt}
        renderStatus={row => <RunListStatus run={row} stages={STAGES}
          stageTag={row.currentStage && row.currentStage !== 'completed' ? <span className="tp-tone-tag tone-slate">代码风险分析</span> : undefined} />}
        renderArtifacts={row => <RunArtifacts artifacts={[{ key: 'report', label: '分析报告', available: Boolean(row.hasResult) }]} onOpen={() => setReportRunId(row.runId)} />}
        renderActions={row => <RunRowActions inline={<>
          {['failed', 'error'].includes(row.status ?? '') && row.errorMessage ? <Button size="small" onClick={event => { event.stopPropagation(); setErrorContent(row.errorMessage) }}>错误信息</Button> : null}
          {canWrite ? <ActionButton operation="delete" iconOnly size="small" aria-label="删除运行记录" disabled={!isRunDeletable(row.status) || workspace.remove.isPending}
            onClick={event => { event.stopPropagation(); confirmDeleteRun(() => workspace.remove.mutate(row.runId!)) }} /> : null}
        </>} />} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前类型暂无运行记录" />}
      {workspace.runsLoading ? null : !workspace.pagedRows.length ? <div className="table-footer"><ListPagination {...pagination} /></div> : null}
    </section>
    <Modal title="分析报告" open={reportRunId !== undefined} onCancel={() => setReportRunId(undefined)} footer={<Button onClick={() => setReportRunId(undefined)}>关闭</Button>} width={960}>
      {reportQuery.isPending ? <Spin /> : report ? (
        report.report ? <CodeRiskReportView report={report.report} />
          : report.resultYaml ? <pre className="ai-task-code-block">{report.resultYaml}</pre>
          : <Empty description="该运行没有报告内容" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : <Empty description="报告读取失败" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    </Modal>
    <Modal title="错误信息" open={errorContent !== undefined} onCancel={() => setErrorContent(undefined)} footer={<Button onClick={() => setErrorContent(undefined)}>关闭</Button>}><pre style={{ whiteSpace: 'pre-wrap', maxHeight: '60dvh', overflow: 'auto' }}>{errorContent}</pre></Modal>
  </>
}
