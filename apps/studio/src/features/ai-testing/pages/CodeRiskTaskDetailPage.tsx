import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ArrowLeftOutlined, DownOutlined, RightOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Space, Spin, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import '@/features/ai-testing/styles/index.css'
import { CodeRiskReportView } from '@/features/ai-testing/components/CodeRiskReportView'
import { RunPipelineStatus } from '@/features/ai-testing/components/RunPipelineStatus'
import { RunHistoryTable } from '@/features/ai-testing/components/RunHistoryTable'
import { LlmConnectionSelectModal } from '@/features/ai-testing/components/LlmConnectionSelectModal'
import { getApiCaseGenerateTaskRunStatusMeta, isApiCaseGenerateTaskRunInProgress } from '@/features/ai-testing/utils/taskStatus'
import { api, listItems, type CodeRiskTaskRun } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage, pickCreatedAt, pickUpdatedAt } from '@/utils/format'

const { Title } = Typography

function getRunSortTime(run: CodeRiskTaskRun) {
  const time = new Date(run.createdAt || run.startedAt || run.updatedAt || '').getTime()
  return Number.isNaN(time) ? 0 : time
}

function isRunFailed(status?: string) {
  return status === 'failed' || status === 'error'
}

export function CodeRiskTaskDetailPage() {
  const { taskId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const personalGitlab = usePersonalConnectionChoice('gitlab')
  const [llmSelectOpen, setLlmSelectOpen] = useState(false)
  const [expandedSection, setExpandedSection] = useState<'instruction' | 'runHistory' | 'report'>('runHistory')
  const [selectedRunRecordId, setSelectedRunRecordId] = useState<string | null>(null)

  const taskQuery = useQuery({
    queryKey: ['codeRiskTask', taskId],
    queryFn: () => api.getCodeRiskTask(taskId),
    enabled: Boolean(taskId),
  })
  const task = taskQuery.data
  const taskRequirementQuery = useQuery({
    queryKey: ['requirement', task?.requirementId],
    queryFn: () => api.getRequirement(task!.requirementId!),
    enabled: Boolean(task?.requirementId),
  })
  const taskSprintQuery = useQuery({
    queryKey: ['sprint', task?.sprintId],
    queryFn: () => api.getSprint(task!.sprintId!),
    enabled: Boolean(task?.sprintId),
  })

  const runsQuery = useQuery({
    queryKey: ['codeRiskTaskRuns', taskId],
    queryFn: () => api.getCodeRiskTaskRuns(taskId),
    enabled: Boolean(taskId),
    refetchInterval: (query) =>
      query.state.data && listItems(query.state.data).some((run) => isApiCaseGenerateTaskRunInProgress(run.status)) ? 5000 : false,
  })
  const runRecords = useMemo(
    () => [...listItems(runsQuery.data)].sort((left, right) => getRunSortTime(right) - getRunSortTime(left)),
    [runsQuery.data],
  )
  const selectedRunId = selectedRunRecordId ?? runRecords[0]?.runId ?? ''
  const selectedRunQuery = useQuery({
    queryKey: ['codeRiskRun', selectedRunId],
    queryFn: () => api.getCodeRiskRun(selectedRunId),
    enabled: Boolean(selectedRunId),
    refetchInterval: (query) => (query.state.data && isApiCaseGenerateTaskRunInProgress(query.state.data.status) ? 5000 : false),
  })
  const selectedRun = selectedRunQuery.data
  const resolveRunRecord = (record: CodeRiskTaskRun) =>
    record.runId === selectedRunId && selectedRun ? selectedRun : record
  const runStatusMeta = getApiCaseGenerateTaskRunStatusMeta(selectedRun?.status)
  const selectedRunFailed = isRunFailed(selectedRun?.status)

  useEffect(() => {
    if (selectedRunRecordId) return
    const latest = runRecords[0]?.runId
    if (latest) setSelectedRunRecordId(latest)
  }, [runRecords, selectedRunRecordId])

  const runTaskMutation = useMutation({
    mutationFn: async (connectionId: string) => api.runCodeRiskTask(taskId, { llmConnectionId: connectionId, triggerType: 'manual', gitlabConnectionIds: await personalGitlab.forRequirement(task!.projectId!, task!.requirementId!) }),
    onSuccess: (run) => {
      message.success('任务已加入执行队列')
      setLlmSelectOpen(false)
      queryClient.invalidateQueries({ queryKey: ['codeRiskTaskRuns', taskId] })
      if (run.runId) setSelectedRunRecordId(run.runId)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const menuItemClass = (section: 'instruction' | 'runHistory' | 'report') =>
    `ai-task-detail-fold-trigger${expandedSection === section ? ' expanded' : ''}`

  return (<ProjectAccessScope resourceError={taskQuery.error} projectId={task?.projectId ?? ''}>{(
    <div className="workbench-page ai-testing-page">
      {taskQuery.error ? <Alert showIcon type="error" title={getErrorMessage(taskQuery.error)} /> : null}
      {taskQuery.isLoading ? (
        <div className="sprint-card-loading">
          <Empty description="任务加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      ) : null}

      {task ? (
        <>
          <div className="ai-task-detail-layout">
            <Card className="ai-task-detail-summary-card" size="small">
              <div className="ai-task-detail-inline-meta">
                <span className="ai-task-detail-inline-item">
                  <span className="ai-task-detail-inline-label">返回</span>
                  <span className="ai-task-detail-inline-value">
                    <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/ai-testing/tasks')}>
                      返回任务列表
                    </Button>
                  </span>
                </span>
                <span className="ai-task-detail-inline-item">
                  <span className="ai-task-detail-inline-label">任务</span>
                  <span className="ai-task-detail-inline-value">
                    <Space size={8}>
                      <Title level={4} className="ai-task-detail-summary-title" style={{ margin: 0 }}>
                        {task.name || '未命名任务'}
                      </Title>
                      <Tag color="geekblue">代码风险分析</Tag>
                      <Tag color={runStatusMeta.color}>{runStatusMeta.label}</Tag>
                    </Space>
                  </span>
                </span>
                <span className="ai-task-detail-inline-item">
                  <span className="ai-task-detail-inline-label">所属需求</span>
                  <span className="ai-task-detail-inline-value">
                    {taskRequirementQuery.data?.name ?? task.requirementId ?? '-'}
                  </span>
                </span>
                <span className="ai-task-detail-inline-item">
                  <span className="ai-task-detail-inline-label">所属迭代</span>
                  <span className="ai-task-detail-inline-value">{taskSprintQuery.data?.name ?? task.sprintId ?? '-'}</span>
                </span>
                <span className="ai-task-detail-inline-item">
                  <span className="ai-task-detail-inline-label">创建时间</span>
                  <span className="ai-task-detail-inline-value">{formatTime(pickCreatedAt(task) || task.createdAt)}</span>
                </span>
                <span className="ai-task-detail-inline-item">
                  <span className="ai-task-detail-inline-label">更新时间</span>
                  <span className="ai-task-detail-inline-value">{formatTime(pickUpdatedAt(task) || task.updatedAt)}</span>
                </span>
                <span className="ai-task-detail-inline-actions">
                  <ProjectActionButton action="execute"
                    type="primary"
                    className="action-btn-create"
                    onClick={() => setLlmSelectOpen(true)}
                    disabled={runRecords.length > 0 && isApiCaseGenerateTaskRunInProgress(runRecords[0].status)}
                  >
                    发起运行
                  </ProjectActionButton>
                </span>
              </div>
            </Card>

            <Card
              className={`ai-task-detail-card ai-task-detail-fold-card ai-task-detail-fold-card-instruction${expandedSection === 'instruction' ? ' expanded' : ' collapsed'}`}
              title={
                <button type="button" className={menuItemClass('instruction')} onClick={() => setExpandedSection('instruction')}>
                  {expandedSection === 'instruction' ? <DownOutlined /> : <RightOutlined />}
                  <span>运行指令</span>
                </button>
              }
              size="small"
            >
              <pre className="ai-task-code-block">{task.instruction || '-'}</pre>
            </Card>

            <Card
              className={`ai-task-detail-card ai-task-detail-fold-card ai-task-detail-fold-card-history${expandedSection === 'runHistory' ? ' expanded' : ' collapsed'}`}
              title={
                <button type="button" className={menuItemClass('runHistory')} onClick={() => setExpandedSection('runHistory')}>
                  {expandedSection === 'runHistory' ? <DownOutlined /> : <RightOutlined />}
                  <span>运行历史</span>
                </button>
              }
              size="small"
            >
              <div className="ai-task-run-history-toolbar">
                <span className="ai-task-run-history-auto-refresh">每 5 秒自动刷新</span>
              </div>
              <div className="ai-task-detail-content-scroll ai-task-run-history-scroll">
                {runsQuery.isLoading ? <Empty description="运行历史加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} /> : null}
                {!runsQuery.isLoading && runRecords.length === 0 ? (
                  <Empty description="暂无运行记录，点击「发起运行」开始分析" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : null}
                {runRecords.length > 0 ? (
                  <RunHistoryTable<CodeRiskTaskRun>
                    rows={runRecords}
                    getRunId={(record) => record.runId}
                    selectedRunId={selectedRunId}
                    resolveRow={resolveRunRecord}
                    onSelect={(runId) => setSelectedRunRecordId(runId ?? null)}
                    renderPrimary={(row, index) => (
                      <span className="ai-task-run-table-id">
                        <span className="ai-task-run-table-index">#{index + 1}</span>
                        <span className="ai-task-run-table-time">{formatTime(pickCreatedAt(row) || row.createdAt)}</span>
                      </span>
                    )}
                    renderStatus={(row) => {
                      const data = resolveRunRecord(row)
                      return (
                        <RunPipelineStatus
                          run={data}
                          stages={['generate']}
                          stageTag={data.currentStage ? <Tag color="default">{data.currentStage}</Tag> : null}
                        />
                      )
                    }}
                  />
                ) : null}
              </div>
            </Card>

            <Card
              className={`ai-task-detail-card ai-task-detail-fold-card ai-task-detail-fold-card-report${expandedSection === 'report' ? ' expanded' : ' collapsed'}`}
              title={
                <button type="button" className={menuItemClass('report')} onClick={() => setExpandedSection('report')}>
                  {expandedSection === 'report' ? <DownOutlined /> : <RightOutlined />}
                  <span>分析报告</span>
                </button>
              }
              size="small"
            >
              {selectedRunQuery.isLoading ? (
                <div className="ai-task-detail-report-loading">
                  <Spin />
                </div>
              ) : !selectedRun ? (
                <Empty description="选择一次运行后查看报告" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <>
                  {selectedRunFailed ? (
                    <Alert
                      showIcon
                      type="error"
                      className="ai-task-detail-report-failure"
                      title={selectedRun.errorMessage || '运行失败'}
                      description={selectedRun.remediation || undefined}
                    />
                  ) : null}
                  {selectedRun.report ? (
                    <CodeRiskReportView report={selectedRun.report} />
                  ) : selectedRun.resultYaml ? (
                    <pre className="ai-task-code-block ai-task-detail-result-yaml">{selectedRun.resultYaml}</pre>
                  ) : (
                    <Empty description="该运行没有报告内容" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  )}
                  {selectedRun.remediation && !selectedRunFailed ? (
                    <Alert showIcon type="info" title={selectedRun.remediation} />
                  ) : null}
                </>
              )}
            </Card>
          </div>
        </>
      ) : null}

      {personalGitlab.dialog}
      <LlmConnectionSelectModal
        open={llmSelectOpen}
        projectId={task?.projectId ?? ''}
        onClose={() => setLlmSelectOpen(false)}
        onConfirm={(connectionId) => runTaskMutation.mutate(connectionId)}
        loading={runTaskMutation.isPending}
      />
    </div>
  )}</ProjectAccessScope>)
}
