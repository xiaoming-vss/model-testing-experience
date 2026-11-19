import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Form } from 'antd'
import { useState } from 'react'
import { usePendingRequestId } from '@/shared/hooks/usePendingRequestId'
import { saveBlob } from '@/shared/utils/download'
import { message } from '@/shared/utils/feedback'
import { api, listItems, type TestReportGenerateRun } from '@/services/api'
import {
  getRunId,
  getRunReportMarkdown,
  getRunStatusMeta,
  isTestReportRunGenerating,
  type TestReportGenerateFormValues,
} from '../utils/sprintReport'
import { useQueryErrorToast } from './useQueryErrorToast'

export function useSprintReports({
  projectId,
  sprintId,
  todayDate,
  metricsLoading,
  metricsError,
  metricsHasData,
}: {
  projectId: string
  sprintId: string
  todayDate: string
  metricsLoading: boolean
  metricsError: unknown
  metricsHasData: boolean
}) {
  const queryClient = useQueryClient()
  const [reportDrawerOpen, setReportDrawerOpen] = useState(false)
  const [reportHistoryOpen, setReportHistoryOpen] = useState(false)
  const [reportModalRunId, setReportModalRunId] = useState('')
  const [reportForm] = Form.useForm<TestReportGenerateFormValues>()

  const reportRunsQuery = useQuery({
    queryKey: ['testReportGenerateRuns', projectId, sprintId],
    queryFn: () => api.getTestReportGenerateRuns(projectId, { sprintId }),
    enabled: Boolean(projectId && sprintId),
  })
  useQueryErrorToast(reportRunsQuery.error, `sprint-reports-${sprintId}`)

  const reportRunDetailQuery = useQuery({
    queryKey: ['testReportGenerateRun', reportModalRunId],
    queryFn: () => api.getTestReportGenerateRun(reportModalRunId),
    enabled: Boolean(reportModalRunId),
  })

  const pendingReportRequest = usePendingRequestId()
  const createReportRunMutation = useMutation({
    mutationFn: (values: TestReportGenerateFormValues) => {
      if (!projectId) throw new Error('缺少项目信息，无法生成测试报告')
      const input = {
        sprintId,
        snapshotDate: todayDate,
        connectionId: values.connectionId,
        instruction: values.instruction?.trim() || undefined,
      }
      const requestId = pendingReportRequest.forInput(JSON.stringify({ projectId, ...input }))
      return api.createTestReportGenerateRun(projectId, { ...input, requestId })
    },
    onSuccess: () => {
      pendingReportRequest.clear()
      message.success('报告生成已开始')
      setReportDrawerOpen(false)
      reportForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['testReportGenerateRuns', projectId, sprintId] })
    },
  })
  const downloadReportPdfMutation = useMutation({
    mutationFn: (run: TestReportGenerateRun) => {
      const runId = getRunId(run)
      if (!runId) throw new Error('缺少报告运行 ID，无法导出 PDF')
      return api.downloadTestReportGenerateRunPdf(runId)
    },
    onSuccess: (response, run) => {
      const runId = getRunId(run)
      saveBlob(response.blob, response.filename || `test-report-${runId}.pdf`)
    },
  })

  const reportRuns = listItems(reportRunsQuery.data)
  const latestReportRun = reportRuns[0]
  const latestSuccessfulReport = reportRuns.find(run => getRunStatusMeta(run.status).value === 'success' && Boolean(getRunId(run)))
  const isReportGenerating = createReportRunMutation.isPending || isTestReportRunGenerating(latestReportRun)
  const canViewLatestReport = Boolean(latestSuccessfulReport)

  function closeReportDrawer() {
    setReportDrawerOpen(false)
    reportForm.resetFields()
  }

  function handleOpenReportDrawer() {
    if (isReportGenerating) {
      message.warning('测试报告正在生成中，请稍后再试')
      return
    }
    if (metricsLoading) {
      message.warning('统计快照加载中，请稍后再试')
      return
    }
    if (metricsError || !metricsHasData) {
      message.warning('请先更新数据后再生成测试报告')
      return
    }
    setReportDrawerOpen(true)
  }

  function handleCreateReportRun(values: TestReportGenerateFormValues) {
    createReportRunMutation.mutate(values)
  }

  function handleViewReport(run: TestReportGenerateRun) {
    const runId = getRunId(run)
    if (!runId) {
      message.warning('缺少报告运行 ID，无法查看报告')
      return
    }
    setReportModalRunId(runId)
  }

  function closeReportModal() {
    setReportModalRunId('')
  }

  function handleDownloadReportPdf(run: TestReportGenerateRun) {
    if (getRunStatusMeta(run.status).value !== 'success' || !getRunReportMarkdown(run)) {
      message.warning('报告未生成完成，暂不能导出 PDF')
      return
    }
    downloadReportPdfMutation.mutate(run)
  }

  return {
    reportDrawerOpen,
    setReportDrawerOpen,
    reportHistoryOpen,
    setReportHistoryOpen,
    reportModalRunId,
    setReportModalRunId,
    reportForm,
    reportRunsQuery,
    reportRunDetailQuery,
    createReportRunMutation,
    downloadReportPdfMutation,
    reportRuns,
    latestReportRun,
    latestSuccessfulReport,
    isReportGenerating,
    canViewLatestReport,
    closeReportDrawer,
    handleOpenReportDrawer,
    handleCreateReportRun,
    handleViewReport,
    closeReportModal,
    handleDownloadReportPdf,
  } as const
}
