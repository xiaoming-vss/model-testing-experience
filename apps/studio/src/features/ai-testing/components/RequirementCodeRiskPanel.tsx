import { ActionButton } from '@/shared/components/ActionButton'
import { ListPagination } from '@/shared/components/ListPagination'
import { tableFooterClass } from '@/shared/utils/surfaceClasses'
import { Alert, Button, Empty, Modal, Spin, Tooltip } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { CodeRiskReportView } from './CodeRiskReportView'
import { RunArtifacts } from './RunPipelineStatus'
import { RunHistoryTable, RunRowActions } from './RunHistoryTable'
import { RunListStatus } from './RunListStatus'
import type { RequirementCodeRiskWorkspace } from '../hooks/useRequirementCodeRiskWorkspace'
import { confirmDeleteRun, isRunDeletable } from '../utils/runDeletion'
import { aiTestingApi } from '../api/aiTesting.api'
import { getErrorMessage } from '@/utils/format'

/** 需求详情「代码风险」弹窗：发起入口加上按需求汇总的运行历史，历史列表与设计类页签共用外观与分页。 */
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
  const hasRuns = workspace.total > 0
  return <>
    {workspace.personalLlm.dialog}
    {workspace.personalGitlab.dialog}
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--app-surface-divider)] px-4 py-3">
      <span className="text-[12px] leading-[18px] text-[var(--app-surface-text-muted)]">
        运行记录按当前需求汇总；发起时使用当前采用的材料整理。
      </span>
      {/* 禁用原因只在悬停或聚焦时提示，不在弹窗里常驻。 */}
      <Tooltip title={workspace.runDisabledReason}>
        <span>
          <ProjectActionButton action="execute" operation={hasRuns ? 'run' : 'create'} type="primary"
            loading={workspace.start.isPending} disabled={Boolean(workspace.runDisabledReason)}
            onClick={() => workspace.start.mutate()}>
            {hasRuns ? '重新分析' : '发起分析'}
          </ProjectActionButton>
        </span>
      </Tooltip>
    </div>
    {workspace.runsError ? <Alert showIcon type="error" title={getErrorMessage(workspace.runsError)} action={<Button onClick={workspace.refresh}>重试读取</Button>} /> : null}
    <section className="ai-requirement-design-history flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden border-0 rounded-none bg-transparent [&>.ant-empty]:flex [&>.ant-empty]:flex-1 [&>.ant-empty]:flex-col [&>.ant-empty]:items-center [&>.ant-empty]:justify-center [&_.ant-table-wrapper]:m-0 [&_.ant-table-wrapper]:min-h-0 [&_.ant-table-wrapper]:flex-1 [&_.ant-table-wrapper]:overflow-auto [&_.ant-table-wrapper]:p-4">
      {workspace.runsLoading ? <Spin /> : workspace.pagedRows.length ? <RunHistoryTable className="tp-list-table" rows={workspace.pagedRows} getRunId={row => row.runId} selectedRunId={workspace.selectedRunId}
        onSelect={workspace.setSelectedRunId} pagination={pagination}
        getCreatedAt={row => row.createdAt}
        renderStatus={row => <RunListStatus run={row}
          stageTag={row.currentStage && row.currentStage !== 'completed' ? <span className="tp-tone-tag tone-slate">代码风险分析</span> : undefined} />}
        renderArtifacts={row => <RunArtifacts artifacts={[{ key: 'report', label: '分析报告', available: Boolean(row.hasResult) }]} onOpen={() => setReportRunId(row.runId)} />}
        renderActions={row => <RunRowActions inline={<>
          {['failed', 'error'].includes(row.status ?? '') && row.errorMessage ? <Button size="small" onClick={event => { event.stopPropagation(); setErrorContent(row.errorMessage) }}>错误信息</Button> : null}
          {canWrite ? <ActionButton operation="delete" iconOnly size="small" aria-label="删除运行记录" disabled={!isRunDeletable(row.status) || workspace.remove.isPending}
            onClick={event => { event.stopPropagation(); confirmDeleteRun(() => workspace.remove.mutate(row.runId!)) }} /> : null}
        </>} />} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前类型暂无运行记录" />}
      {workspace.runsLoading ? null : !workspace.pagedRows.length ? <div className={`table-footer ${tableFooterClass}`}><ListPagination {...pagination} /></div> : null}
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
