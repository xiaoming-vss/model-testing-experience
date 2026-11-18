import { CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined, PauseCircleOutlined } from '@ant-design/icons'
import type { ModuleAgentProgress, ModuleGenerationProgress } from '../api/generationChain.api'

const labels: Record<ModuleAgentProgress['status'], string> = {
  queued: '排队中', running: '生成中', repairing: '校验修复中', completed: '已完成', failed: '失败', canceled: '已停止',
}

export function ModuleGenerationProgressPanel({ progress }: { progress: ModuleGenerationProgress }) {
  const completed = progress.modules.filter(module => module.status === 'completed').length
  const running = progress.modules.filter(module => module.status === 'running' || module.status === 'repairing').length
  const points = progress.stage === 'case_names'
  const active = ['running', 'merging', 'reviewing', 'revising'].includes(progress.status)
  const status = progress.status === 'reviewing' ? ((progress.reviewRound ?? 1) > 1 ? `第 ${progress.reviewRound} 轮增量复核` : '正在进行首次全局覆盖与依据审查')
    : progress.status === 'revising' ? `正在修订 ${progress.issueCount ?? 0} 条审查意见，保留未受影响内容`
      : progress.status === 'review_failed' ? `测试点候选已生成，仍有 ${progress.issueCount ?? 0} 条审查意见待人工核查`
        : progress.status === 'merging' ? (points ? '正在合并测试点并统一编号' : '正在合并并校验完整用例')
    : progress.status === 'failed' ? '生成失败，未发布部分结果'
      : progress.status === 'canceled' ? '本次生成已停止'
        : progress.status === 'completed' ? (points ? '测试点生成及独立复核完成' : '完整用例生成完成')
          : `${running} 个生成中 · 最多同时 ${progress.concurrency} 个`

  return <section className="module-generation-progress min-w-0 flex-none border-b border-[var(--app-surface-divider)] p-4 text-[var(--app-text)] [container-type:inline-size]" aria-label={points ? "测试点分组进度" : "模块生成进度"}>
    <details open={active || progress.status === 'failed' || progress.status === 'review_failed'}>
      <summary className="cursor-pointer leading-[1.6] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--app-accent)]">
        <strong className="me-4 text-[15px]">子 Agent 执行进度</strong>
        <span className="text-[14px] tabular-nums text-[var(--app-surface-text-muted)]">{points ? '初稿已完成' : '已完成'} {completed}/{progress.modules.length} {points ? '个分组' : '个模块'}</span>
      </summary>
      <p role="status" aria-live="polite" className="module-generation-summary my-2 text-[14px] tabular-nums text-[var(--app-surface-text-muted)]">{status}</p>
      <ul aria-label="模块子任务" className="module-generation-list m-0 max-h-[260px] list-none overflow-auto p-0">
        {progress.modules.map(module => {
          const Icon = module.status === 'running' || module.status === 'repairing' ? LoadingOutlined
            : module.status === 'completed' ? CheckCircleOutlined
              : module.status === 'failed' ? CloseCircleOutlined : PauseCircleOutlined
          const iconTone = module.status === 'running' || module.status === 'repairing' ? 'text-[var(--app-accent)]'
            : module.status === 'completed' ? 'text-[var(--app-result-success-text)]' : ''
          return <li key={module.id} className={`module-generation-row grid grid-cols-[18px_minmax(0,1fr)_auto_minmax(130px,auto)] items-center gap-3 border-b border-[var(--app-surface-divider)] py-2.5 text-[14px] last:border-b-0 is-${module.status}`}>
            <Icon aria-hidden className={iconTone} />
            <span className="module-generation-name [overflow-wrap:anywhere]">{module.module}</span>
            <span className={`module-generation-status${module.status === 'failed' ? ' text-[var(--app-result-failed-text)]' : ''}`}>{labels[module.status]}{module.status === 'repairing' ? ` ${module.repairAttempt}/2` : ''}</span>
            <span className="module-generation-result text-end">{module.status === 'completed' ? `${points ? (module.pointCount ?? 0) + ' 个测试点（初稿）' : module.caseCount + ' 条用例'} · ${Math.ceil(module.elapsedMs / 1000)} 秒` : ''}</span>
          </li>
        })}
      </ul>
    </details>
  </section>
}
