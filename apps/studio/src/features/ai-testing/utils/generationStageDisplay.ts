import { formatTime } from '@/utils/format'
import type { GenerationChainStage } from '../api/generationChain.api'

const labels: Record<string, string> = { approved: '已通过', draft: '待审核', invalid: '已作废', running: '运行中', failed: '执行失败', not_started: '未开始', imported: '已导入' }
export function generationStageLabel(stage: GenerationChainStage) {
  if (stage.state === 'running') return '运行中'
  if (stage.draft?.invalidated) return '已作废'
  if (stage.draft) return stage.draft.status === 'rejected' ? '已退回' : '待审核'
  return labels[stage.state] ?? stage.state
}
export function generationFailureMeta(stage: GenerationChainStage) {
  return [
    stage.failureRunId ? `运行 ID：${stage.failureRunId}` : '',
    stage.failedAt ? `失败时间：${formatTime(stage.failedAt)}` : '',
  ].filter(Boolean).join(' · ')
}
export function generationStageClass(stage: GenerationChainStage) {
  if (stage.state === 'running') return 'is-running'
  if (stage.draft?.invalidated || stage.draft?.status === 'rejected') return 'is-rejected'
  if (stage.draft) return 'is-draft'
  return ({ running: 'is-running', failed: 'is-failed', imported: 'is-imported', approved: 'is-approved' } as Record<string, string>)[stage.state] ?? 'is-empty'
}
