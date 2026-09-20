export type RunPipelineStageKey = 'generate' | 'review' | 'import'
export type RunPipelineStageState = 'done' | 'current' | 'fail' | 'idle'
export type RunPipelineTone = 'processing' | 'success' | 'error' | 'warning' | 'purple' | 'muted'
export type RunPipelineFilterKey =
  | 'running'
  | 'review_pending'
  | 'import_pending'
  | 'imported'
  | 'rejected'
  | 'failed'
  | 'canceled'

export type RunPipelineModel = {
  stages: Array<{ key: RunPipelineStageKey; label: string; state: RunPipelineStageState; tooltip: string }>
  statusLabel: string
  statusTone: RunPipelineTone
  filterKey: RunPipelineFilterKey
}

const inProgressRunStatuses = ['pending', 'claimed', 'running', 'waiting_review']

export function getRunPipelineModel(
  run: { status?: string; reviewStatus?: string; importStatus?: string },
  options?: { stages?: RunPipelineStageKey[] },
): RunPipelineModel {
  const includeReview = !options?.stages || options.stages.includes('review')
  const includeImport = !options?.stages || options.stages.includes('import')
  const status = (run.status ?? '').toLowerCase()
  const reviewStatus = run.reviewStatus ?? ''
  const importStatus = run.importStatus ?? ''
  const succeeded = status === 'success'
  const failed = status === 'failed' || status === 'error'
  const canceled = status === 'canceled'
  const inProgress = inProgressRunStatuses.includes(status)

  const generateState: RunPipelineStageState = succeeded ? 'done' : failed ? 'fail' : inProgress ? 'current' : 'idle'
  const reviewState: RunPipelineStageState = !succeeded
    ? 'idle'
    : reviewStatus === 'approved'
      ? 'done'
      : reviewStatus === 'rejected'
        ? 'fail'
        : 'current'
  const importState: RunPipelineStageState =
    reviewStatus === 'approved' ? (importStatus === 'imported' ? 'done' : 'current') : 'idle'

  const stages: RunPipelineModel['stages'] = [
    {
      key: 'generate',
      label: '生成',
      state: generateState,
      tooltip: succeeded ? '生成成功' : failed ? '生成失败' : '生成中',
    },
    ...(includeReview
      ? [{
          key: 'review' as const,
          label: '审核',
          state: reviewState,
          tooltip: !succeeded ? '未开始' : reviewStatus === 'approved' ? '审核通过' : reviewStatus === 'rejected' ? '已拒绝' : '待审核',
        }]
      : []),
    ...(includeImport
      ? [{
          key: 'import' as const,
          label: '导入',
          state: importState,
          tooltip: importState === 'done' ? '已导入' : importState === 'current' ? '待导入' : '未开始',
        }]
      : []),
  ]

  if (failed) {
    return { stages, statusLabel: status === 'error' ? '异常' : '失败', statusTone: 'error', filterKey: 'failed' }
  }
  if (canceled) {
    return { stages, statusLabel: '已取消', statusTone: 'muted', filterKey: 'canceled' }
  }
  if (inProgress) {
    return {
      stages,
      statusLabel: includeReview && status === 'waiting_review' ? '待审核' : '执行中',
      statusTone: 'processing',
      filterKey: 'running',
    }
  }
  if (includeReview && reviewStatus === 'rejected') {
    return { stages, statusLabel: '已拒绝', statusTone: 'error', filterKey: 'rejected' }
  }
  if (includeImport && reviewStatus === 'approved') {
    return importStatus === 'imported'
      ? { stages, statusLabel: '已导入', statusTone: 'success', filterKey: 'imported' }
      : { stages, statusLabel: '待导入', statusTone: 'purple', filterKey: 'import_pending' }
  }
  if (includeReview) {
    return { stages, statusLabel: '待审核', statusTone: 'warning', filterKey: 'review_pending' }
  }
  return { stages, statusLabel: '成功', statusTone: 'success', filterKey: 'imported' }
}
